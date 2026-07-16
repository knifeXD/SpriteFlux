#!/usr/bin/env python3
"""Build an exact-chroma reference board while preserving source foreground pixels."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter


def _is_low_chroma(pixel: tuple[int, int, int], max_chroma: int, min_value: int) -> bool:
    return max(pixel) - min(pixel) <= max_chroma and max(pixel) >= min_value


def flood_background(image: Image.Image, max_step: int = 20, max_chroma: int = 42, min_value: int = 130) -> Image.Image:
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    background = bytearray(width * height)
    queue: collections.deque[tuple[int, int]] = collections.deque()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))
    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if background[index] or not _is_low_chroma(pixels[x, y], max_chroma, min_value):
            continue
        background[index] = 1
        current = pixels[x, y]
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height or background[ny * width + nx]:
                continue
            neighbor = pixels[nx, ny]
            if max(abs(current[channel] - neighbor[channel]) for channel in range(3)) <= max_step:
                queue.append((nx, ny))
    alpha = Image.new("L", (width, height), 255)
    alpha.putdata([0 if value else 255 for value in background])
    # One-pixel minimum filter removes residual backing fringe without regenerating foreground colour.
    alpha = alpha.filter(ImageFilter.MinFilter(3))
    _remove_large_neutral_holes(rgb, alpha)
    return alpha


def _remove_large_neutral_holes(rgb: Image.Image, alpha: Image.Image, min_area: int = 500) -> None:
    """Remove enclosed neutral backing regions without touching warm white costume fabric."""
    width, height = rgb.size
    pixels, mask = rgb.load(), alpha.load()
    visited = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if visited[index] or mask[x, y] == 0 or not _is_low_chroma(pixels[x, y], 12, 130):
                continue
            queue = collections.deque([(x, y)])
            visited[index] = 1
            component: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.popleft()
                component.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    ni = ny * width + nx
                    if visited[ni] or mask[nx, ny] == 0 or not _is_low_chroma(pixels[nx, ny], 12, 130):
                        continue
                    visited[ni] = 1
                    queue.append((nx, ny))
            if len(component) >= min_area:
                for cx, cy in component:
                    mask[cx, cy] = 0


def build_board(
    source_path: Path,
    output_path: Path,
    canvas: tuple[int, int],
    columns: int,
    target_height: int | None,
    baseline_y: int,
    chroma: tuple[int, int, int],
    integer_scale: int | None = None,
    pixel_nearest_target: bool = False,
) -> dict:
    opened = Image.open(source_path)
    source_size = opened.size
    source_rgba = opened.convert("RGBA")
    embedded_alpha = source_rgba.getchannel("A")
    if embedded_alpha.getextrema()[0] < 255:
        source = source_rgba.convert("RGB")
        alpha = embedded_alpha
        alpha_source = "embedded"
    else:
        source = opened.convert("RGB")
        alpha = flood_background(source)
        alpha_source = "border_flood"
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("foreground mask is empty")
    foreground = Image.new("RGBA", source.size)
    foreground.paste(source, mask=alpha)
    foreground = foreground.crop(bbox)
    if integer_scale is not None:
        if integer_scale < 1:
            raise ValueError("integer scale must be positive")
        scale = float(integer_scale)
        if integer_scale == 1:
            resized = foreground
            resize_filter = "none_native_pixels"
        else:
            resized = foreground.resize(
                (foreground.width * integer_scale, foreground.height * integer_scale),
                Image.Resampling.NEAREST,
            )
            resize_filter = "nearest_integer_pixel_scale"
    elif target_height is None:
        scale = 1.0
        resized = foreground
        resize_filter = "none_native_pixels"
    else:
        scale = target_height / foreground.height
        resampling = Image.Resampling.NEAREST if pixel_nearest_target else Image.Resampling.LANCZOS
        resized = foreground.resize((max(1, round(foreground.width * scale)), target_height), resampling)
        resize_filter = "nearest_pixel_target_height" if pixel_nearest_target else "lanczos_non_pixel_reference"
    board = Image.new("RGB", canvas, chroma)
    cell_width = canvas[0] / columns
    placements = []
    for column in range(columns):
        x = round((column + 0.5) * cell_width - resized.width / 2)
        y = baseline_y - resized.height
        if x < 0 or y < 0 or x + resized.width > canvas[0] or y + resized.height > canvas[1]:
            raise ValueError("subject placement exceeds reference board")
        board.paste(resized.convert("RGB"), (x, y), resized.getchannel("A"))
        placements.append({"column": column, "x": x, "y": y, "width": resized.width, "height": resized.height})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    board.save(output_path, format="PNG", optimize=True)
    exact_chroma = sum(1 for pixel in board.get_flattened_data() if pixel == chroma)
    return {
        "sourceSha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "outputSha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "canvas": list(canvas), "columns": columns, "targetHeight": target_height,
        "baselineY": baseline_y, "chroma": list(chroma), "placements": placements,
        "inputNativeSize": list(source_size), "alphaSource": alpha_source,
        "referenceScale": scale, "resizeFilter": resize_filter,
        "nativePixelReferencePreserved": target_height is None and (integer_scale is None or integer_scale == 1),
        "integerPixelScale": integer_scale,
        "sourceForegroundBounds": list(bbox),
        "exactChromaCoverage": round(exact_chroma / (canvas[0] * canvas[1]), 6),
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = Image.new("RGB", (32, 48), (230, 230, 230))
        for y in range(8, 43):
            for x in range(11, 22):
                source.putpixel((x, y), (80, 30, 20))
        source_path, output_path = root / "source.png", root / "board.png"
        source.save(source_path)
        report = build_board(source_path, output_path, (128, 64), 2, 48, 60, (0, 255, 0))
        assert report["columns"] == 2 and report["exactChromaCoverage"] > 0.5
        assert Image.open(output_path).getpixel((0, 0)) == (0, 255, 0)
        rgba = Image.new("RGBA", (20, 24), (0, 0, 0, 0))
        for y in range(3, 22):
            for x in range(6, 15):
                rgba.putpixel((x, y), (90, 40, 25, 255))
        native_source, native_output = root / "native.png", root / "native-board.png"
        rgba.save(native_source)
        native = build_board(native_source, native_output, (64, 32), 1, None, 28, (0, 255, 0), 1)
        assert native["alphaSource"] == "embedded"
        assert native["nativePixelReferencePreserved"] is True
        assert native["resizeFilter"] == "none_native_pixels"
        assert native["placements"][0]["width"] == 9 and native["placements"][0]["height"] == 19
        enlarged_output = root / "nearest-board.png"
        enlarged = build_board(native_source, enlarged_output, (64, 48), 1, None, 44, (0, 255, 0), 2)
        assert enlarged["resizeFilter"] == "nearest_integer_pixel_scale"
        assert enlarged["referenceScale"] == 2.0
    print("prepare_chroma_reference_board self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--canvas", default="1112x834")
    parser.add_argument("--columns", type=int, default=2)
    parser.add_argument("--target-height", type=int, default=600)
    parser.add_argument("--native-size", action="store_true",
                        help="preserve the approved runtime Idle foreground at 1:1 native pixels")
    parser.add_argument("--integer-scale", type=int,
                        help="enlarge a pixel reference only by this integer nearest-neighbour factor")
    parser.add_argument("--pixel-nearest-target-height", action="store_true",
                        help="fit a pixel source to --target-height with nearest-neighbour sampling")
    parser.add_argument("--baseline-y", type=int, default=760)
    parser.add_argument("--chroma", default="0,255,0")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.source is None or args.output is None:
        parser.error("source and output are required")
    canvas = tuple(int(value) for value in args.canvas.lower().split("x"))
    chroma = tuple(int(value) for value in args.chroma.split(","))
    if args.native_size and args.integer_scale not in (None, 1):
        parser.error("--native-size cannot be combined with --integer-scale greater than 1")
    target_height = None if args.native_size or args.integer_scale is not None else args.target_height
    integer_scale = 1 if args.native_size else args.integer_scale
    report = build_board(args.source, args.output, canvas, args.columns, target_height, args.baseline_y, chroma, integer_scale,
                         args.pixel_nearest_target_height)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
