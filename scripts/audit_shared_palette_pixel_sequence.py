#!/usr/bin/env python3
"""Fail-closed structural QA for shared-palette pixel animation candidates."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def _erode(mask: np.ndarray) -> np.ndarray:
    result = mask.copy()
    padded = np.pad(mask, 1, constant_values=False)
    for y in range(3):
        for x in range(3):
            result &= padded[y:y + mask.shape[0], x:x + mask.shape[1]]
    return result


def _components(mask: np.ndarray) -> tuple[int, int]:
    seen = np.zeros_like(mask, dtype=bool)
    count = 0
    largest = 0
    height, width = mask.shape
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        count += 1
        stack = [(int(sy), int(sx))]
        seen[sy, sx] = True
        area = 0
        while stack:
            y, x = stack.pop()
            area += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        largest = max(largest, area)
    return count, largest


def _composite(array: np.ndarray, background: np.ndarray) -> np.ndarray:
    alpha = array[:, :, 3:4].astype(np.float32) / 255.0
    return np.rint(array[:, :, :3] * alpha + background * (1.0 - alpha)).astype(np.uint8)


def run(build_report: Path, output: Path, qa_sheet: Path) -> dict:
    build = json.loads(build_report.read_text(encoding="utf-8"))
    palette = np.asarray(build["palette"], dtype=np.uint8)
    arrays = [np.asarray(Image.open(frame["file"]).convert("RGBA")) for frame in build["frames"]]
    masks = [array[:, :, 3] >= 128 for array in arrays]
    heights, areas, components, largest_ratios, green = [], [], [], [], []
    used_colours: set[tuple[int, int, int]] = set()
    for array, mask in zip(arrays, masks):
        ys = np.nonzero(mask)[0]
        heights.append(int(ys.max() - ys.min() + 1) if ys.size else 0)
        area = int(mask.sum())
        areas.append(area)
        component_count, largest = _components(mask)
        components.append(component_count)
        largest_ratios.append(float(largest / area) if area else 0.0)
        band = mask & ~_erode(mask)
        rgb = array[:, :, :3].astype(np.int16)
        green.append(int(np.count_nonzero(band & ((rgb[:, :, 1] - np.maximum(rgb[:, :, 0], rgb[:, :, 2])) > 6))))
        used_colours.update(tuple(map(int, colour)) for colour in np.unique(array[mask, :3].reshape(-1, 3), axis=0))
    alpha_ious, area_deltas = [], []
    for left, right, left_area in zip(masks, masks[1:], areas):
        union = int(np.logical_or(left, right).sum())
        alpha_ious.append(float(np.logical_and(left, right).sum() / union) if union else 1.0)
        area_deltas.append(abs(int(right.sum()) - left_area) / max(left_area, 1))
    seam_union = int(np.logical_or(masks[-1], masks[0]).sum())
    seam_iou = float(np.logical_and(masks[-1], masks[0]).sum() / seam_union) if seam_union else 1.0
    errors = []
    if max(components, default=0) > 1:
        errors.append("multiple_connected_components")
    if min(largest_ratios, default=1.0) < 0.995:
        errors.append("largest_component_ratio_below_limit")
    if max(area_deltas, default=0.0) > 0.08:
        errors.append("adjacent_area_delta_above_limit")
    if min(alpha_ious, default=1.0) < 0.90:
        errors.append("adjacent_alpha_iou_below_limit")
    if sum(green) > 0:
        errors.append("contour_green_excess_present")
    if len(used_colours) > len(palette):
        errors.append("pixels_outside_shared_palette")
    if seam_iou < 0.94:
        errors.append("loop_alpha_seam_below_limit")
    result = {
        "schemaVersion": 1,
        "sourceBuildReport": str(build_report),
        "summary": {
            "frameCount": len(arrays),
            "visibleHeightMin": min(heights),
            "visibleHeightMax": max(heights),
            "opaqueAreaMin": min(areas),
            "opaqueAreaMax": max(areas),
            "minAdjacentAlphaIoU": min(alpha_ious, default=1.0),
            "maxAdjacentAreaDeltaRatio": max(area_deltas, default=0.0),
            "maxConnectedComponents": max(components, default=0),
            "minLargestComponentRatio": min(largest_ratios, default=1.0),
            "contourGreenExcessPixelsAbove6": sum(green),
            "usedOpaqueRgbColours": len(used_colours),
            "sharedPaletteEntries": len(palette),
            "loopAlphaIoU": seam_iou,
        },
        "qa": {"status": "pass" if not errors else "failed", "errors": errors},
    }
    samples = [arrays[0], arrays[len(arrays) // 2], arrays[-1]]
    h, w = samples[0].shape[:2]
    sheet = Image.new("RGB", (w * 3, h * 3 + 24), (25, 26, 31))
    checker = np.indices((h, w)).sum(axis=0) // 16 % 2
    checker_rgb = np.where(checker[:, :, None] == 0, 56, 176).astype(np.uint8)
    backgrounds = [np.full((h, w, 3), 24, np.uint8), np.full((h, w, 3), 232, np.uint8), checker_rgb]
    draw = ImageDraw.Draw(sheet)
    for column, sample in enumerate(samples):
        for row, background in enumerate(backgrounds):
            sheet.paste(Image.fromarray(_composite(sample, background), "RGB"), (column * w, 24 + row * h))
        draw.text((column * w + 6, 6), f"sample {column + 1}", fill="white")
    qa_sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(qa_sheet, optimize=True)
    result["qaSheet"] = str(qa_sheet)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        frames = []
        for index in range(3):
            array = np.zeros((16, 16, 4), dtype=np.uint8)
            array[3:13, 4:12] = (80, 60, 70, 255)
            path = root / f"f{index}.png"
            Image.fromarray(array, "RGBA").save(path)
            frames.append({"file": str(path)})
        build = root / "build.json"
        build.write_text(json.dumps({"palette": [[80, 60, 70]], "frames": frames}), encoding="utf-8")
        result = run(build, root / "audit.json", root / "qa.png")
        assert result["qa"]["status"] == "pass"
        assert result["summary"]["usedOpaqueRgbColours"] == 1
    print("audit_shared_palette_pixel_sequence self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--qa-sheet", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if None in (args.build_report, args.output, args.qa_sheet):
        parser.error("build-report/output/qa-sheet are required")
    result = run(args.build_report, args.output, args.qa_sheet)
    print(json.dumps({"ok": result["qa"]["status"] == "pass", **result["summary"], "errors": result["qa"]["errors"]}, indent=2))
    raise SystemExit(0 if result["qa"]["status"] == "pass" else 2)


if __name__ == "__main__":
    main()
