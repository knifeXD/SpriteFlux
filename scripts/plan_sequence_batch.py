from __future__ import annotations

import argparse
import json
import math


def repeat_plan(min_duration: float, action_duration: float, gap: float, repeats: int | None) -> dict:
    if min_duration <= 0 or action_duration <= 0 or gap < 0:
        raise ValueError("durations must be positive and gap cannot be negative")
    capacity = max(1, math.floor((min_duration + gap) / (action_duration + gap)))
    count = min(capacity, repeats) if repeats else min(capacity, 4)
    windows = []
    cursor = 0.0
    for index in range(count):
        end = cursor + action_duration
        windows.append({"take": index, "start": round(cursor, 4), "end": round(end, 4)})
        cursor = end + gap
    return {
        "mode": "repeat",
        "clipDuration": min_duration,
        "actionDuration": action_duration,
        "gap": gap,
        "capacity": capacity,
        "plannedTakes": count,
        "windows": windows,
        "unusedTail": round(max(0.0, min_duration - (cursor - gap)), 4),
    }


def grid_plan(
    width: int,
    height: int,
    rows: int,
    cols: int,
    target_character_height: int,
    occupancy: float,
    oversample: float,
    minimum_source_height: int,
) -> dict:
    if min(width, height, rows, cols, target_character_height) <= 0:
        raise ValueError("dimensions and counts must be positive")
    if not 0 < occupancy <= 1 or oversample < 1:
        raise ValueError("occupancy must be (0,1] and oversample must be >= 1")
    cell_width = width / cols
    cell_height = height / rows
    expected = cell_height * occupancy
    required = max(target_character_height * oversample, minimum_source_height)
    passes = expected >= required
    max_rows = max(1, math.floor(height * occupancy / required))
    return {
        "mode": "grid",
        "output": [width, height],
        "grid": [cols, rows],
        "cells": rows * cols,
        "cellSize": [round(cell_width, 2), round(cell_height, 2)],
        "expectedSourceCharacterHeight": round(expected, 2),
        "requiredSourceCharacterHeight": round(required, 2),
        "targetCharacterHeight": target_character_height,
        "oversample": oversample,
        "passesPixelBudget": passes,
        "recommendation": "use-grid" if passes else "reduce-rows-or-use-sequential-packing",
        "maxRowsAtCurrentWidthIndependent": max_rows,
    }


def self_test() -> None:
    repeat = repeat_plan(4.0, 0.8, 0.3, None)
    assert repeat["plannedTakes"] == 3
    assert repeat["windows"][2] == {"take": 2, "start": 2.2, "end": 3.0}
    good = grid_plan(1280, 720, 2, 2, 64, 0.75, 3.0, 128)
    assert good["passesPixelBudget"] is True
    bad = grid_plan(1280, 720, 4, 4, 96, 0.75, 3.0, 128)
    assert bad["passesPixelBudget"] is False
    print("plan_sequence_batch self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan repeated-take or low-pixel grid video generation")
    parser.add_argument("--mode", choices=("repeat", "grid"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--provider-min-duration", type=float, default=4.0)
    parser.add_argument("--action-duration", type=float, default=0.8)
    parser.add_argument("--gap", type=float, default=0.3)
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--cols", type=int, default=2)
    parser.add_argument("--target-character-height", type=int, default=64)
    parser.add_argument("--occupancy", type=float, default=0.75)
    parser.add_argument("--oversample", type=float, default=3.0)
    parser.add_argument("--minimum-source-height", type=int, default=128)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.mode:
        parser.error("--mode is required unless --self-test is used")
    if args.mode == "repeat":
        result = repeat_plan(args.provider_min_duration, args.action_duration, args.gap, args.repeats)
    else:
        result = grid_plan(
            args.width,
            args.height,
            args.rows,
            args.cols,
            args.target_character_height,
            args.occupancy,
            args.oversample,
            args.minimum_source_height,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
