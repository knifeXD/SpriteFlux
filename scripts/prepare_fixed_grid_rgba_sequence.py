#!/usr/bin/env python3
"""Reduce a registered RGBA sequence onto one fixed virtual pixel grid."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resize(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0
    alpha = rgba[:, :, 3:4]
    premultiplied = rgba[:, :, :3] * alpha
    rgb = Image.fromarray(np.rint(premultiplied * 255.0).astype(np.uint8), "RGB")
    alpha_image = Image.fromarray(np.rint(alpha[:, :, 0] * 255.0).astype(np.uint8), "L")
    rgb_small = np.asarray(rgb.resize(size, Image.Resampling.BOX), dtype=np.float32) / 255.0
    alpha_small = np.asarray(alpha_image.resize(size, Image.Resampling.BOX), dtype=np.float32)[:, :, None] / 255.0
    straight = np.divide(rgb_small, np.maximum(alpha_small, 1.0 / 255.0), out=np.zeros_like(rgb_small), where=alpha_small > 0)
    result = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    result[:, :, :3] = np.rint(np.clip(straight, 0.0, 1.0) * 255.0).astype(np.uint8)
    result[:, :, 3] = np.where(alpha_small[:, :, 0] >= 0.5, 255, 0).astype(np.uint8)
    result[result[:, :, 3] == 0, :3] = 0
    return result


def run(args: argparse.Namespace) -> dict:
    paths = sorted(args.input_dir.glob("frame-*.png"))
    if not paths:
        raise ValueError("input sequence is empty")
    if args.output_dir.exists():
        raise ValueError("output directory already exists")
    args.output_dir.mkdir(parents=True)
    runtime_frames = []
    for index, source in enumerate(paths):
        array = _resize(Image.open(source), (args.canvas_width, args.canvas_height))
        output = args.output_dir / f"frame-{index:04d}.png"
        Image.fromarray(array, "RGBA").save(output, optimize=True)
        runtime_frames.append({
            "file": str(output),
            "sourceIndex": args.source_index_start + index,
            "pts": index,
            "sourceTime": index / args.art_fps,
            "sha256": _sha(output),
        })
    result = {
        "schemaVersion": 1,
        "source": {"inputDirectory": str(args.input_dir)},
        "canonical": {
            "baseStandingHeightPx": args.visible_height,
            "canvas": [args.canvas_width, args.canvas_height],
            "root": [args.root_x, args.root_y],
            "baselineY": args.baseline_y,
            "textureFilter": "nearest",
            "lossless": True,
            "mipmaps": False,
        },
        "policy": {
            "alphaAwarePremultipliedBoxResize": True,
            "binaryCoverageThreshold": 0.5,
            "fixedVirtualGrid": True,
            "perFrameBoundsNormalization": False,
        },
        "actions": [{
            "actionId": args.action_id,
            "phase": args.phase,
            "artFps": args.art_fps,
            "runtimeFrames": runtime_frames,
        }],
        "qa": {"status": "prepared_pending_contour_palette_audit"},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = root / "source"
        source.mkdir()
        image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        for y in range(2, 6):
            for x in range(2, 6):
                image.putpixel((x, y), (100, 60, 80, 255))
        image.save(source / "frame-0000.png")
        args = argparse.Namespace(
            input_dir=source, output_dir=root / "out", report=root / "report.json",
            canvas_width=4, canvas_height=4, visible_height=2, root_x=2, root_y=3,
            baseline_y=3, action_id="idle", phase="loop", art_fps=24.0, source_index_start=0,
        )
        result = run(args)
        output = np.asarray(Image.open(result["actions"][0]["runtimeFrames"][0]["file"]))
        assert set(np.unique(output[:, :, 3])).issubset({0, 255})
        assert result["policy"]["perFrameBoundsNormalization"] is False
    print("prepare_fixed_grid_rgba_sequence self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--canvas-width", type=int)
    parser.add_argument("--canvas-height", type=int)
    parser.add_argument("--visible-height", type=int)
    parser.add_argument("--root-x", type=int)
    parser.add_argument("--root-y", type=int)
    parser.add_argument("--baseline-y", type=int)
    parser.add_argument("--action-id", default="idle")
    parser.add_argument("--phase", default="loop")
    parser.add_argument("--art-fps", type=float, default=24.0)
    parser.add_argument("--source-index-start", type=int, default=0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    required = (args.input_dir, args.output_dir, args.report, args.canvas_width, args.canvas_height,
                args.visible_height, args.root_x, args.root_y, args.baseline_y)
    if any(value is None for value in required):
        parser.error("all input/output/canonical arguments are required")
    try:
        result = run(args)
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        raise SystemExit(2)
    print(json.dumps({"ok": True, "frameCount": len(result["actions"][0]["runtimeFrames"])}, indent=2))


if __name__ == "__main__":
    main()
