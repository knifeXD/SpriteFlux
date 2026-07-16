#!/usr/bin/env python3
"""Build fixed-palette beauty, normal, and mask channels from registered frames."""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _indices(count: int, stride: int, include_last: bool) -> list[int]:
    result = list(range(0, count, stride))
    if include_last and result[-1] != count - 1: result.append(count - 1)
    return result


def _border_connected(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    parent: list[int] = []
    border: list[bool] = []
    runs: list[tuple[int, int, int, int]] = []

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left
            border[left] = border[left] or border[right]

    previous: list[tuple[int, int, int]] = []
    for y, row in enumerate(mask):
        transitions = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        current: list[tuple[int, int, int]] = []
        for start, end in zip(np.flatnonzero(transitions == 1).tolist(), np.flatnonzero(transitions == -1).tolist()):
            label = len(parent); parent.append(label)
            border.append(y == 0 or y == height - 1 or start == 0 or end == width)
            current.append((start, end, label)); runs.append((y, start, end, label))
            for old_start, old_end, old_label in previous:
                if old_end >= start - 1 and old_start <= end + 1:
                    union(label, old_label)
        previous = current
    connected = np.zeros(mask.shape, dtype=bool)
    for y, start, end, label in runs:
        if border[find(label)]:
            connected[y, start:end] = True
    return connected


def _topology(alpha: np.ndarray, source_background_support: np.ndarray | None = None) -> dict:
    foreground = alpha >= 128
    transparent = ~foreground
    interior = transparent & ~_border_connected(transparent)
    supported = np.zeros(interior.shape, dtype=bool)
    if source_background_support is not None:
        supported = interior & source_background_support
    unsupported = interior & ~supported
    return {"opaquePixels": int(np.count_nonzero(foreground)),
            "interiorTransparentPixels": int(np.count_nonzero(interior)),
            "sourceConnectedNegativeSpacePixels": int(np.count_nonzero(supported)),
            "unsupportedInteriorTransparentPixels": int(np.count_nonzero(unsupported))}


def _project_source_background_support(key_frame: Path, source_crop: list[int], transform: dict,
                                       canvas: tuple[int, int]) -> np.ndarray:
    source = Image.open(key_frame).convert("RGBA").crop(tuple(source_crop))
    alpha = np.asarray(source.getchannel("A"), dtype=np.uint8)
    exterior_background = _border_connected(alpha < 128)
    scaled = Image.fromarray(exterior_background.astype(np.uint8) * 255, "L").resize(
        tuple(transform["scaledCell"]), Image.Resampling.BOX)
    projected = Image.new("L", canvas, 0)
    projected.paste(scaled, tuple(transform["offset"]))
    return np.asarray(projected, dtype=np.uint8) > 0


def _palette(frames: list[Image.Image], colors: int) -> np.ndarray:
    opaque = []
    for frame in frames:
        array = np.asarray(frame.convert("RGBA"))
        values = array[:, :, :3][array[:, :, 3] >= 128]
        if len(values): opaque.append(values[::max(1, len(values) // 12000)])
    pixels = np.concatenate(opaque, axis=0)
    if len(pixels) > 500000: pixels = pixels[::math.ceil(len(pixels) / 500000)]
    width = min(1024, len(pixels)); height = math.ceil(len(pixels) / width)
    padded = np.zeros((height * width, 3), dtype=np.uint8); padded[:len(pixels)] = pixels
    sample = Image.fromarray(padded.reshape(height, width, 3), "RGB")
    quantized = sample.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw_palette = quantized.getpalette()
    actual_colors = min(colors, len(raw_palette) // 3)
    values = np.asarray(raw_palette[:actual_colors * 3], dtype=np.uint8).reshape(actual_colors, 3)
    return np.unique(values, axis=0)


def _map_palette(frame: Image.Image, palette: np.ndarray) -> Image.Image:
    array = np.asarray(frame.convert("RGBA")); alpha = array[:, :, 3]
    rgb = array[:, :, :3].copy(); positions = np.flatnonzero(alpha.reshape(-1) >= 128)
    flat = rgb.reshape(-1, 3); palette_i = palette.astype(np.int16)
    for start in range(0, len(positions), 8192):
        selected = positions[start:start + 8192]
        values = flat[selected].astype(np.int16)
        distance = np.square(values[:, None, :] - palette_i[None, :, :]).sum(axis=2)
        flat[selected] = palette[np.argmin(distance, axis=1)]
    flat[np.flatnonzero(alpha.reshape(-1) < 128)] = 0
    binary = np.where(alpha >= 128, 255, 0).astype(np.uint8)
    return Image.fromarray(np.dstack((rgb, binary)), "RGBA")


def _stabilize_dark_outliers(frames: list[Image.Image], contract: dict) -> tuple[list[Image.Image], list[int]]:
    if not contract.get("enabled", False):
        return frames, [0] * len(frames)
    arrays = [np.asarray(frame.convert("RGBA")).copy() for frame in frames]
    result = [array.copy() for array in arrays]; counts: list[int] = []
    dark_max = int(contract.get("darkMax", 24)); spatial_delta = int(contract.get("spatialDelta", 40))
    temporal_delta = int(contract.get("temporalDelta", 32)); cyclic = bool(contract.get("cyclic", False))
    require_temporal = bool(contract.get("requireTemporalConfirmation", True))
    for index, array in enumerate(arrays):
        previous = arrays[(index - 1) % len(arrays)] if cyclic or index > 0 else array
        following = arrays[(index + 1) % len(arrays)] if cyclic or index + 1 < len(arrays) else array
        rgb = array[:, :, :3].astype(np.int16); alpha = array[:, :, 3] >= 128
        padded = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
        neighbours = np.stack([padded[y:y + rgb.shape[0], x:x + rgb.shape[1]]
                               for y in range(3) for x in range(3) if (y, x) != (1, 1)])
        spatial_rgb = np.median(neighbours, axis=0).astype(np.int16)
        spatial_value = spatial_rgb.max(axis=2); value = rgb.max(axis=2)
        temporal_neighbours = []
        for temporal_frame in (previous, following):
            temporal_pad = np.pad(temporal_frame[:, :, :3], ((1, 1), (1, 1), (0, 0)), mode="edge")
            temporal_neighbours.extend(temporal_pad[y:y + rgb.shape[0], x:x + rgb.shape[1]] for y in range(3) for x in range(3))
        temporal_value = np.median(np.stack(temporal_neighbours).max(axis=3), axis=0).astype(np.int16)
        core = alpha.copy(); alpha_pad = np.pad(alpha, 1, constant_values=False)
        for y in range(3):
            for x in range(3): core &= alpha_pad[y:y + alpha.shape[0], x:x + alpha.shape[1]]
        candidate = core & (value <= dark_max) & (spatial_value - value >= spatial_delta)
        if require_temporal: candidate &= temporal_value - value >= temporal_delta
        result[index][:, :, :3][candidate] = spatial_rgb[candidate].astype(np.uint8)
        counts.append(int(np.count_nonzero(candidate)))
    return [Image.fromarray(array, "RGBA") for array in result], counts


def _stabilize_post_palette_dark_components(frames: list[Image.Image], contract: dict) -> tuple[list[Image.Image], list[int]]:
    """Repair only tiny, temporally unsupported dark islands created by palette mapping."""
    if not contract.get("enabled", False):
        return frames, [0] * len(frames)
    arrays = [np.asarray(frame.convert("RGBA")).copy() for frame in frames]
    result = [array.copy() for array in arrays]; counts = [0] * len(arrays)
    dark_max = int(contract.get("darkMax", 20)); spatial_delta = int(contract.get("spatialDelta", 12))
    max_component = int(contract.get("maxComponentPixels", 4)); radius = int(contract.get("temporalMotionRadius", 2))
    cyclic = bool(contract.get("cyclic", False))
    for index, array in enumerate(arrays):
        rgb = array[:, :, :3].astype(np.int16); alpha = array[:, :, 3] >= 128; value = rgb.max(axis=2)
        core = alpha.copy(); alpha_pad = np.pad(alpha, 1, constant_values=False)
        for y in range(3):
            for x in range(3): core &= alpha_pad[y:y + alpha.shape[0], x:x + alpha.shape[1]]
        dark = core & (value <= dark_max); visited = np.zeros(dark.shape, dtype=bool)
        previous = arrays[(index - 1) % len(arrays)] if cyclic or index > 0 else array
        following = arrays[(index + 1) % len(arrays)] if cyclic or index + 1 < len(arrays) else array
        temporal_dark = [(frame[:, :, :3].max(axis=2) <= dark_max) & (frame[:, :, 3] >= 128)
                         for frame in (previous, following)]
        for start_y, start_x in zip(*np.nonzero(dark & ~visited)):
            queue = deque([(int(start_y), int(start_x))]); visited[start_y, start_x] = True; component = []
            while queue:
                y, x = queue.popleft(); component.append((y, x))
                if len(component) > max_component: break
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if (dy or dx) and 0 <= ny < dark.shape[0] and 0 <= nx < dark.shape[1] and dark[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True; queue.append((ny, nx))
            if len(component) > max_component:
                while queue:
                    y, x = queue.popleft()
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = y + dy, x + dx
                            if (dy or dx) and 0 <= ny < dark.shape[0] and 0 <= nx < dark.shape[1] and dark[ny, nx] and not visited[ny, nx]:
                                visited[ny, nx] = True; queue.append((ny, nx))
                continue
            supported = False
            for y, x in component:
                y0, y1 = max(0, y - radius), min(dark.shape[0], y + radius + 1)
                x0, x1 = max(0, x - radius), min(dark.shape[1], x + radius + 1)
                if any(np.any(mask[y0:y1, x0:x1]) for mask in temporal_dark): supported = True; break
            if supported: continue
            component_set = set(component); neighbours = []
            for y, x in component:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if (dy or dx) and 0 <= ny < dark.shape[0] and 0 <= nx < dark.shape[1] and alpha[ny, nx] and (ny, nx) not in component_set:
                            neighbours.append(rgb[ny, nx])
            if not neighbours: continue
            replacement = np.median(np.stack(neighbours), axis=0).astype(np.uint8)
            if int(replacement.max()) - max(int(value[y, x]) for y, x in component) < spatial_delta: continue
            for y, x in component: result[index][y, x, :3] = replacement
            counts[index] += len(component)
    return [Image.fromarray(array, "RGBA") for array in result], counts


def _normal(beauty: Image.Image, strength: float) -> Image.Image:
    rgba = np.asarray(beauty.convert("RGBA")); rgb = rgba[:, :, :3].astype(np.float32) / 255.0
    alpha = rgba[:, :, 3] >= 128
    luminance = rgb[:, :, 0] * 0.2126 + rgb[:, :, 1] * 0.7152 + rgb[:, :, 2] * 0.0722
    luminance[~alpha] = 0.0
    dx = (np.roll(luminance, -1, axis=1) - np.roll(luminance, 1, axis=1)) * 0.5
    dy = (np.roll(luminance, -1, axis=0) - np.roll(luminance, 1, axis=0)) * 0.5
    nx, ny, nz = -dx * strength, dy * strength, np.ones_like(dx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz); nx /= length; ny /= length; nz /= length
    encoded = np.dstack(((nx * 0.5 + 0.5) * 255.0, (ny * 0.5 + 0.5) * 255.0,
                         (nz * 0.5 + 0.5) * 255.0, alpha.astype(np.float32) * 255.0))
    encoded[~alpha, :3] = (128.0, 128.0, 255.0)
    return Image.fromarray(np.rint(encoded).astype(np.uint8), "RGBA")


def _mask(beauty: Image.Image) -> Image.Image:
    alpha = np.asarray(beauty.getchannel("A"), dtype=np.uint8)
    return Image.fromarray(np.dstack((alpha, alpha, alpha, alpha)), "RGBA")


def _qa_sheet(actions: list[dict], output: Path, canvas: tuple[int, int], baseline: int) -> None:
    columns = 3; row_height = canvas[1] + 24; rows = len(actions) * 2
    sheet = Image.new("RGB", (columns * canvas[0], rows * row_height), (18, 18, 22)); draw = ImageDraw.Draw(sheet)
    for action_index, action in enumerate(actions):
        frames = action["frames"]; chosen = [0, len(frames) // 2, len(frames) - 1]
        for column, index in enumerate(chosen):
            for channel_row, channel in enumerate(("beauty", "normal")):
                image = Image.open(frames[index][channel]).convert("RGBA")
                background = Image.new("RGB", canvas, (28, 28, 34) if channel == "beauty" else (128, 128, 255))
                background.paste(image, (0, 0), image.getchannel("A"))
                row = action_index * 2 + channel_row; x, y = column * canvas[0], row * row_height
                sheet.paste(background, (x, y)); draw.line((x, y + baseline, x + canvas[0], y + baseline), fill=(80, 120, 170))
                draw.text((x + 5, y + canvas[1] + 4), f"{action['actionId']} {channel} f{frames[index]['sourceIndex']}", fill=(235, 235, 235))
    output.parent.mkdir(parents=True, exist_ok=True); sheet.save(output)


def build(args: argparse.Namespace) -> dict:
    contract = json.loads(args.contract.read_text(encoding="utf-8")); contract_hash = _sha256(args.contract)
    registration_path = (args.contract.parent / contract["registrationReport"]).resolve()
    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    if args.report.exists():
        existing = json.loads(args.report.read_text(encoding="utf-8"))
        files = [Path(frame[channel]) for action in existing.get("actions", []) for frame in action.get("frames", [])
                 for channel in ("beauty", "normal", "mask")]
        if existing.get("source", {}).get("contractSha256") == contract_hash and files and all(path.exists() for path in files):
            return {"ok": True, "state": "already_built", "report": str(args.report), "channelFileCount": len(files)}
        return {"ok": False, "state": "output_conflict", "errors": ["pixel_channel_report_mismatch"]}
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        return {"ok": False, "state": "output_conflict", "errors": ["pixel_output_directory_not_empty"]}
    canonical = contract["canonical"]; canvas = tuple(canonical["canvas"]); pixel = contract["pixelContract"]
    registration_actions = {action["actionId"]: action for action in registration["actions"]}
    key_report_path = Path(registration["source"]["keyReport"])
    key_report = json.loads(key_report_path.read_text(encoding="utf-8"))
    key_frames = {int(frame["sourceIndex"]): Path(frame["file"]) for frame in key_report["frames"]}
    results = []; compressed = 0; decoded = 0
    for specification in contract["actions"]:
        action_id = specification["actionId"]; source_action = registration_actions[action_id]
        selected = _indices(len(source_action["runtimeFrames"]), int(specification["sampleStride"]), bool(specification["includeLastFrame"]))
        source_frames = [Image.open(source_action["runtimeFrames"][index]["file"]).convert("RGBA") for index in selected]
        source_frames, stabilized_counts = _stabilize_dark_outliers(source_frames, pixel.get("temporalColorStability", {}))
        palette = _palette(source_frames, int(pixel["paletteColorsPerAction"]))
        mapped_frames = [_map_palette(frame, palette) for frame in source_frames]
        mapped_frames, post_palette_counts = _stabilize_post_palette_dark_components(
            mapped_frames, pixel.get("postPaletteDarkComponentStability", {}))
        action_dir = args.output_dir / action_id
        for channel in ("beauty", "normal", "mask"): (action_dir / channel).mkdir(parents=True, exist_ok=False)
        frames = []; previous_area: int | None = None; max_area_drop = 0.0
        for output_index, source_local_index in enumerate(selected):
            source_item = source_action["runtimeFrames"][source_local_index]
            beauty = mapped_frames[output_index]
            normal = _normal(beauty, float(pixel["normalStrength"])); mask = _mask(beauty)
            paths = {channel: action_dir / channel / f"frame-{output_index:04d}.png" for channel in ("beauty", "normal", "mask")}
            for channel, image in (("beauty", beauty), ("normal", normal), ("mask", mask)):
                image.save(paths[channel], optimize=True); compressed += paths[channel].stat().st_size
            decoded += canvas[0] * canvas[1] * 4 * 3
            alpha = np.asarray(beauty.getchannel("A"))
            support = _project_source_background_support(
                key_frames[int(source_item["sourceIndex"])], source_action["sourceCrop"],
                source_action["sharedTransform"], canvas)
            topology = _topology(alpha, support)
            normal_alpha = np.asarray(normal.getchannel("A")); mask_alpha = np.asarray(mask.getchannel("A"))
            channel_alpha_parity = bool(np.array_equal(alpha, normal_alpha) and np.array_equal(alpha, mask_alpha))
            if previous_area is not None and previous_area > 0:
                max_area_drop = max(max_area_drop, max(0.0, (previous_area - topology["opaquePixels"]) / previous_area))
            previous_area = topology["opaquePixels"]
            frames.append({"beauty": str(paths["beauty"]), "normal": str(paths["normal"]), "mask": str(paths["mask"]),
                           "beautySha256": _sha256(paths["beauty"]), "normalSha256": _sha256(paths["normal"]),
                           "maskSha256": _sha256(paths["mask"]), "sourceIndex": source_item["sourceIndex"],
                           "pts": source_item["pts"], "sourceTime": source_item["sourceTime"],
                           "semiTransparentPixels": int(np.count_nonzero((alpha > 0) & (alpha < 255))),
                           "stabilizedDarkOutlierPixels": stabilized_counts[output_index],
                           "stabilizedPostPaletteDarkComponentPixels": post_palette_counts[output_index],
                           **topology, "channelAlphaParity": channel_alpha_parity})
        results.append({"actionId": action_id, "phase": specification["phase"], "artFps": specification["artFps"],
                        "sampleStride": specification["sampleStride"], "palette": palette.tolist(),
                        "paletteSize": len(palette), "frameCount": len(frames),
                        "maxAdjacentAreaDrop": round(max_area_drop, 6), "frames": frames})
    _qa_sheet(results, args.qa_sheet, canvas, int(canonical["baselineY"]))
    report = {"schemaVersion": 1, "source": {"contract": str(args.contract), "contractSha256": contract_hash,
              "registrationReport": str(registration_path), "videoSha256": registration["source"]["videoSha256"]},
              "canonical": canonical, "pixelContract": pixel, "actions": results,
              "resource": {"compressedBytes": compressed, "decodedRgbaBytesAllChannels": decoded},
              "qa": {"status": "pending_normal_lighting_and_temporal_visual_review", "ditheringUsed": False,
                     "binaryAlphaPass": all(frame["semiTransparentPixels"] == 0 for action in results for frame in action["frames"]),
                     "interiorTopologyPass": all(frame["unsupportedInteriorTransparentPixels"] == 0 for action in results for frame in action["frames"]),
                     "channelTransformParityPass": all(frame["channelAlphaParity"] for action in results for frame in action["frames"]),
                     "areaContinuityPass": all(action["maxAdjacentAreaDrop"] <= float(pixel.get("maxAdjacentAreaDrop", 0.35)) for action in results),
                     "runtimeReady": False}, "qaSheet": str(args.qa_sheet)}
    _atomic_json(args.report, report)
    eligible = all(report["qa"][key] for key in ("binaryAlphaPass", "interiorTopologyPass", "channelTransformParityPass", "areaContinuityPass"))
    return {"ok": eligible, "state": report["qa"]["status"] if eligible else "runtime_matte_contract_failed",
            "actions": [{"actionId": action["actionId"], "frameCount": action["frameCount"],
                         "artFps": action["artFps"], "paletteSize": action["paletteSize"]} for action in results],
            "compressedBytes": compressed, "decodedRgbaBytesAllChannels": decoded,
            "qaSheet": str(args.qa_sheet), "report": str(args.report)}


def self_test() -> None:
    frames = []
    for shift in (0, 8, 16):
        image = Image.new("RGBA", (48, 48), (0, 0, 0, 0)); ImageDraw.Draw(image).rectangle((12, 8, 35, 39), fill=(100 + shift, 60, 40, 255)); frames.append(image)
    palette = _palette(frames, 8); beauty = _map_palette(frames[0], palette); normal = _normal(beauty, 2.0); mask = _mask(beauty)
    assert beauty.size == normal.size == mask.size and len(palette) <= 8
    assert not np.any((np.asarray(beauty.getchannel("A")) > 0) & (np.asarray(beauty.getchannel("A")) < 255))
    assert _topology(np.asarray(beauty.getchannel("A")))["interiorTransparentPixels"] == 0
    holed = np.full((16, 16), 255, dtype=np.uint8); holed[6:10, 6:10] = 0
    assert _topology(holed)["unsupportedInteriorTransparentPixels"] == 16
    support = np.zeros((16, 16), dtype=bool); support[6:10, 6:10] = True
    supported = _topology(holed, support)
    assert supported["sourceConnectedNegativeSpacePixels"] == 16
    assert supported["unsupportedInteriorTransparentPixels"] == 0
    assert _indices(10, 3, True) == [0, 3, 6, 9]
    noisy = [frame.copy() for frame in frames]
    noisy_array = np.asarray(noisy[1]).copy(); noisy_array[30, 24, :3] = 0; noisy[1] = Image.fromarray(noisy_array, "RGBA")
    stable, counts = _stabilize_dark_outliers(noisy, {"enabled": True, "cyclic": True})
    assert counts[1] == 1 and np.asarray(stable[1])[30, 24, 3] == 255
    palette_noisy = [frame.copy() for frame in frames]
    array = np.asarray(palette_noisy[1]).copy(); array[24, 24, :3] = (2, 2, 2)
    palette_noisy[1] = Image.fromarray(array, "RGBA")
    cleaned, component_counts = _stabilize_post_palette_dark_components(
        palette_noisy, {"enabled": True, "cyclic": True, "darkMax": 8, "spatialDelta": 20,
                        "maxComponentPixels": 2, "temporalMotionRadius": 1})
    assert component_counts[1] == 1 and np.asarray(cleaned[1])[24, 24, :3].max() > 2
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "report.json"; _atomic_json(path, {"ok": True}); assert json.loads(path.read_text())["ok"]
    print("build_pixel_sequence_channels self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--contract", type=Path)
    parser.add_argument("--output-dir", type=Path); parser.add_argument("--report", type=Path)
    parser.add_argument("--qa-sheet", type=Path); parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test: self_test(); return
    if any(value is None for value in (args.contract, args.output_dir, args.report, args.qa_sheet)):
        parser.error("contract, output-dir, report and qa-sheet are required")
    result = build(args); print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__": main()
