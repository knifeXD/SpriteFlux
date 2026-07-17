#!/usr/bin/env python3
"""Build a fixed-grid, shared-palette RGBA animation without per-frame palettes."""

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


def _alpha_aware_resize(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0
    alpha = rgba[:, :, 3:4]
    premult = rgba[:, :, :3] * alpha
    rgb_image = Image.fromarray(np.rint(premult * 255.0).astype(np.uint8), "RGB")
    alpha_image = Image.fromarray(np.rint(alpha[:, :, 0] * 255.0).astype(np.uint8), "L")
    rgb_small = np.asarray(rgb_image.resize(size, Image.Resampling.BOX), dtype=np.float32) / 255.0
    alpha_small = np.asarray(alpha_image.resize(size, Image.Resampling.BOX), dtype=np.float32)[:, :, None] / 255.0
    straight = np.divide(rgb_small, np.maximum(alpha_small, 1.0 / 255.0), out=np.zeros_like(rgb_small), where=alpha_small > 0)
    result = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    result[:, :, :3] = np.rint(np.clip(straight, 0.0, 1.0) * 255.0).astype(np.uint8)
    result[:, :, 3] = np.where(alpha_small[:, :, 0] >= 0.5, 255, 0).astype(np.uint8)
    result[result[:, :, 3] == 0, :3] = 0
    return result


def _shared_palette(frames: list[np.ndarray], colours: int, sample_limit: int = 250_000) -> np.ndarray:
    opaque = [frame[frame[:, :, 3] >= 128, :3] for frame in frames]
    pixels = np.concatenate([item for item in opaque if item.size], axis=0)
    if pixels.shape[0] > sample_limit:
        indices = np.linspace(0, pixels.shape[0] - 1, sample_limit, dtype=np.int64)
        pixels = pixels[indices]
    strip = Image.fromarray(pixels.reshape(1, -1, 3), "RGB")
    quantized = strip.quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = np.asarray(quantized.getpalette(), dtype=np.uint8).reshape(-1, 3)
    used = np.unique(np.asarray(quantized))
    return raw[used]


def _map_palette(frame: np.ndarray, palette: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    result = np.zeros_like(frame)
    mask = frame[:, :, 3] >= 128
    pixels = frame[mask, :3].astype(np.int16)
    indices = np.zeros(mask.shape, dtype=np.uint8)
    if pixels.size:
        mapped = np.empty(pixels.shape[0], dtype=np.uint8)
        chunk = 20_000
        pal = palette.astype(np.int32)
        for start in range(0, pixels.shape[0], chunk):
            sample = pixels[start:start + chunk].astype(np.int32)
            distance = np.sum((sample[:, None, :] - pal[None, :, :]) ** 2, axis=2, dtype=np.int32)
            mapped[start:start + chunk] = np.argmin(distance, axis=1).astype(np.uint8) + 1
        indices[mask] = mapped
        result[mask, :3] = palette[mapped.astype(np.int16) - 1]
        result[mask, 3] = 255
    return result, indices


def run(input_dir: Path, output_dir: Path, report_path: Path, canvas: int, colours: int) -> dict:
    paths = sorted(input_dir.glob("*.png"))
    if not paths:
        raise ValueError("input sequence is empty")
    if not 2 <= colours <= 255:
        raise ValueError("opaque colour count must be 2..255; index 0 is reserved for transparency")
    output_dir.mkdir(parents=True, exist_ok=False)
    resized = [_alpha_aware_resize(Image.open(path), (canvas, canvas)) for path in paths]
    palette = _shared_palette(resized, colours)
    frames = []
    prior_indices = None
    transition_changes = []
    total_bytes = 0
    for index, (path, frame) in enumerate(zip(paths, resized)):
        mapped, indices = _map_palette(frame, palette)
        output = output_dir / f"frame-{index:04d}.png"
        Image.fromarray(mapped, "RGBA").save(output, optimize=True)
        total_bytes += output.stat().st_size
        if prior_indices is not None:
            shared_opaque = (prior_indices > 0) & (indices > 0)
            transition_changes.append(float(np.mean(prior_indices[shared_opaque] != indices[shared_opaque])) if np.any(shared_opaque) else 0.0)
        prior_indices = indices
        frames.append({"index": index, "source": str(path), "file": str(output), "sha256": _sha(output)})
    result = {
        "schemaVersion": 1,
        "policy": {
            "alphaAwarePremultipliedBoxResize": True,
            "fixedVirtualGrid": [canvas, canvas],
            "sharedPaletteAcrossSequence": True,
            "transparentIndex": 0,
            "opaquePaletteEntries": int(palette.shape[0]),
            "dither": "none",
            "perFramePaletteForbidden": True,
        },
        "palette": [[int(v) for v in colour] for colour in palette],
        "summary": {
            "frameCount": len(frames),
            "compressedBytes": total_bytes,
            "decodedRgbaBytes": canvas * canvas * 4 * len(frames),
            "meanAdjacentSharedOpaqueIndexChangeRatio": float(np.mean(transition_changes)) if transition_changes else 0.0,
            "maxAdjacentSharedOpaqueIndexChangeRatio": float(max(transition_changes, default=0.0)),
        },
        "frames": frames,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = root / "source"
        source.mkdir()
        for index in range(3):
            image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
            for y in range(4, 12):
                for x in range(3 + index, 11 + index):
                    image.putpixel((x, y), (80 + x * 3, 40 + y * 4, 55, 255))
            image.save(source / f"frame-{index:04d}.png")
        result = run(source, root / "out", root / "report.json", 8, 8)
        assert result["policy"]["sharedPaletteAcrossSequence"]
        assert result["policy"]["transparentIndex"] == 0
        assert len(result["frames"]) == 3
        assert result["policy"]["opaquePaletteEntries"] <= 8
    print("build_shared_palette_pixel_sequence self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--canvas", type=int)
    parser.add_argument("--colours", type=int, default=64)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if None in (args.input_dir, args.output_dir, args.report, args.canvas):
        parser.error("input/output/report/canvas are required")
    try:
        result = run(args.input_dir, args.output_dir, args.report, args.canvas, args.colours)
    except (ValueError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        raise SystemExit(2)
    print(json.dumps({"ok": True, **result["summary"]}, indent=2))


if __name__ == "__main__":
    main()
