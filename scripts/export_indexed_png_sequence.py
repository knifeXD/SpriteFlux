#!/usr/bin/env python3
"""Encode an approved shared-palette RGBA sequence as exact Indexed PNG."""

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


def _resolve(path_text: str, report: Path) -> Path:
    path = Path(path_text)
    for candidate in (path, Path.cwd() / path, report.parent / path):
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise ValueError(f"missing frame: {path_text}")


def run(build_report: Path, audit_report: Path, output_dir: Path, report_path: Path) -> dict:
    build = json.loads(build_report.read_text(encoding="utf-8"))
    audit = json.loads(audit_report.read_text(encoding="utf-8"))
    if audit.get("qa", {}).get("status") != "pass":
        raise ValueError("shared-palette audit must pass before Indexed export")
    if output_dir.exists():
        raise ValueError("output directory already exists")
    palette = [tuple(map(int, colour)) for colour in build.get("palette", [])]
    if not 1 <= len(palette) <= 255:
        raise ValueError("shared opaque palette must contain 1..255 colours")
    lookup = {colour: index + 1 for index, colour in enumerate(palette)}
    png_palette = [0, 0, 0]
    for colour in palette:
        png_palette.extend(colour)
    png_palette.extend([0] * (768 - len(png_palette)))
    output_dir.mkdir(parents=True)
    frames = []
    total_bytes = 0
    canvas = None
    for index, item in enumerate(build.get("frames", [])):
        source = _resolve(item["file"], build_report)
        rgba = np.asarray(Image.open(source).convert("RGBA"))
        canvas = rgba.shape[1], rgba.shape[0]
        indices = np.zeros(rgba.shape[:2], dtype=np.uint8)
        opaque = rgba[:, :, 3] >= 128
        for colour in np.unique(rgba[opaque, :3].reshape(-1, 3), axis=0):
            key = tuple(map(int, colour))
            if key not in lookup:
                raise ValueError(f"frame {index} contains colour outside shared palette: {key}")
            matches = opaque & np.all(rgba[:, :, :3] == colour, axis=2)
            indices[matches] = lookup[key]
        image = Image.fromarray(indices, "P")
        image.putpalette(png_palette)
        output = output_dir / f"frame-{index:04d}.png"
        image.save(output, optimize=True, transparency=0)
        roundtrip = np.asarray(Image.open(output).convert("RGBA"))
        if not np.array_equal(roundtrip, rgba):
            raise ValueError(f"frame {index} Indexed round-trip changed approved RGBA")
        total_bytes += output.stat().st_size
        frames.append({"index": index, "source": str(source), "file": str(output), "sha256": _sha(output)})
    result = {
        "schemaVersion": 1,
        "source": {"buildReport": str(build_report), "auditReport": str(audit_report)},
        "policy": {
            "backend": "spriteflux_native_indexed_png",
            "sharedPaletteAcrossSequence": True,
            "transparentIndex": 0,
            "dither": "none",
            "rgbaExactRoundTrip": True,
        },
        "palette": [[*colour] for colour in palette],
        "summary": {
            "frameCount": len(frames),
            "canvas": list(canvas) if canvas else None,
            "opaquePaletteEntries": len(palette),
            "compressedBytes": total_bytes,
            "decodedRgbaBytes": canvas[0] * canvas[1] * 4 * len(frames) if canvas else 0,
        },
        "frames": frames,
        "qa": {"status": "pass", "errors": []},
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = root / "source.png"
        array = np.zeros((4, 4, 4), dtype=np.uint8)
        array[1:3, 1:3] = (80, 60, 70, 255)
        Image.fromarray(array, "RGBA").save(source)
        build = root / "build.json"
        build.write_text(json.dumps({"palette": [[80, 60, 70]], "frames": [{"file": str(source)}]}), encoding="utf-8")
        audit = root / "audit.json"
        audit.write_text(json.dumps({"qa": {"status": "pass"}}), encoding="utf-8")
        result = run(build, audit, root / "out", root / "report.json")
        with Image.open(result["frames"][0]["file"]) as exported:
            assert exported.mode == "P" and exported.info.get("transparency") == 0
    print("export_indexed_png_sequence self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-report", type=Path)
    parser.add_argument("--audit-report", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if None in (args.build_report, args.audit_report, args.output_dir, args.report):
        parser.error("build-report, audit-report, output-dir, and report are required")
    try:
        result = run(args.build_report, args.audit_report, args.output_dir, args.report)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        raise SystemExit(2)
    print(json.dumps({"ok": True, **result["summary"]}, indent=2))


if __name__ == "__main__":
    main()
