#!/usr/bin/env python3
"""Split already-keyed grid cells and apply one canonical transform per take."""

from __future__ import annotations

import argparse
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


def _bbox(alpha: np.ndarray) -> list[int] | None:
    ys, xs = np.nonzero(alpha >= 128)
    if not len(xs): return None
    return [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]


def _foot_root_x(alpha: np.ndarray, bbox: list[int], band: int = 18) -> float:
    bottom = bbox[3]
    ys, xs = np.nonzero((alpha >= 128) & (np.indices(alpha.shape)[0] >= max(bbox[1], bottom - band)))
    if not len(xs): raise ValueError("support_foot_band_empty")
    return float(np.median(xs))


def _premultiplied_box(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    alpha = rgba[:, :, 3:4] / 255.0
    premultiplied = np.concatenate((rgba[:, :, :3] * alpha, rgba[:, :, 3:4]), axis=2)
    channels = []
    for index in range(4):
        channel = Image.fromarray(premultiplied[:, :, index].astype(np.float32), "F")
        channels.append(np.asarray(channel.resize(size, Image.Resampling.BOX), dtype=np.float32))
    reduced_alpha = np.clip(channels[3] / 255.0, 0.0, 1.0)
    reduced_rgb = np.stack(channels[:3], axis=2)
    divisor = np.maximum(reduced_alpha[:, :, None], 1e-6)
    reduced_rgb = np.clip(reduced_rgb / divisor, 0.0, 255.0)
    binary = reduced_alpha >= 0.5
    reduced_rgb[~binary] = 0.0
    output = np.dstack((np.rint(reduced_rgb).astype(np.uint8), (binary.astype(np.uint8) * 255)))
    return Image.fromarray(output, "RGBA")


def _crop_box(size: tuple[int, int], cell: int, columns: int, rows: int) -> tuple[int, int, int, int]:
    width, height = size; row, column = divmod(cell, columns)
    return (round(column * width / columns), round(row * height / rows),
            round((column + 1) * width / columns), round((row + 1) * height / rows))


def _shared_transform(reference: Image.Image, scale: float, root: tuple[int, int], baseline: int) -> dict:
    scaled_size = (round(reference.width * scale), round(reference.height * scale))
    scaled = _premultiplied_box(reference, scaled_size)
    alpha = np.asarray(scaled.getchannel("A")); bbox = _bbox(alpha)
    if not bbox: raise ValueError("scaled_reference_empty")
    source_root_x = _foot_root_x(alpha, bbox)
    offset = [round(root[0] - source_root_x), baseline - bbox[3]]
    return {"requestedScale": scale, "scaledCell": list(scaled_size),
            "effectiveScaleX": scaled_size[0] / reference.width,
            "effectiveScaleY": scaled_size[1] / reference.height,
            "scaledReferenceBbox": bbox, "scaledReferenceFootRootX": source_root_x,
            "offset": offset}


def _apply(image: Image.Image, transform: dict, canvas: tuple[int, int]) -> Image.Image:
    scaled = _premultiplied_box(image, tuple(transform["scaledCell"]))
    output = Image.new("RGBA", canvas, (0, 0, 0, 0))
    output.alpha_composite(scaled, tuple(transform["offset"]))
    return output


def _uniform_within_pixel_quantization(transform: dict, source_size: tuple[int, int]) -> bool:
    tolerance = max(1.0 / source_size[0], 1.0 / source_size[1])
    return abs(transform["effectiveScaleX"] - transform["effectiveScaleY"]) <= tolerance


def _qa_sheet(actions: list[dict], output: Path, canvas: tuple[int, int], root: tuple[int, int], baseline: int) -> None:
    columns = 3; rows = len(actions); label = 28
    sheet = Image.new("RGB", (columns * canvas[0], rows * (canvas[1] + label)), (20, 20, 24))
    draw = ImageDraw.Draw(sheet)
    for row, action in enumerate(actions):
        frames = action["runtimeFrames"]
        choices = [0, len(frames) // 2, len(frames) - 1]
        for column, index in enumerate(choices):
            frame = Image.open(frames[index]["file"]).convert("RGBA")
            background = Image.new("RGB", canvas, (28, 28, 34)); background.paste(frame, (0, 0), frame.getchannel("A"))
            x, y = column * canvas[0], row * (canvas[1] + label)
            sheet.paste(background, (x, y)); draw.line((x, y + baseline, x + canvas[0], y + baseline), fill=(90, 130, 180), width=1)
            draw.line((x + root[0], y, x + root[0], y + canvas[1]), fill=(180, 90, 90), width=1)
            draw.text((x + 5, y + canvas[1] + 5),
                      f"{action['actionId']} f{frames[index]['sourceIndex']} t={frames[index]['sourceTime']:.3f}", fill=(235, 235, 235))
    output.parent.mkdir(parents=True, exist_ok=True); sheet.save(output)


def register(args: argparse.Namespace) -> dict:
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    key_report_path = (args.contract.parent / contract["sourceKeyReport"]).resolve()
    key_report = json.loads(key_report_path.read_text(encoding="utf-8"))
    keyed_items = key_report["frames"]; keyed_paths = [Path(item["file"]) for item in keyed_items]
    if not keyed_paths or not all(path.exists() for path in keyed_paths):
        return {"ok": False, "state": "source_missing", "errors": ["keyed_frame_missing"]}
    contract_hash = _sha256(args.contract)
    if args.report.exists():
        existing = json.loads(args.report.read_text(encoding="utf-8"))
        files = [Path(frame["file"]) for action in existing.get("actions", []) for frame in action.get("runtimeFrames", [])]
        if existing.get("source", {}).get("contractSha256") == contract_hash and files and all(path.exists() for path in files):
            return {"ok": True, "state": "already_registered", "report": str(args.report), "frameCount": len(files)}
        return {"ok": False, "state": "output_conflict", "errors": ["registration_report_mismatch"]}
    canonical = contract["canonical"]; canvas = tuple(canonical["canvas"]); root = tuple(canonical["root"])
    baseline = int(canonical["baselineY"]); safe_margin = int(canonical["minimumSafeMarginPx"])
    first = Image.open(keyed_paths[0]).convert("RGBA"); columns, rows = args.columns, args.rows
    scale_reference = contract["scaleReference"]
    ref_box = _crop_box(first.size, int(scale_reference["cellIndex"]), columns, rows)
    ref_index = int(scale_reference["frameIndex"])
    ref_cell = Image.open(keyed_paths[ref_index]).convert("RGBA").crop(ref_box)
    ref_bbox = _bbox(np.asarray(ref_cell.getchannel("A")))
    if not ref_bbox: return {"ok": False, "state": "reference_empty", "errors": ["scale_reference_has_no_subject"]}
    reference_height = ref_bbox[3] - ref_bbox[1]
    requested_scale = int(canonical["baseStandingHeightPx"]) / reference_height
    actions = []; total_bytes = 0
    for cell_spec in contract["cells"]:
        cell_index = int(cell_spec["cellIndex"]); action_id = cell_spec["actionId"]
        crop = _crop_box(first.size, cell_index, columns, rows)
        reference_index = int(cell_spec["referenceFrameIndex"])
        reference = Image.open(keyed_paths[reference_index]).convert("RGBA").crop(crop)
        transform = _shared_transform(reference, requested_scale, root, baseline)
        if not _uniform_within_pixel_quantization(transform, reference.size):
            return {"ok": False, "state": "non_uniform_scale", "errors": [action_id]}
        window = cell_spec["sourceWindow"]; start, end = int(window["first"]), int(window["lastInclusive"])
        action_dir = args.output_dir / action_id; action_dir.mkdir(parents=True, exist_ok=False)
        runtime_frames = []; union = [canvas[0], canvas[1], 0, 0]
        for source_index in range(start, end + 1):
            source = Image.open(keyed_paths[source_index]).convert("RGBA").crop(crop)
            registered = _apply(source, transform, canvas)
            bbox = _bbox(np.asarray(registered.getchannel("A")))
            if not bbox: return {"ok": False, "state": "registered_frame_empty", "errors": [f"{action_id}:{source_index}"]}
            union = [min(union[0], bbox[0]), min(union[1], bbox[1]), max(union[2], bbox[2]), max(union[3], bbox[3])]
            output = action_dir / f"frame-{len(runtime_frames):04d}.png"; registered.save(output, optimize=True)
            total_bytes += output.stat().st_size
            runtime_frames.append({"file": str(output), "sha256": _sha256(output), "sourceIndex": source_index,
                                   "pts": keyed_items[source_index]["pts"], "sourceTime": keyed_items[source_index]["sourceTime"],
                                   "alphaBbox": bbox})
        margins = [union[0], union[1], canvas[0] - union[2], canvas[1] - union[3]]
        actions.append({"actionId": action_id, "cellIndex": cell_index, "sourceCrop": list(crop),
                        "sourceWindow": cell_spec["sourceWindow"], "activeWindow": cell_spec.get("activeWindow"),
                        "phase": cell_spec["phase"], "sharedTransform": transform,
                        "unionBbox": union, "margins": margins, "safeMarginPass": min(margins) >= safe_margin,
                        "runtimeFrames": runtime_frames})
    failed = [action["actionId"] for action in actions if not action["safeMarginPass"]]
    _qa_sheet(actions, args.qa_sheet, canvas, root, baseline)
    report = {"schemaVersion": 1, "source": {"contract": str(args.contract), "contractSha256": contract_hash,
              "keyReport": str(key_report_path), "videoSha256": key_report["source"]["videoSha256"]},
              "canonical": canonical, "scaleReference": {**scale_reference, "sourceAlphaBbox": ref_bbox,
              "sourceVisibleHeight": reference_height, "requestedUniformScale": requested_scale},
              "actions": actions, "resource": {"compressedBytes": total_bytes,
              "decodedRgbaBytes": canvas[0] * canvas[1] * 4 * sum(len(action["runtimeFrames"]) for action in actions)},
              "qa": {"status": "failed_safe_margin" if failed else "pending_gameplay_size_visual_review",
                     "failedSafeMarginActions": failed, "sharedScalePass": True,
                     "perFrameNormalizationUsed": False, "runtimeReady": False},
              "qaSheet": str(args.qa_sheet)}
    _atomic_json(args.report, report)
    return {"ok": not failed, "state": report["qa"]["status"], "referenceHeight": reference_height,
            "uniformScale": requested_scale, "canvas": list(canvas), "root": list(root), "baseline": baseline,
            "actions": [{"actionId": action["actionId"], "frameCount": len(action["runtimeFrames"]),
                         "unionBbox": action["unionBbox"], "margins": action["margins"],
                         "safeMarginPass": action["safeMarginPass"]} for action in actions],
            "compressedBytes": total_bytes, "qaSheet": str(args.qa_sheet), "report": str(args.report)}


def self_test() -> None:
    image = Image.new("RGBA", (60, 90), (0, 0, 0, 0)); ImageDraw.Draw(image).rectangle((20, 15, 39, 74), fill=(100, 80, 60, 255))
    transform = _shared_transform(image, 0.5, (48, 80), 80)
    output = _apply(image, transform, (96, 96)); bbox = _bbox(np.asarray(output.getchannel("A")))
    assert bbox and bbox[3] == 80 and abs(_foot_root_x(np.asarray(output.getchannel("A")), bbox) - 48.0) <= 0.5
    assert _crop_box((200, 100), 1, 2, 1) == (100, 0, 200, 100)
    quantized = {"effectiveScaleX": 386 / 752, "effectiveScaleY": 287 / 560}
    assert _uniform_within_pixel_quantization(quantized, (752, 560))
    assert not _uniform_within_pixel_quantization({"effectiveScaleX": 0.51, "effectiveScaleY": 0.50}, (752, 560))
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "report.json"; _atomic_json(path, {"ok": True})
        assert json.loads(path.read_text(encoding="utf-8"))["ok"]
    print("register_sprite_cells self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--contract", type=Path)
    parser.add_argument("--output-dir", type=Path); parser.add_argument("--report", type=Path)
    parser.add_argument("--qa-sheet", type=Path); parser.add_argument("--columns", type=int, default=1)
    parser.add_argument("--rows", type=int, default=1); parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test: self_test(); return
    if any(value is None for value in (args.contract, args.output_dir, args.report, args.qa_sheet)):
        parser.error("contract, output-dir, report and qa-sheet are required")
    result = register(args); print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__": main()
