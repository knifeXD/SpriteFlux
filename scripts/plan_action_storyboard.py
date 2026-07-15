#!/usr/bin/env python3
"""Plan action motion envelopes and render simple preflight SVG storyboards."""

from __future__ import annotations

import argparse
import html
import json
import math
import tempfile
from pathlib import Path


def round_up(value: float, multiple: int = 16) -> int:
    return int(math.ceil(value / multiple) * multiple)


def pose_box(root: tuple[float, float], body: dict, reach: list[float]) -> tuple[float, float, float, float]:
    x, y = root
    half_width = float(body["width"]) / 2
    body_box = (x - half_width, y - float(body["height"]), x + half_width, y)
    left, up, right, down = map(float, reach)
    reach_box = (x - left, y - up, x + right, y + down)
    return (
        min(body_box[0], reach_box[0]),
        min(body_box[1], reach_box[1]),
        max(body_box[2], reach_box[2]),
        max(body_box[3], reach_box[3]),
    )


def union_box(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def plan_action(config: dict, action: dict) -> dict:
    canvas = tuple(config.get("canvas", [128, 128]))
    canonical_root = tuple(config.get("root", [64, 112]))
    body = config.get("body", {"width": 36, "height": 70})
    padding_ratio = float(config.get("paddingRatio", 0.25))
    oversample = float(config.get("oversample", 3))
    boxes = []
    roots = []
    for pose in action["poses"]:
        offset = pose.get("root", [0, 0])
        root = (canonical_root[0] + float(offset[0]), canonical_root[1] + float(offset[1]))
        roots.append(root)
        boxes.append(pose_box(root, body, pose.get("reach", [body["width"] / 2, body["height"], body["width"] / 2, 0])))
    raw = union_box(boxes)
    padding = math.ceil(float(body["height"]) * padding_ratio)
    padded = (raw[0] - padding, raw[1] - padding, raw[2] + padding, raw[3] + padding)
    required = [round_up(padded[2] - padded[0]), round_up(padded[3] - padded[1])]
    source_required = [math.ceil(required[0] * oversample), math.ceil(required[1] * oversample)]
    fits = padded[0] >= 0 and padded[1] >= 0 and padded[2] <= canvas[0] and padded[3] <= canvas[1]
    return {
        "name": action["name"],
        "loop": bool(action.get("loop", False)),
        "facing": action.get("facing", "right"),
        "rawEnvelope": [round(value, 2) for value in raw],
        "paddingPx": padding,
        "paddedEnvelope": [round(value, 2) for value in padded],
        "requiredFinalCanvas": required,
        "oversample": oversample,
        "requiredSourceCell": source_required,
        "fitsCanonicalCanvas": fits,
        "roots": [[round(x, 2), round(y, 2)] for x, y in roots],
        "poseBoxes": [[round(value, 2) for value in box] for box in boxes],
    }


def svg_storyboard(config: dict, action: dict, report: dict) -> str:
    canvas_w, canvas_h = config.get("canvas", [128, 128])
    canonical_root = config.get("root", [64, 112])
    body = config.get("body", {"width": 36, "height": 70})
    poses = action["poses"]
    tile_w, tile_h, label_h = 176, 176, 28
    width, height = tile_w * len(poses), tile_h + label_h + 42
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#101827"/>',
        f'<text x="12" y="20" fill="#eaf2ff" font-family="sans-serif" font-size="14">{html.escape(action["name"])} · required {report["requiredFinalCanvas"][0]}×{report["requiredFinalCanvas"][1]} · {"FIT" if report["fitsCanonicalCanvas"] else "EXPAND"}</text>',
    ]
    scale = min((tile_w - 24) / canvas_w, (tile_h - 24) / canvas_h)
    offset_y = 34
    previous = None
    for index, (pose, box, root) in enumerate(zip(poses, report["poseBoxes"], report["roots"])):
        ox = index * tile_w + 12
        oy = offset_y + 8
        parts.append(f'<rect x="{ox}" y="{oy}" width="{canvas_w * scale:.1f}" height="{canvas_h * scale:.1f}" fill="#14243a" stroke="#38506f"/>')
        ground_y = oy + canonical_root[1] * scale
        parts.append(f'<line x1="{ox}" y1="{ground_y:.1f}" x2="{ox + canvas_w * scale:.1f}" y2="{ground_y:.1f}" stroke="#5ee4d8" stroke-opacity=".55"/>')
        bx1, by1, bx2, by2 = box
        parts.append(f'<rect x="{ox + bx1 * scale:.1f}" y="{oy + by1 * scale:.1f}" width="{(bx2 - bx1) * scale:.1f}" height="{(by2 - by1) * scale:.1f}" fill="none" stroke="#ffc857" stroke-dasharray="4 3"/>')
        rx, ry = root
        body_x = ox + (rx - body["width"] / 2) * scale
        body_y = oy + (ry - body["height"]) * scale
        parts.append(f'<rect x="{body_x:.1f}" y="{body_y:.1f}" width="{body["width"] * scale:.1f}" height="{body["height"] * scale:.1f}" rx="8" fill="#d75a55" stroke="#ffe1ba"/>')
        parts.append(f'<circle cx="{ox + rx * scale:.1f}" cy="{oy + ry * scale:.1f}" r="3.5" fill="#59e1d8"/>')
        if previous is not None:
            px, py = previous
            parts.append(f'<line x1="{ox + px * scale:.1f}" y1="{oy + py * scale:.1f}" x2="{ox + rx * scale:.1f}" y2="{oy + ry * scale:.1f}" stroke="#7ab8ff" stroke-width="2" marker-end="url(#arrow)"/>')
        previous = root
        parts.append(f'<text x="{ox}" y="{offset_y + tile_h + 18}" fill="#eaf2ff" font-family="sans-serif" font-size="12">{index + 1}. {html.escape(pose.get("label", "pose"))} · root {pose.get("root", [0, 0])}</text>')
    parts.insert(1, '<defs><marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#7ab8ff"/></marker></defs>')
    parts.append('</svg>')
    return "\n".join(parts)


def run(config: dict, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for action in config["actions"]:
        report = plan_action(config, action)
        reports.append(report)
        (output / f'{action["name"]}.svg').write_text(svg_storyboard(config, action, report), encoding="utf-8")
    result = {
        "canvas": config.get("canvas", [128, 128]),
        "root": config.get("root", [64, 112]),
        "body": config.get("body", {"width": 36, "height": 70}),
        "actions": reports,
    }
    (output / "envelope-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    config = {
        "canvas": [128, 128],
        "root": [64, 112],
        "body": {"width": 36, "height": 70},
        "paddingRatio": 0.25,
        "oversample": 3,
        "actions": [{
            "name": "dodge_backward",
            "facing": "right",
            "poses": [
                {"label": "idle", "root": [0, 0], "reach": [24, 70, 28, 0]},
                {"label": "travel left", "root": [-34, -4], "reach": [30, 54, 34, 2]},
                {"label": "recover", "root": [-8, 0], "reach": [24, 70, 28, 0]},
                {"label": "idle", "root": [0, 0], "reach": [24, 70, 28, 0]},
            ],
        }],
    }
    with tempfile.TemporaryDirectory() as directory:
        result = run(config, Path(directory))
        action = result["actions"][0]
        assert action["requiredFinalCanvas"][0] >= 112
        assert action["requiredSourceCell"][0] == action["requiredFinalCanvas"][0] * 3
        assert (Path(directory) / "dodge_backward.svg").exists()
        assert (Path(directory) / "envelope-report.json").exists()
    print("plan_action_storyboard self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", nargs="?", type=Path)
    parser.add_argument("--output", type=Path, default=Path("preflight"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.plan is None:
        parser.error("plan JSON is required unless --self-test is used")
    config = json.loads(args.plan.read_text(encoding="utf-8"))
    result = run(config, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
