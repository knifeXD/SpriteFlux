from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def alpha_bbox(image: Image.Image) -> list[int] | None:
    alpha = np.asarray(image.getchannel("A"))
    ys, xs = np.where(alpha >= 8)
    if not len(xs):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def resolve_frame_path(manifest_path: Path, value: str, asset_root: Path | None) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    roots = [asset_root.resolve()] if asset_root else []
    roots.extend([manifest_path.parent, *manifest_path.parents])
    for root in roots:
        resolved = (root / candidate).resolve()
        if resolved.exists():
            return resolved
    return ((asset_root or manifest_path.parent) / candidate).resolve()


def validate(manifest_path: Path, asset_root: Path | None = None) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    canvas = tuple(manifest["canvas"])
    baseline = int(manifest.get("baseline", manifest["root"][1]))
    frames = manifest.get("frames", [])
    errors: list[str] = []
    warnings: list[str] = []
    reports: list[dict] = []
    bottoms: list[int] = []
    heights: list[int] = []
    total_bytes = 0

    for index, item in enumerate(frames):
        frame_value = item.get("file") or item.get("output")
        if not frame_value:
            errors.append(f"frame {index}: missing file/output path")
            continue
        path = resolve_frame_path(manifest_path, frame_value, asset_root)
        if not path.exists():
            errors.append(f"frame {index}: missing {path}")
            continue
        total_bytes += path.stat().st_size
        with Image.open(path) as source:
            if source.mode != "RGBA":
                errors.append(f"frame {index}: expected RGBA, got {source.mode}")
            image = source.convert("RGBA")
            if image.size != canvas:
                errors.append(f"frame {index}: expected canvas {canvas}, got {image.size}")
            bbox = alpha_bbox(image)
        if bbox is None:
            errors.append(f"frame {index}: empty alpha")
            continue
        bottom = bbox[3]
        height = bbox[3] - bbox[1]
        bottoms.append(bottom)
        heights.append(height)
        reports.append({"index": index, "file": str(path), "alphaBbox": bbox, "bytes": path.stat().st_size})

    if not frames:
        errors.append("manifest has no frames")
    support_foot_values = [
        int(item[key])
        for item in frames
        for key in ("supportFootFinalY", "supportFootYRuntime")
        if key in item
    ]
    if support_foot_values:
        maximum_deviation = int(manifest.get("maxBaselineDeviation", 8))
        if max(abs(value - baseline) for value in support_foot_values) > maximum_deviation:
            errors.append(
                f"support-foot positions deviate from baseline {baseline}: "
                f"{min(support_foot_values)}..{max(support_foot_values)}"
            )
    elif bottoms:
        warnings.append(
            "runtime support-foot coordinates are absent; alpha-bottom range is diagnostic only: "
            f"{min(bottoms)}..{max(bottoms)}"
        )
    if heights and "maxHeightRatio" in manifest:
        ratio = max(heights) / max(1, min(heights))
        if ratio > float(manifest["maxHeightRatio"]):
            errors.append(f"visible height ratio too large: {ratio:.3f}")

    decoded_bytes = canvas[0] * canvas[1] * 4 * len(frames)
    return {
        "status": "pass" if not errors else "fail",
        "manifest": str(manifest_path.resolve()),
        "frameCount": len(frames),
        "canvas": list(canvas),
        "runtimeCompressedBytes": total_bytes,
        "estimatedDecodedRgbaBytes": decoded_bytes,
        "errors": errors,
        "warnings": warnings,
        "frames": reports,
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        frames = root / "frames"
        frames.mkdir()
        for index in range(2):
            image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            pixels = np.asarray(image).copy()
            pixels[12:60, 24:40] = (255, 255, 255, 255)
            Image.fromarray(pixels, "RGBA").save(frames / f"{index}.png")
        manifest = {
            "canvas": [64, 64],
            "root": [32, 60],
            "baseline": 60,
            "frames": [{"file": f"frames/{index}.png"} for index in range(2)],
        }
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        report = validate(path)
        assert report["status"] == "pass", report
    print("validate_sequence self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a registered video-derived sprite sequence")
    parser.add_argument("manifest", nargs="?", type=Path)
    parser.add_argument("--asset-root", type=Path, help="Project root used to resolve project-relative frame paths")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.manifest:
        parser.error("manifest path is required unless --self-test is used")
    report = validate(args.manifest.resolve(), args.asset_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
