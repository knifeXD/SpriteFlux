#!/usr/bin/env python3
"""Create an auditable contiguous PTS window from an extraction report."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path


def slice_report(source: dict, start: int, end: int) -> dict:
    frames = source.get("frames", [])
    if not isinstance(frames, list) or not frames:
        raise ValueError("source report has no frames")
    if start < 0 or end < start:
        raise ValueError("invalid inclusive source-index window")
    selected = [item for item in frames if start <= int(item.get("sourceIndex", -1)) <= end]
    expected = list(range(start, end + 1))
    actual = [int(item.get("sourceIndex", -1)) for item in selected]
    if actual != expected:
        raise ValueError("source-index window is missing, duplicated, or unordered")
    pts = [int(item["pts"]) for item in selected]
    times = [float(item["sourceTime"]) for item in selected]
    if any(b <= a for a, b in zip(pts, pts[1:])) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("PTS and source times must increase strictly")
    probe = dict(source.get("probe", {}))
    fps = float(probe.get("fps", 0.0))
    if fps <= 0:
        raise ValueError("source FPS missing or invalid")
    return {
        "schemaVersion": 1,
        "source": dict(source.get("source", {})),
        "probe": probe,
        "slice": {
            "mode": "contiguous_source_index_pts_window",
            "startSourceIndex": start,
            "endSourceIndexInclusive": end,
            "frameCount": len(selected),
            "firstPts": pts[0],
            "lastPts": pts[-1],
            "startTimeSeconds": times[0],
            "endTimeSeconds": times[-1],
            "durationSecondsAtSourceFps": len(selected) / fps,
        },
        "frames": selected,
        "qa": {
            "status": "sliced_pending_downstream_qa",
            "sourceIndicesContiguous": True,
            "ptsStrictlyIncreasing": True,
            "sourceTimesStrictlyIncreasing": True,
        },
    }


def write_report(source_path: Path, output_path: Path, start: int, end: int) -> dict:
    result = slice_report(json.loads(source_path.read_text(encoding="utf-8")), start, end)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output_path.exists() and output_path.read_text(encoding="utf-8") == payload:
        return {"ok": True, "state": "already_sliced", "frameCount": len(result["frames"])}
    output_path.write_text(payload, encoding="utf-8")
    return {"ok": True, "state": "sliced", "frameCount": len(result["frames"])}


def self_test() -> None:
    fixture = {
        "source": {"sha256": "fixture"},
        "probe": {"fps": 24.0},
        "frames": [
            {"file": f"frame-{index:06d}.png", "sourceIndex": index, "pts": index * 512,
             "sourceTime": index / 24.0, "sha256": str(index)}
            for index in range(6)
        ],
    }
    sliced = slice_report(fixture, 1, 4)
    assert sliced["slice"]["frameCount"] == 4
    assert sliced["slice"]["firstPts"] == 512 and sliced["slice"]["lastPts"] == 2048
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw); source = root / "source.json"; output = root / "slice.json"
        source.write_text(json.dumps(fixture), encoding="utf-8")
        assert write_report(source, output, 1, 4)["state"] == "sliced"
        assert write_report(source, output, 1, 4)["state"] == "already_sliced"
    broken = dict(fixture); broken["frames"] = fixture["frames"][:2] + fixture["frames"][3:]
    try:
        slice_report(broken, 1, 4)
        raise AssertionError("missing frame was not rejected")
    except ValueError:
        pass
    print("slice_extraction_report self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-report", type=Path)
    parser.add_argument("--output-report", type=Path)
    parser.add_argument("--start-source-index", type=int)
    parser.add_argument("--end-source-index-inclusive", type=int)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if None in (args.source_report, args.output_report, args.start_source_index, args.end_source_index_inclusive):
        parser.error("source-report, output-report and inclusive source-index window are required")
    print(json.dumps(write_report(args.source_report, args.output_report, args.start_source_index,
                                  args.end_source_index_inclusive), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
