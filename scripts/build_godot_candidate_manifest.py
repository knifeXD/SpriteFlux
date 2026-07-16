#!/usr/bin/env python3
"""Copy verified channels and build one Godot sprite-sequence candidate manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: dict) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError("manifest_output_conflict")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8"); temporary.replace(path)


def _copy(source: Path, destination: Path) -> None:
    if destination.exists():
        if _sha(source) != _sha(destination): raise ValueError(f"resource_output_conflict:{destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, destination)


def build(args: argparse.Namespace) -> dict:
    report = json.loads(args.channel_report.read_text(encoding="utf-8"))
    actions = [item for item in report["actions"] if item["actionId"] == args.action_id]
    if len(actions) != 1: raise ValueError("action_id_not_unique")
    action = actions[0]; canonical = report["canonical"]
    required_qa = ("binaryAlphaPass", "interiorTopologyPass", "channelTransformParityPass", "areaContinuityPass")
    if not all(report["qa"].get(key) for key in required_qa):
        raise ValueError("channel_report_not_eligible")
    hold = max(1, round(args.logic_fps / float(action["artFps"])))
    frames = []
    for index, item in enumerate(action["frames"]):
        paths = {}
        channels = ("beauty", "mask") if args.runtime_normal else ("beauty", "normal", "mask")
        for channel in channels:
            source = Path(item[channel]); destination = args.resource_dir / channel / f"frame-{index:04d}.png"
            _copy(source, destination); paths[channel] = f"{args.resource_prefix}/{channel}/frame-{index:04d}.png"
        frame = {"frame_id": f"{args.action_id}.{index:04d}",
                       "beauty_path": paths["beauty"],
                       "mask_path": paths["mask"], "utility_path": paths["mask"],
                       "pts_seconds": item["sourceTime"], "hold_logic_frames": hold,
                       "root_offset_px": [0, 0]}
        if not args.runtime_normal: frame["normal_path"] = paths["normal"]
        frames.append(frame)
    manifest = {"schemaVersion": 1, "manifestId": args.manifest_id, "characterId": args.character_id,
                "availability": "available", "canonical": {
                    "base_standing_height_px": canonical["baseStandingHeightPx"],
                    "target_standing_height_px": canonical["baseStandingHeightPx"],
                    "canvas": canonical["canvas"], "root": canonical["root"],
                    "baseline_y": canonical["baselineY"], "safe_margin_px": args.safe_margin,
                    "world_pixel_size": args.world_pixel_size, "texture_filter": canonical["textureFilter"],
                    "mipmaps": canonical["mipmaps"],
                    "normal_generation": "runtime_luminance_gradient" if args.runtime_normal else "authored_texture"}, "sequences": [{
                        "sequence_id": args.sequence_id, "kind": args.kind, "availability": "available",
                        "logic_fps": args.logic_fps, "art_fps": action["artFps"], "frames": frames,
                        "segments": [{"segment_id": "full", "start_frame": 0,
                                      "end_frame": len(frames) - 1, "loop": args.loop}]}]}
    _write_json(args.output_manifest, manifest)
    return {"ok": True, "frameCount": len(frames), "channelFileCount": len(frames) * (2 if args.runtime_normal else 3),
            "holdLogicFrames": hold, "manifest": str(args.output_manifest), "resourceDir": str(args.resource_dir)}


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw); source = root / "source.bin"; source.write_bytes(b"sprite")
        destination = root / "nested" / "copy.bin"; _copy(source, destination); _copy(source, destination)
        assert _sha(source) == _sha(destination)
        manifest = root / "manifest.json"; _write_json(manifest, {"ok": True}); _write_json(manifest, {"ok": True})
        assert json.loads(manifest.read_text())["ok"]
        assert argparse.Namespace(loop=True).loop and not argparse.Namespace(loop=False).loop
    print("build_godot_candidate_manifest self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--channel-report", type=Path)
    parser.add_argument("--action-id"); parser.add_argument("--sequence-id"); parser.add_argument("--manifest-id")
    parser.add_argument("--character-id"); parser.add_argument("--output-manifest", type=Path)
    parser.add_argument("--resource-dir", type=Path); parser.add_argument("--resource-prefix")
    parser.add_argument("--kind", default="stationary"); parser.add_argument("--logic-fps", type=int, default=60)
    parser.add_argument("--safe-margin", type=int, default=51)
    parser.add_argument("--world-pixel-size", type=float, default=0.00703125)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--runtime-normal", action="store_true")
    parser.add_argument("--self-test", action="store_true"); args = parser.parse_args()
    if args.self_test: self_test(); return
    required = (args.channel_report, args.action_id, args.sequence_id, args.manifest_id, args.character_id,
                args.output_manifest, args.resource_dir, args.resource_prefix)
    if any(value is None for value in required): parser.error("all manifest inputs are required")
    try: result = build(args)
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False)); raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
