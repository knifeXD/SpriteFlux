#!/usr/bin/env python3
"""Extract every provider frame with PTS metadata and create a QA contact sheet."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

SHOWINFO = re.compile(r"n:\s*(\d+).*?pts:\s*(-?\d+).*?pts_time:([0-9.eE+\-]+)")


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


def parse_showinfo(stderr: str) -> list[dict]:
    records = []
    for match in SHOWINFO.finditer(stderr):
        records.append({"sourceIndex": int(match.group(1)), "pts": int(match.group(2)),
                        "sourceTime": float(match.group(3))})
    return records


def _probe(video: Path) -> dict:
    generator = imageio_ffmpeg.read_frames(str(video), pix_fmt="rgb24")
    try:
        metadata = next(generator)
    finally:
        generator.close()
    return {
        "codec": metadata.get("codec"), "pixFmt": metadata.get("pix_fmt"),
        "sourceSize": list(metadata.get("source_size", metadata.get("size", (0, 0)))),
        "displaySize": list(metadata.get("size", (0, 0))), "fps": metadata.get("fps"),
        "durationSeconds": metadata.get("duration"), "rotation": metadata.get("rotate", 0),
    }


def _sample_indices(count: int, sample_count: int) -> list[int]:
    if count <= sample_count:
        return list(range(count))
    return sorted({round(index * (count - 1) / (sample_count - 1)) for index in range(sample_count)})


def _motion_energy(images: list[Image.Image]) -> list[float]:
    energies = [0.0]
    previous = None
    for image in images:
        current = np.asarray(image.resize((139, 104), Image.Resampling.BOX), dtype=np.int16)
        if previous is not None:
            energies.append(round(float(np.abs(current - previous).mean()), 6))
        previous = current
    return energies[:len(images)]


def _largest_component_bbox(mask: np.ndarray) -> list[int] | None:
    parent: list[int] = []
    runs: list[tuple[int, int, int, int]] = []

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    previous: list[tuple[int, int, int]] = []
    for y, row in enumerate(mask):
        padded = np.pad(row.astype(np.int8), (1, 1))
        transitions = np.diff(padded)
        starts = np.flatnonzero(transitions == 1)
        ends = np.flatnonzero(transitions == -1)
        current: list[tuple[int, int, int]] = []
        for start, end in zip(starts.tolist(), ends.tolist()):
            label = len(parent); parent.append(label)
            current.append((start, end, label)); runs.append((y, start, end, label))
            for previous_start, previous_end, previous_label in previous:
                if previous_end >= start - 1 and previous_start <= end:
                    union(label, previous_label)
        previous = current
    if not runs:
        return None
    components: dict[int, list[int]] = {}
    for y, start, end, label in runs:
        root = find(label)
        value = components.setdefault(root, [start, y, end, y + 1, 0])
        value[0] = min(value[0], start); value[1] = min(value[1], y)
        value[2] = max(value[2], end); value[3] = max(value[3], y + 1)
        value[4] += end - start
    largest = max(components.values(), key=lambda value: value[4])
    return largest[:4]


def _green_foreground_bbox(image: Image.Image, chroma: tuple[int, int, int] = (0, 255, 0)) -> list[int] | None:
    rgb = np.asarray(image.convert("RGB"), dtype=np.int32)
    key = np.asarray(chroma, dtype=np.int32)
    distance = np.sqrt(np.square(rgb - key).sum(axis=2))
    green_dominant = (rgb[:, :, 1] > rgb[:, :, 0] + 22) & (rgb[:, :, 1] > rgb[:, :, 2] + 22)
    foreground = (distance > 72) | ~green_dominant
    # Provider grids often synthesize dark gutters wider than a few pixels.
    # Cell metrics ignore a diagnostic-only 16 px perimeter; production keying
    # still operates on the untouched full frame before any crop.
    foreground[:16, :] = False; foreground[-16:, :] = False
    foreground[:, :16] = False; foreground[:, -16:] = False
    return _largest_component_bbox(foreground)


def _cell_metrics(frames: list[Image.Image], columns: int, rows: int) -> list[dict]:
    width, height = frames[0].size
    result = []
    for row in range(rows):
        for column in range(columns):
            box = (round(column * width / columns), round(row * height / rows),
                   round((column + 1) * width / columns), round((row + 1) * height / rows))
            crops = [frame.crop(box) for frame in frames]
            bboxes = [_green_foreground_bbox(crop) for crop in crops]
            valid = [bbox for bbox in bboxes if bbox]
            heights = [bbox[3] - bbox[1] for bbox in valid]
            bottoms = [bbox[3] for bbox in valid]
            energies = _motion_energy(crops)
            result.append({
                "cellIndex": row * columns + column, "crop": list(box),
                "foregroundFrames": len(valid),
                "visibleHeightMin": min(heights) if heights else None,
                "visibleHeightMax": max(heights) if heights else None,
                "visibleHeightMedian": float(np.median(heights)) if heights else None,
                "foregroundBottomMin": min(bottoms) if bottoms else None,
                "foregroundBottomMax": max(bottoms) if bottoms else None,
                "motionEnergyMean": round(float(np.mean(energies)), 6),
                "motionEnergyMax": round(float(np.max(energies)), 6),
                "motionEnergy": energies,
                "roughForegroundBboxes": bboxes,
                "note": "Diagnostics only; key full frames before production cell crops.",
            })
    return result


def _contact_sheet(frames: list[Image.Image], timestamps: list[float], output: Path, sample_count: int) -> list[int]:
    indices = _sample_indices(len(frames), sample_count)
    columns = min(4, len(indices))
    rows = math.ceil(len(indices) / columns)
    thumb_width = 445
    thumb_height = round(frames[0].height * thumb_width / frames[0].width)
    sheet = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + 24)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for slot, index in enumerate(indices):
        thumb = frames[index].resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        x = (slot % columns) * thumb_width; y = (slot // columns) * (thumb_height + 24)
        sheet.paste(thumb, (x, y))
        draw.text((x + 6, y + thumb_height + 4), f"f{index:03d}  t={timestamps[index]:.3f}s", fill=(235, 235, 235))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return indices


def extract(args: argparse.Namespace) -> dict:
    video_hash = _sha256(args.video)
    if args.report.exists():
        existing = json.loads(args.report.read_text(encoding="utf-8"))
        if existing.get("source", {}).get("sha256") == video_hash and all(Path(item["file"]).exists() for item in existing.get("frames", [])):
            return {"ok": True, "state": "already_extracted", "videoSha256": video_hash,
                    "frameCount": len(existing["frames"]), "report": str(args.report)}
        return {"ok": False, "state": "output_conflict", "errors": ["report_or_frames_do_not_match_source"]}
    if args.reuse_pts_report:
        prior = json.loads(args.reuse_pts_report.read_text(encoding="utf-8"))
        if prior.get("source", {}).get("sha256") != video_hash:
            return {"ok": False, "state": "source_mismatch", "errors": ["reuse_report_video_hash_mismatch"]}
        paths = [Path(item["file"]) for item in prior.get("frames", [])]
        pts = [{"sourceIndex": int(item["sourceIndex"]), "pts": int(item["pts"]),
                "sourceTime": float(item["sourceTime"])} for item in prior.get("frames", [])]
        if not paths or not all(path.exists() for path in paths):
            return {"ok": False, "state": "source_missing", "errors": ["reuse_report_frame_missing"]}
    else:
        if args.frames_dir.exists() and any(args.frames_dir.iterdir()):
            return {"ok": False, "state": "output_conflict", "errors": ["frames_directory_not_empty"]}
        args.frames_dir.mkdir(parents=True, exist_ok=True)
        pattern = args.frames_dir / "frame-%06d.png"
        command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "info", "-i", str(args.video),
                   "-vf", "showinfo", "-fps_mode", "passthrough", "-start_number", "1", str(pattern)]
        process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if process.returncode:
            return {"ok": False, "state": "ffmpeg_failed", "errors": ["frame_extraction_failed"]}
        paths = sorted(args.frames_dir.glob("frame-*.png"))
        pts = parse_showinfo(process.stderr)
    if not paths or len(paths) != len(pts):
        return {"ok": False, "state": "pts_mismatch", "frameFiles": len(paths), "ptsRecords": len(pts),
                "errors": ["every_frame_requires_source_pts"]}
    images = [Image.open(path).convert("RGB") for path in paths]
    timestamps = [item["sourceTime"] for item in pts]
    energies = _motion_energy(images)
    contact_indices = _contact_sheet(images, timestamps, args.contact_sheet, args.samples)
    cells = _cell_metrics(images, args.columns, args.rows)
    report = {
        "schemaVersion": 1,
        "source": {"file": str(args.video), "sha256": video_hash, "bytes": args.video.stat().st_size},
        "probe": _probe(args.video),
        "extraction": {"mode": "all_provider_frames_pts_passthrough", "frameCount": len(paths),
                       "contactSheet": str(args.contact_sheet), "contactFrameIndices": contact_indices,
                       "motionEnergyMean": round(float(np.mean(energies)), 6),
                       "motionEnergyMax": round(float(np.max(energies)), 6),
                       "nearFrozenTransitionCount": sum(1 for value in energies[1:] if value < args.frozen_threshold),
                       "frozenThreshold": args.frozen_threshold},
        "cells": cells,
        "frames": [{"file": str(path), **pts[index], "motionEnergy": energies[index],
                    "sha256": _sha256(path)} for index, path in enumerate(paths)],
        "qa": {"status": "pending_visual_action_boundary_and_chroma_review",
               "productionCropReady": False, "canonicalRegistrationReady": False},
    }
    _atomic_json(args.report, report)
    return {"ok": True, "state": "extracted_pending_qa", "videoSha256": video_hash,
            "frameCount": len(paths), "durationSeconds": report["probe"]["durationSeconds"],
            "sourceFps": report["probe"]["fps"], "nearFrozenTransitionCount": report["extraction"]["nearFrozenTransitionCount"],
            "contactSheet": str(args.contact_sheet), "report": str(args.report)}


def self_test() -> None:
    parsed = parse_showinfo("[Parsed_showinfo] n:   0 pts:      0 pts_time:0 pos: 1\n[Parsed_showinfo] n:1 pts:512 pts_time:0.0416667")
    assert parsed == [{"sourceIndex": 0, "pts": 0, "sourceTime": 0.0},
                      {"sourceIndex": 1, "pts": 512, "sourceTime": 0.0416667}]
    assert _sample_indices(97, 12)[0] == 0 and _sample_indices(97, 12)[-1] == 96
    test = Image.new("RGB", (80, 80), (0, 255, 0)); ImageDraw.Draw(test).rectangle((20, 18, 59, 64), fill=(40, 30, 25))
    assert _green_foreground_bbox(test) == [20, 18, 60, 64]
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "report.json"; _atomic_json(path, {"ok": True})
        assert json.loads(path.read_text(encoding="utf-8"))["ok"]
    print("extract_video_frames self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path, nargs="?")
    parser.add_argument("--frames-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--contact-sheet", type=Path)
    parser.add_argument("--columns", type=int, default=1)
    parser.add_argument("--rows", type=int, default=1)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--frozen-threshold", type=float, default=0.2)
    parser.add_argument("--reuse-pts-report", type=Path,
                        help="Reuse already extracted frames and PTS from a matching prior report for deterministic re-analysis")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if any(value is None for value in (args.video, args.frames_dir, args.report, args.contact_sheet)):
        parser.error("video, frames-dir, report and contact-sheet are required")
    if args.columns < 1 or args.rows < 1 or args.samples < 2:
        parser.error("columns/rows must be positive and samples must be at least 2")
    result = extract(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
