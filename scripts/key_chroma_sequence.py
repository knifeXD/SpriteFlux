#!/usr/bin/env python3
"""Key a complete constant-chroma sequence with one shared video model."""

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


def _smoothstep(low: float, high: float, values: np.ndarray) -> np.ndarray:
    scaled = np.clip((values - low) / max(high - low, 1e-6), 0.0, 1.0)
    return scaled * scaled * (3.0 - 2.0 * scaled)


def _border_connected(mask: np.ndarray) -> np.ndarray:
    """Return only true regions that are connected to the image border."""
    height, width = mask.shape
    parent: list[int] = []
    touches_border: list[bool] = []
    runs: list[tuple[int, int, int, int]] = []

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        parent[right_root] = left_root
        touches_border[left_root] = touches_border[left_root] or touches_border[right_root]

    previous: list[tuple[int, int, int]] = []
    for y, row in enumerate(mask):
        transitions = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        starts = np.flatnonzero(transitions == 1)
        ends = np.flatnonzero(transitions == -1)
        current: list[tuple[int, int, int]] = []
        for start, end in zip(starts.tolist(), ends.tolist()):
            label = len(parent)
            parent.append(label)
            touches_border.append(y == 0 or y == height - 1 or start == 0 or end == width)
            current.append((start, end, label))
            runs.append((y, start, end, label))
            for previous_start, previous_end, previous_label in previous:
                if previous_end >= start - 1 and previous_start <= end + 1:
                    union(label, previous_label)
        previous = current

    connected = np.zeros(mask.shape, dtype=bool)
    for y, start, end, label in runs:
        if touches_border[find(label)]:
            connected[y, start:end] = True
    return connected


def estimate_model(frames: list[Image.Image], border: int = 12) -> dict:
    samples = []
    frame_samples: list[np.ndarray] = []
    stride = max(1, len(frames) // 24)
    for image in frames[::stride]:
        rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
        regions = (rgb[:border], rgb[-border:], rgb[:, :border], rgb[:, -border:])
        current_samples = []
        for region in regions:
            flat = region.reshape(-1, 3)
            dominant = (flat[:, 1] > flat[:, 0] + 24) & (flat[:, 1] > flat[:, 2] + 24)
            selected = flat[dominant]
            samples.append(selected)
            current_samples.append(selected)
        if current_samples:
            frame_values = np.concatenate(current_samples, axis=0)
            if len(frame_values):
                frame_samples.append(frame_values)
    values = np.concatenate(samples, axis=0)
    if len(values) < 100:
        raise ValueError("insufficient_green_dominant_border_samples")
    key = np.median(values, axis=0)
    distances = np.linalg.norm(values.astype(np.float32) - key.astype(np.float32), axis=1)
    excess = values[:, 1] - np.maximum(values[:, 0], values[:, 2])
    low_quantile = float(np.percentile(excess, 1))
    alpha_low = max(18.0, min(55.0, low_quantile * 0.25))
    alpha_high = max(alpha_low + 25.0, min(150.0, low_quantile * 0.68))
    distance_p50 = float(np.percentile(distances, 50))
    distance_p95 = float(np.percentile(distances, 95))
    distance_p99 = float(np.percentile(distances, 99))
    distance_low = max(3.0, min(18.0, distance_p50 * 1.5 + 2.0))
    distance_high = max(distance_low + 18.0, min(96.0, distance_p99 * 1.35 + 12.0))
    frame_medians = [np.median(frame.astype(np.float32), axis=0) for frame in frame_samples]
    temporal_distances = [float(np.linalg.norm(median - key)) for median in frame_medians]
    return {
        "keyRgb": [round(float(value), 4) for value in key],
        "borderSampleCount": int(len(values)),
        "borderGreenExcessP01": round(low_quantile, 4),
        "borderGreenExcessMedian": round(float(np.median(excess)), 4),
        "alphaGreenExcessLow": round(alpha_low, 4),
        "alphaGreenExcessHigh": round(alpha_high, 4),
        "keyDistanceP50": round(distance_p50, 4),
        "keyDistanceP95": round(distance_p95, 4),
        "keyDistanceP99": round(distance_p99, 4),
        "alphaKeyDistanceLow": round(distance_low, 4),
        "alphaKeyDistanceHigh": round(distance_high, 4),
        "borderTemporalDriftMax": round(max(temporal_distances, default=0.0), 4),
        "sampledFrameCount": len(frame_samples),
        "borderPixels": border,
    }


def key_frame(image: Image.Image, model: dict, no_intentional_green: bool) -> tuple[Image.Image, dict]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    key = np.asarray(model["keyRgb"], dtype=np.float32)
    distance = np.linalg.norm(rgb - key, axis=2)
    distance_background = 1.0 - _smoothstep(
        model["alphaKeyDistanceLow"], model["alphaKeyDistanceHigh"], distance
    )
    excess = rgb[:, :, 1] - np.maximum(rgb[:, :, 0], rgb[:, :, 2])
    green_confidence = _smoothstep(model["alphaGreenExcessLow"], model["alphaGreenExcessHigh"], excess)
    brightness_confidence = _smoothstep(24.0, 96.0, rgb[:, :, 1])
    chroma_background = green_confidence * brightness_confidence
    background_confidence = np.maximum(distance_background, chroma_background)
    background_candidate = background_confidence >= 0.02
    exterior_background = _border_connected(background_candidate)
    protected_interior = background_candidate & ~exterior_background
    effective_background = np.where(exterior_background, background_confidence, 0.0)
    alpha = np.clip(1.0 - effective_background, 0.0, 1.0)
    interior_alpha_holes = (alpha < 0.5) & ~_border_connected(alpha < 0.5)
    alpha[interior_alpha_holes] = 1.0
    alpha[alpha < 0.02] = 0.0
    alpha[alpha > 0.98] = 1.0
    recovered = rgb.copy()
    mixed = (alpha > 0.02) & (alpha < 0.98)
    if np.any(mixed):
        divisor = np.maximum(alpha[mixed, None], 0.05)
        recovered[mixed] = (rgb[mixed] - (1.0 - alpha[mixed, None]) * key) / divisor
        recovered[mixed] = np.clip(recovered[mixed], 0.0, 255.0)
        if no_intentional_green:
            cap = np.maximum(recovered[mixed, 0], recovered[mixed, 2]) + 12.0
            recovered[mixed, 1] = np.minimum(recovered[mixed, 1], cap)
    protected_colour_mask = (protected_interior | interior_alpha_holes) & (alpha > 0.5)
    repaired_protected = _repair_protected_foreground_colour(recovered, alpha, protected_colour_mask)
    if no_intentional_green:
        retained = alpha > 0.5
        current_excess = recovered[:, :, 1] - np.maximum(recovered[:, :, 0], recovered[:, :, 2])
        contaminated = retained & (current_excess > 6.0)
        if np.any(contaminated):
            values = recovered[contaminated]
            original_value = np.max(values, axis=1)
            values[:, 1] = np.maximum(values[:, 0], values[:, 2]) + 6.0
            repaired_value = np.maximum(np.max(values, axis=1), 1.0)
            values *= (original_value / repaired_value)[:, None]
            values[:, 1] = np.minimum(values[:, 1], np.maximum(values[:, 0], values[:, 2]) + 6.0)
            recovered[contaminated] = np.clip(values, 0.0, 255.0)
    recovered[alpha == 0.0] = 0.0
    rgba = np.dstack((np.rint(recovered).astype(np.uint8), np.rint(alpha * 255.0).astype(np.uint8)))
    retained = alpha > 0.5
    retained_excess = recovered[:, :, 1] - np.maximum(recovered[:, :, 0], recovered[:, :, 2])
    metrics = {
        "transparentPixels": int(np.count_nonzero(alpha == 0.0)),
        "semiTransparentPixels": int(np.count_nonzero((alpha > 0.0) & (alpha < 1.0))),
        "opaquePixels": int(np.count_nonzero(alpha == 1.0)),
        "protectedInteriorCandidatePixels": int(np.count_nonzero(protected_interior)),
        "protectedInteriorAlphaPixels": int(np.count_nonzero(interior_alpha_holes)),
        "protectedInteriorColourRecoveredPixels": repaired_protected,
        "unprotectedInteriorTransparentPixels": int(np.count_nonzero(
            (alpha < 0.5) & ~_border_connected(alpha < 0.5)
        )),
        "retainedGreenExcessAbove12": int(np.count_nonzero(retained & (retained_excess > 12.0))),
        "retainedGreenExcessAbove6": int(np.count_nonzero(retained & (retained_excess > 6.01))),
    }
    return Image.fromarray(rgba, "RGBA"), metrics


def _repair_protected_foreground_colour(rgb: np.ndarray, alpha: np.ndarray, target: np.ndarray) -> int:
    unresolved = target.copy()
    valid = (alpha > 0.5) & ~target
    repaired = 0
    height, width = target.shape
    for _wave in range(max(height, width)):
        ys, xs = np.nonzero(unresolved)
        if len(xs) == 0:
            break
        updates: list[tuple[int, int, np.ndarray]] = []
        for y, x in zip(ys.tolist(), xs.tolist()):
            y0, y1 = max(0, y - 1), min(height, y + 2)
            x0, x1 = max(0, x - 1), min(width, x + 2)
            support = valid[y0:y1, x0:x1]
            if np.any(support):
                values = rgb[y0:y1, x0:x1][support]
                updates.append((y, x, np.median(values, axis=0)))
        if not updates:
            break
        for y, x, value in updates:
            rgb[y, x] = value
            unresolved[y, x] = False
            valid[y, x] = True
            repaired += 1
    return repaired


def _largest_component_bbox(mask: np.ndarray) -> list[int] | None:
    parent: list[int] = []
    runs: list[tuple[int, int, int, int]] = []

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]; value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    previous: list[tuple[int, int, int]] = []
    for y, row in enumerate(mask):
        transitions = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        starts, ends = np.flatnonzero(transitions == 1), np.flatnonzero(transitions == -1)
        current = []
        for start, end in zip(starts.tolist(), ends.tolist()):
            label = len(parent); parent.append(label); current.append((start, end, label)); runs.append((y, start, end, label))
            for previous_start, previous_end, previous_label in previous:
                if previous_end >= start - 1 and previous_start <= end:
                    union(label, previous_label)
        previous = current
    if not runs:
        return None
    components: dict[int, list[int]] = {}
    for y, start, end, label in runs:
        root = find(label); value = components.setdefault(root, [start, y, end, y + 1, 0])
        value[0] = min(value[0], start); value[1] = min(value[1], y)
        value[2] = max(value[2], end); value[3] = max(value[3], y + 1); value[4] += end - start
    return max(components.values(), key=lambda value: value[4])[:4]


def _cell_bboxes(keyed: Image.Image, columns: int, rows: int) -> list[list[int] | None]:
    alpha = np.asarray(keyed.getchannel("A"))
    height, width = alpha.shape
    result = []
    for row in range(rows):
        for column in range(columns):
            left, top = round(column * width / columns), round(row * height / rows)
            right, bottom = round((column + 1) * width / columns), round((row + 1) * height / rows)
            bbox = _largest_component_bbox(alpha[top:bottom, left:right] >= 128)
            result.append(bbox)
    return result


def _checker(size: tuple[int, int], tile: int = 24) -> Image.Image:
    width, height = size
    y, x = np.indices((height, width))
    pattern = ((x // tile + y // tile) % 2)[:, :, None]
    colors = np.array([[52, 52, 52], [188, 188, 188]], dtype=np.uint8)
    return Image.fromarray(colors[pattern[:, :, 0]], "RGB")


def _qa_sheets(frames: list[Image.Image], timestamps: list[float], output_dir: Path, samples: int) -> dict[str, str]:
    indices = sorted({round(index * (len(frames) - 1) / (samples - 1)) for index in range(samples)})
    columns = min(4, len(indices)); rows = math.ceil(len(indices) / columns)
    thumb_width = 445; thumb_height = round(frames[0].height * thumb_width / frames[0].width)
    backgrounds = {"dark": (18, 18, 22), "light": (235, 235, 235), "checker": None}
    outputs = {}
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, color in backgrounds.items():
        sheet = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + 24)), (24, 24, 24))
        draw = ImageDraw.Draw(sheet)
        for slot, index in enumerate(indices):
            foreground = frames[index].resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            background = (_checker((thumb_width, thumb_height), 16) if color is None
                          else Image.new("RGB", (thumb_width, thumb_height), color))
            background.paste(foreground, (0, 0), foreground.getchannel("A"))
            x = (slot % columns) * thumb_width; y = (slot // columns) * (thumb_height + 24)
            sheet.paste(background, (x, y)); draw.text((x + 6, y + thumb_height + 4),
                f"f{index:03d} t={timestamps[index]:.3f}s", fill=(235, 235, 235))
        path = output_dir / f"keyed-{name}.png"; sheet.save(path); outputs[name] = str(path)
    return outputs


def process(args: argparse.Namespace) -> dict:
    extraction = json.loads(args.extraction_report.read_text(encoding="utf-8"))
    source_hash = extraction["source"]["sha256"]
    frame_items = extraction["frames"]
    source_paths = [Path(item["file"]) for item in frame_items]
    if not source_paths or not all(path.exists() for path in source_paths):
        return {"ok": False, "state": "source_missing", "errors": ["extracted_frame_missing"]}
    if args.report.exists():
        existing = json.loads(args.report.read_text(encoding="utf-8"))
        outputs = [Path(item["file"]) for item in existing.get("frames", [])]
        if existing.get("source", {}).get("videoSha256") == source_hash and outputs and all(path.exists() for path in outputs):
            return {"ok": True, "state": "already_keyed", "frameCount": len(outputs), "report": str(args.report)}
        return {"ok": False, "state": "output_conflict", "errors": ["existing_key_report_mismatch"]}
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        return {"ok": False, "state": "output_conflict", "errors": ["keyed_output_directory_not_empty"]}
    sources = [Image.open(path).convert("RGB") for path in source_paths]
    model = estimate_model(sources, args.border)
    background_errors = []
    if model["keyDistanceP95"] > args.max_border_distance_p95:
        background_errors.append("background_border_spatial_variation_exceeds_limit")
    if model["borderTemporalDriftMax"] > args.max_border_temporal_drift:
        background_errors.append("background_border_temporal_drift_exceeds_limit")
    if background_errors:
        return {"ok": False, "state": "background_chroma_contract_failed",
                "errors": background_errors, "model": model,
                "limits": {"maxBorderDistanceP95": args.max_border_distance_p95,
                           "maxBorderTemporalDrift": args.max_border_temporal_drift}}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    keyed_frames = []; output_items = []; totals = {"transparentPixels": 0, "semiTransparentPixels": 0,
                                                     "opaquePixels": 0,
                                                     "protectedInteriorCandidatePixels": 0,
                                                     "protectedInteriorAlphaPixels": 0,
                                                     "unprotectedInteriorTransparentPixels": 0,
                                                     "retainedGreenExcessAbove12": 0,
                                                     "retainedGreenExcessAbove6": 0}
    cell_bboxes: list[list[list[int] | None]] = [[] for _ in range(args.columns * args.rows)]
    for index, source in enumerate(sources):
        keyed, metrics = key_frame(source, model, args.no_intentional_green_material)
        output = args.output_dir / f"frame-{index + 1:06d}.png"; keyed.save(output, optimize=True)
        keyed_frames.append(keyed)
        for key in totals: totals[key] += metrics[key]
        bboxes = _cell_bboxes(keyed, args.columns, args.rows)
        for cell, bbox in enumerate(bboxes): cell_bboxes[cell].append(bbox)
        output_items.append({"file": str(output), "sha256": _sha256(output),
                             "sourceIndex": frame_items[index]["sourceIndex"],
                             "pts": frame_items[index]["pts"], "sourceTime": frame_items[index]["sourceTime"],
                             "metrics": metrics, "cellBboxes": bboxes})
    cell_metrics = []
    for index, bboxes in enumerate(cell_bboxes):
        valid = [bbox for bbox in bboxes if bbox]
        heights = [bbox[3] - bbox[1] for bbox in valid]; bottoms = [bbox[3] for bbox in valid]
        cell_metrics.append({"cellIndex": index, "validFrames": len(valid),
                             "visibleHeightMin": min(heights), "visibleHeightMax": max(heights),
                             "visibleHeightMedian": float(np.median(heights)),
                             "foregroundBottomMin": min(bottoms), "foregroundBottomMax": max(bottoms)})
    timestamps = [float(item["sourceTime"]) for item in frame_items]
    qa_sheets = _qa_sheets(keyed_frames, timestamps, args.qa_dir, args.samples)
    report = {"schemaVersion": 1, "source": {"videoSha256": source_hash,
              "extractionReport": str(args.extraction_report), "frameCount": len(sources)},
              "contract": {"oneModelForCompleteSequence": True, "keyBeforeCellCrop": True,
              "noIntentionalGreenMaterial": args.no_intentional_green_material,
              "backgroundUniformityFailClosed": True,
              "maxBorderDistanceP95": args.max_border_distance_p95,
              "maxBorderTemporalDrift": args.max_border_temporal_drift,
              "retainedGreenSanitizer": "preserve_value_cap_green_excess_to_6_only_when_no_green_is_declared"},
              "model": model, "totals": totals, "cells": cell_metrics,
              "qaSheets": qa_sheets, "frames": output_items,
              "qa": {"status": "pending_dark_light_checker_visual_review",
                     "canonicalRegistrationReady": False}}
    _atomic_json(args.report, report)
    return {"ok": True, "state": "keyed_pending_visual_qa", "frameCount": len(sources),
            "model": model, "totals": totals, "cells": cell_metrics,
            "qaSheets": qa_sheets, "report": str(args.report)}


def self_test() -> None:
    frames = []
    for shift in (0, 3, -2):
        array = np.zeros((80, 100, 3), dtype=np.uint8); array[:] = (4, 246 + shift, 8)
        array[20:70, 35:65] = (120, 70, 45); frames.append(Image.fromarray(array, "RGB"))
    model = estimate_model(frames, 8)
    assert model["keyDistanceP95"] < 8 and model["borderTemporalDriftMax"] < 8
    keyed, metrics = key_frame(frames[0], model, True)
    alpha = np.asarray(keyed.getchannel("A")); assert alpha[0, 0] == 0 and alpha[40, 50] == 255
    assert metrics["opaquePixels"] > 0 and _cell_bboxes(keyed, 1, 1)[0] == [35, 20, 65, 70]
    enclosed = np.zeros((80, 100, 3), dtype=np.uint8); enclosed[:] = (4, 246, 8)
    enclosed[15:70, 25:75] = (110, 65, 45)
    enclosed[35:50, 42:58] = (4, 246, 8)
    enclosed_image, enclosed_metrics = key_frame(Image.fromarray(enclosed, "RGB"), model, True)
    enclosed_alpha = np.asarray(enclosed_image.getchannel("A"))
    assert enclosed_alpha[40, 50] == 255
    assert enclosed_metrics["protectedInteriorCandidatePixels"] >= 15 * 16
    assert enclosed_metrics["protectedInteriorColourRecoveredPixels"] >= 15 * 16
    assert np.max(np.asarray(enclosed_image.convert("RGBA"))[40, 50, :3]) > 20
    assert enclosed_metrics["unprotectedInteriorTransparentPixels"] == 0
    open_gap = enclosed.copy(); open_gap[15:43, 49:52] = (4, 246, 8)
    open_image, _ = key_frame(Image.fromarray(open_gap, "RGB"), model, True)
    assert np.asarray(open_image.getchannel("A"))[40, 50] == 0
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "report.json"; _atomic_json(path, {"ok": True})
        assert json.loads(path.read_text(encoding="utf-8"))["ok"]
    drifted = [Image.new("RGB", (100, 80), (4, 246, 8)), Image.new("RGB", (100, 80), (80, 150, 90))]
    try:
        drift_model = estimate_model(drifted, 8)
        assert drift_model["borderTemporalDriftMax"] > 20
    except ValueError:
        pass
    print("key_chroma_sequence self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction-report", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--qa-dir", type=Path)
    parser.add_argument("--columns", type=int, default=1); parser.add_argument("--rows", type=int, default=1)
    parser.add_argument("--border", type=int, default=12); parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--max-border-distance-p95", type=float, default=45.0)
    parser.add_argument("--max-border-temporal-drift", type=float, default=24.0)
    parser.add_argument("--no-intentional-green-material", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test: self_test(); return
    if any(value is None for value in (args.extraction_report, args.output_dir, args.report, args.qa_dir)):
        parser.error("extraction-report, output-dir, report and qa-dir are required")
    if not args.no_intentional_green_material:
        parser.error("declare --no-intentional-green-material or provide a future semantic protection mask")
    result = process(args); print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
