#!/usr/bin/env python3
"""Export a structurally approved SpriteFlux pixel sequence through local Aseprite.

Aseprite remains an optional, user-provided tool. This adapter never downloads,
bundles, or redistributes Aseprite and never performs chroma keying or matting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


ASEPRITE_SOURCE = "https://github.com/aseprite/aseprite"
ASEPRITE_EULA = "https://github.com/aseprite/aseprite/blob/main/EULA.txt"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _resolve_existing(path_text: str, report: Path) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    cwd_candidate = (Path.cwd() / candidate).resolve()
    if cwd_candidate.is_file():
        return cwd_candidate
    report_candidate = (report.parent / candidate).resolve()
    if report_candidate.is_file():
        return report_candidate
    raise ValueError(f"Referenced frame does not exist: {path_text}")


def _resolve_aseprite(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    environment = os.environ.get("ASEPRITE_EXE")
    if environment:
        candidates.append(Path(environment))
    command = shutil.which("aseprite") or shutil.which("aseprite.exe")
    if command:
        candidates.append(Path(command))
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.is_file():
            return resolved
    raise ValueError(
        "Aseprite executable not found. Pass --aseprite, set ASEPRITE_EXE, "
        "or add a legally installed/local personal build to PATH."
    )


def _write_gpl(path: Path, palette: list[list[int]]) -> None:
    if not 1 <= len(palette) <= 255:
        raise ValueError("Opaque shared palette must contain 1..255 colours")
    lines = [
        "GIMP Palette",
        "Name: SpriteFlux fixed shared sequence palette",
        "Columns: 8",
        "# Index 0 is reserved for transparency",
        "0 0 0 Transparent",
    ]
    for index, colour in enumerate(palette, 1):
        if len(colour) != 3 or any(not 0 <= int(channel) <= 255 for channel in colour):
            raise ValueError(f"Invalid RGB palette entry at {index - 1}")
        lines.append(f"{int(colour[0])} {int(colour[1])} {int(colour[2])} C{index:03d}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _tool_version(executable: Path) -> str:
    completed = subprocess.run(
        [str(executable), "--version"],
        cwd=executable.parent,
        capture_output=True,
        text=True,
    )
    text = (completed.stdout + "\n" + completed.stderr).strip()
    return text.splitlines()[0] if text else "unknown"


def export(args: argparse.Namespace) -> dict:
    build_report = args.build_report.resolve()
    audit_report = args.audit_report.resolve()
    lua_script = args.lua_script.resolve()
    output_dir = args.output_dir.resolve()
    report_path = args.report.resolve()
    aseprite = _resolve_aseprite(args.aseprite)
    build = json.loads(build_report.read_text(encoding="utf-8"))
    audit = json.loads(audit_report.read_text(encoding="utf-8"))

    if audit.get("qa", {}).get("status") != "pass":
        raise ValueError("Shared-palette sequence audit must pass before Aseprite export")
    if not build.get("policy", {}).get("sharedPaletteAcrossSequence"):
        raise ValueError("Build report does not declare one shared sequence palette")
    if build.get("policy", {}).get("dither") != "none":
        raise ValueError("Aseprite production export currently requires a non-dithered source")
    if output_dir.exists():
        raise ValueError("Output directory already exists")
    if not lua_script.is_file():
        raise ValueError("Bundled Aseprite Lua adapter is missing")

    palette = build.get("palette")
    frame_entries = build.get("frames", [])
    if not isinstance(palette, list) or not frame_entries:
        raise ValueError("Build report palette/frames are missing")
    sources = [_resolve_existing(frame["file"], build_report) for frame in frame_entries]
    first = Image.open(sources[0]).convert("RGBA")
    canvas = first.size
    for source in sources:
        image = Image.open(source).convert("RGBA")
        if image.size != canvas:
            raise ValueError("All source frames must share one fixed canvas")

    output_dir.mkdir(parents=True)
    beauty_dir = output_dir / "beauty"
    beauty_dir.mkdir()
    palette_file = output_dir / "shared-palette.gpl"
    _write_gpl(palette_file, palette)

    # Aseprite's sequence loader detects contiguous numbered PNGs. Copy the
    # approved inputs into an isolated deterministic staging directory so the
    # Lua adapter never depends on project-specific filenames.
    staging = output_dir / "input-rgba"
    staging.mkdir()
    for index, source in enumerate(sources):
        shutil.copyfile(source, staging / f"frame-{index:04d}.png")

    command = [
        str(aseprite), "-b",
        "--script-param", f"inputDir={staging.as_posix()}",
        "--script-param", f"outputDir={output_dir.as_posix()}",
        "--script-param", f"paletteFile={palette_file.as_posix()}",
        "--script-param", f"frameCount={len(sources)}",
        "--script-param", f"canvasWidth={canvas[0]}",
        "--script-param", f"canvasHeight={canvas[1]}",
        "--script-param", f"artFps={args.art_fps}",
        "--script", str(lua_script),
    ]
    completed = subprocess.run(command, cwd=aseprite.parent, capture_output=True, text=True)
    if completed.returncode != 0:
        diagnostic = (completed.stdout + "\n" + completed.stderr).strip()
        raise RuntimeError(f"Aseprite export failed with exit {completed.returncode}: {diagnostic}")

    outputs = sorted(beauty_dir.glob("frame-*.png"))
    if len(outputs) != len(sources):
        raise ValueError("Aseprite did not export the complete frame sequence")
    expected_palette = {tuple(map(int, colour)) for colour in palette}
    frame_reports = []
    shared_palette_bytes: bytes | None = None
    all_indexed = True
    all_alpha_equal = True
    all_rgba_equal = True
    all_palette_equal = True
    transparent_indices: set[int] = set()
    used_opaque_indices: set[int] = set()
    for index, (source, output) in enumerate(zip(sources, outputs)):
        original = np.asarray(Image.open(source).convert("RGBA"))
        indexed = Image.open(output)
        all_indexed &= indexed.mode == "P"
        transparency = indexed.info.get("transparency")
        if isinstance(transparency, int):
            transparent_indices.add(transparency)
        palette_bytes = bytes(indexed.getpalette() or [])
        if shared_palette_bytes is None:
            shared_palette_bytes = palette_bytes
        else:
            all_palette_equal &= palette_bytes == shared_palette_bytes
        indices = np.asarray(indexed)
        if isinstance(transparency, int):
            used_opaque_indices.update(int(value) for value in np.unique(indices) if int(value) != transparency)
        converted = np.asarray(indexed.convert("RGBA"))
        alpha_equal = bool(np.array_equal(original[:, :, 3], converted[:, :, 3]))
        rgba_equal = bool(np.array_equal(original, converted))
        all_alpha_equal &= alpha_equal
        all_rgba_equal &= rgba_equal
        opaque_colours = {
            tuple(map(int, colour))
            for colour in np.unique(converted[converted[:, :, 3] >= 128, :3].reshape(-1, 3), axis=0)
        }
        if not opaque_colours.issubset(expected_palette):
            raise ValueError(f"Frame {index} contains colours outside the approved shared palette")
        frame_reports.append({
            "index": index,
            "source": str(source),
            "file": str(output),
            "sha256": _sha256(output),
            "indexedPng": indexed.mode == "P",
            "transparentIndex": transparency,
            "alphaExact": alpha_equal,
            "rgbaExact": rgba_equal,
        })

    errors = []
    if not all_indexed:
        errors.append("non_indexed_png_output")
    if transparent_indices != {0}:
        errors.append("transparent_index_not_zero")
    if not all_palette_equal:
        errors.append("palette_differs_between_frames")
    if not all_alpha_equal:
        errors.append("alpha_changed_during_aseprite_export")
    if not all_rgba_equal:
        errors.append("rgba_changed_during_aseprite_export")
    aseprite_file = output_dir / "sequence.aseprite"
    if not aseprite_file.is_file():
        errors.append("aseprite_project_missing")

    result = {
        "schemaVersion": 1,
        "source": {"buildReport": str(build_report), "auditReport": str(audit_report)},
        "tool": {
            "name": "Aseprite",
            "version": _tool_version(aseprite),
            "executableSha256": _sha256(aseprite),
            "source": ASEPRITE_SOURCE,
            "license": ASEPRITE_EULA,
            "distribution": "user_provided_local_tool_not_bundled",
        },
        "policy": {
            "responsibility": "indexed_export_only_after_spriteflux_matte_registration_palette_qa",
            "paletteSource": "spriteflux_shared_palette_build_report",
            "dither": "none",
            "transparentIndex": 0,
            "perFramePaletteForbidden": True,
        },
        "summary": {
            "frameCount": len(outputs),
            "canvas": list(canvas),
            "sharedOpaquePaletteEntries": len(palette),
            "usedOpaquePaletteIndices": len(used_opaque_indices),
            "compressedPngBytes": sum(path.stat().st_size for path in outputs),
            "decodedRgbaBytes": canvas[0] * canvas[1] * 4 * len(outputs),
            "asepriteProjectBytes": aseprite_file.stat().st_size if aseprite_file.is_file() else 0,
            "indexedPngPass": all_indexed,
            "sharedPalettePass": all_palette_equal,
            "alphaExactPass": all_alpha_equal,
            "rgbaExactPass": all_rgba_equal,
        },
        "frames": frame_reports,
        "qa": {"status": "pass" if not errors else "failed", "errors": errors},
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        palette = [[80, 60, 70], [180, 120, 90]]
        target = root / "palette.gpl"
        _write_gpl(target, palette)
        text = target.read_text(encoding="utf-8")
        assert "0 0 0 Transparent" in text and "180 120 90 C002" in text
        try:
            _write_gpl(root / "bad.gpl", [[300, 0, 0]])
            raise AssertionError("invalid palette unexpectedly accepted")
        except ValueError:
            pass
    print("export_aseprite_indexed_sequence self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-report", type=Path)
    parser.add_argument("--audit-report", type=Path)
    parser.add_argument("--aseprite", type=Path)
    parser.add_argument("--lua-script", type=Path, default=Path(__file__).with_name("aseprite_index_sequence.lua"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--art-fps", type=float, default=24.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if None in (args.build_report, args.audit_report, args.output_dir, args.report):
        parser.error("build-report, audit-report, output-dir, and report are required")
    try:
        result = export(args)
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        raise SystemExit(2)
    print(json.dumps({"ok": result["qa"]["status"] == "pass", **result["summary"], "errors": result["qa"]["errors"]}, indent=2))
    raise SystemExit(0 if result["qa"]["status"] == "pass" else 2)


if __name__ == "__main__":
    main()
