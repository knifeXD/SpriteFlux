#!/usr/bin/env python3
"""Remove a declared translucent magenta VFX layer while protecting actor pixels."""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _in_ranges(index: int, ranges: list[list[int]]) -> bool:
    return any(int(start) <= index <= int(end) for start, end in ranges)


def _largest_component(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    best: list[tuple[int, int]] = []
    for start_y, start_x in zip(*np.nonzero(mask)):
        if visited[start_y, start_x]:
            continue
        visited[start_y, start_x] = True
        queue = deque([(int(start_y), int(start_x))])
        component: list[tuple[int, int]] = []
        while queue:
            y, x = queue.popleft(); component.append((y, x))
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    if mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True; queue.append((ny, nx))
        if len(component) > len(best):
            best = component
    result = np.zeros(mask.shape, dtype=np.uint8)
    for y, x in best:
        result[y, x] = 255
    return result


def _clean_frame(image: Image.Image, contract: dict, active: bool) -> tuple[Image.Image, dict]:
    rgba = np.asarray(image.convert("RGBA")).copy()
    if not active:
        return Image.fromarray(rgba, "RGBA"), {"candidatePixels": 0, "removedPixels": 0, "protectedPixels": 0}
    gate = contract["colorGate"]
    rgb = rgba[:, :, :3].astype(np.int16)
    alpha = rgba[:, :, 3]
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    if contract.get("removeAllUnprotectedForeground", False):
        candidate = alpha >= int(gate["alphaMin"])
    else:
        candidate = (
            (alpha >= int(gate["alphaMin"]))
            & (red >= int(gate["redMin"]))
            & (blue >= int(gate["blueMin"]))
            & ((red - green) >= int(gate["redMinusGreenMin"]))
            & ((blue - green) >= int(gate["blueMinusGreenMin"]))
        )
    roi = contract.get("roi")
    if roi:
        left, top, right, bottom = [int(value) for value in roi]
        roi_mask = np.zeros(alpha.shape, dtype=bool)
        roi_mask[max(0, top):min(alpha.shape[0], bottom), max(0, left):min(alpha.shape[1], right)] = True
        candidate &= roi_mask
    core_mask = alpha >= int(contract["protectedOpaqueAlphaMin"])
    if contract.get("protectLargestOpaqueComponentOnly", False):
        core_mask = _largest_component(core_mask) > 0
    core = Image.fromarray(core_mask.astype(np.uint8) * 255, "L")
    radius = int(contract["protectedRadiusPx"])
    protected = np.asarray(core.filter(ImageFilter.MaxFilter(radius * 2 + 1))) > 0
    remove = candidate & ~protected
    opaque_changed = int(np.count_nonzero(remove & core_mask))
    if opaque_changed:
        raise ValueError("protected_opaque_pixels_would_change")
    rgba[remove] = 0
    return Image.fromarray(rgba, "RGBA"), {
        "candidatePixels": int(np.count_nonzero(candidate)),
        "removedPixels": int(np.count_nonzero(remove)),
        "protectedPixels": int(np.count_nonzero(candidate & protected)),
    }


def _checker(size: tuple[int, int], tile: int = 16) -> Image.Image:
    width, height = size
    y, x = np.indices((height, width))
    pattern = ((x // tile + y // tile) % 2)[:, :, None]
    colors = np.array([[52, 52, 52], [188, 188, 188]], dtype=np.uint8)
    return Image.fromarray(colors[pattern[:, :, 0]], "RGB")


def _qa_sheets(frames: list[Image.Image], timestamps: list[float], output_dir: Path, samples: int) -> dict[str, str]:
    indices = sorted({round(i * (len(frames) - 1) / (samples - 1)) for i in range(samples)})
    columns = min(4, len(indices)); rows = math.ceil(len(indices) / columns)
    thumb_width = 445; thumb_height = round(frames[0].height * thumb_width / frames[0].width)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    for name, color in {"dark": (18, 18, 22), "light": (235, 235, 235), "checker": None}.items():
        sheet = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + 24)), (24, 24, 24))
        draw = ImageDraw.Draw(sheet)
        for slot, index in enumerate(indices):
            foreground = frames[index].resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            background = _checker((thumb_width, thumb_height)) if color is None else Image.new("RGB", (thumb_width, thumb_height), color)
            background.paste(foreground, (0, 0), foreground.getchannel("A"))
            x = (slot % columns) * thumb_width; y = (slot // columns) * (thumb_height + 24)
            sheet.paste(background, (x, y))
            draw.text((x + 6, y + thumb_height + 4), f"f{index:03d} t={timestamps[index]:.3f}s", fill=(235, 235, 235))
        path = output_dir / f"cleaned-{name}.png"; sheet.save(path); outputs[name] = str(path)
    return outputs


def process(args: argparse.Namespace) -> dict:
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    source = json.loads(args.key_report.read_text(encoding="utf-8"))
    if int(contract.get("schemaVersion", 0)) != 1:
        return {"ok": False, "state": "invalid_contract", "errors": ["schemaVersion_must_be_1"]}
    if args.report.exists() or (args.output_dir.exists() and any(args.output_dir.iterdir())):
        return {"ok": False, "state": "output_conflict", "errors": ["output_must_be_new"]}
    frame_items = source.get("frames", [])
    paths = [Path(item["file"]) for item in frame_items]
    if not paths or not all(path.exists() for path in paths):
        return {"ok": False, "state": "source_missing", "errors": ["keyed_frame_missing"]}
    ranges = contract.get("frameRanges", [])
    if not ranges or any(len(item) != 2 or int(item[0]) > int(item[1]) for item in ranges):
        return {"ok": False, "state": "invalid_contract", "errors": ["frameRanges_required"]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []; frames = []; total_removed = 0; changed_frames = 0
    for item, path in zip(frame_items, paths):
        source_index = int(item["sourceIndex"])
        image = Image.open(path).convert("RGBA")
        cleaned, metrics = _clean_frame(image, contract, _in_ranges(source_index, ranges))
        output = args.output_dir / path.name
        cleaned.save(output, optimize=True)
        changed = _sha256(output) != _sha256(path)
        if changed and not _in_ranges(source_index, ranges):
            raise ValueError("pixel_change_outside_declared_frame_ranges")
        total_removed += metrics["removedPixels"]; changed_frames += int(changed)
        outputs.append({"file": str(output), "sha256": _sha256(output), "sourceIndex": source_index,
                        "pts": item["pts"], "sourceTime": item["sourceTime"], "changed": changed, "metrics": metrics})
        frames.append(cleaned)
    if total_removed < int(contract["minimumTotalRemovedPixels"]):
        return {"ok": False, "state": "removal_gate_failed", "errors": ["removed_pixel_count_below_contract"]}
    timestamps = [float(item["sourceTime"]) for item in frame_items]
    qa = _qa_sheets(frames, timestamps, args.qa_dir, args.samples)
    report = {"schemaVersion": 1, "source": {"keyReport": str(args.key_report), "frameCount": len(paths),
              "videoSha256": key_report.get("source", {}).get("videoSha256")},
              "contract": contract, "summary": {"changedFrames": changed_frames, "totalRemovedPixels": total_removed,
              "outsideRangeChanges": 0, "protectedOpaqueChanges": 0}, "qaSheets": qa, "frames": outputs,
              "qa": {"status": "pending_dark_light_checker_visual_review", "registrationReady": False}}
    _atomic_json(args.report, report)
    return {"ok": True, "state": "cleaned_pending_visual_qa", "frameCount": len(paths),
            "changedFrames": changed_frames, "totalRemovedPixels": total_removed, "qaSheets": qa, "report": str(args.report)}


def self_test() -> None:
    image = Image.new("RGBA", (80, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image); draw.rectangle((10, 8, 35, 58), fill=(60, 45, 55, 255))
    draw.rectangle((36, 20, 38, 24), fill=(160, 80, 160, 100))
    draw.arc((45, 8, 74, 42), 20, 310, fill=(180, 80, 190, 120), width=5)
    contract = {"colorGate": {"alphaMin": 5, "redMin": 70, "blueMin": 70,
                "redMinusGreenMin": 20, "blueMinusGreenMin": 20},
                "protectedOpaqueAlphaMin": 220, "protectedRadiusPx": 4, "roi": [0, 0, 80, 64]}
    cleaned, metrics = _clean_frame(image, contract, True)
    assert metrics["removedPixels"] > 30 and cleaned.getpixel((37, 22))[3] == 100
    assert cleaned.getpixel((60, 10))[3] == 0 and cleaned.getpixel((20, 20))[3] == 255
    image.putpixel((70, 50), (180, 180, 180, 255))
    strict = dict(contract); strict["removeAllUnprotectedForeground"] = True
    strict["protectLargestOpaqueComponentOnly"] = True
    cleaned, metrics = _clean_frame(image, strict, True)
    assert cleaned.getpixel((70, 50))[3] == 0 and cleaned.getpixel((20, 20))[3] == 255
    unchanged, metrics = _clean_frame(image, contract, False)
    assert metrics["removedPixels"] == 0 and np.array_equal(np.asarray(unchanged), np.asarray(image))
    print("remove_external_vfx self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-report", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--qa-dir", type=Path)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if any(value is None for value in (args.key_report, args.contract, args.output_dir, args.report, args.qa_dir)):
        parser.error("key-report, contract, output-dir, report and qa-dir are required")
    if args.samples < 2:
        parser.error("samples must be at least 2")
    result = process(args); print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
