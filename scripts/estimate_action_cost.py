#!/usr/bin/env python3
"""Estimate or reconcile video-generation cost per requested/readable/accepted action."""

from __future__ import annotations

import argparse
import json
import math


MEASURED_TOKENS_PER_4S = {"480p": 39891, "720p": 87850}


def estimate(
    resolution: str,
    clips: int,
    actions_per_clip: int,
    acceptance_rate: float,
    price_per_million: float,
    seconds: float = 4.0,
    actual_tokens: int | None = None,
    accepted_actions: int | None = None,
    readable_actions: int | None = None,
) -> dict:
    if resolution not in MEASURED_TOKENS_PER_4S:
        raise ValueError("resolution must be 480p or 720p")
    if clips <= 0 or actions_per_clip <= 0 or seconds <= 0 or price_per_million < 0:
        raise ValueError("clips, actions, seconds must be positive and price cannot be negative")
    if not 0 < acceptance_rate <= 1:
        raise ValueError("acceptance rate must be in (0, 1]")
    requested = clips * actions_per_clip
    predicted_tokens_per_clip = round(MEASURED_TOKENS_PER_4S[resolution] * seconds / 4.0)
    estimated_tokens = predicted_tokens_per_clip * clips
    tokens = actual_tokens if actual_tokens is not None else estimated_tokens
    source = "actual-usage" if actual_tokens is not None else "measured-sample-scaled-by-duration"
    total_rmb = tokens / 1_000_000 * price_per_million
    expected_accepted = accepted_actions if accepted_actions is not None else requested * acceptance_rate
    readable = readable_actions if readable_actions is not None else requested
    return {
        "resolution": resolution,
        "clips": clips,
        "secondsPerClip": seconds,
        "requestedDistinctActions": requested,
        "tokenSource": source,
        "tokens": tokens,
        "pricePerMillionRmb": price_per_million,
        "rmb": round(total_rmb, 6),
        "readableDistinctActions": readable,
        "acceptedActions": accepted_actions,
        "expectedAcceptedActions": round(expected_accepted, 4),
        "rmbPerRequestedAction": round(total_rmb / requested, 6),
        "rmbPerReadableAction": round(total_rmb / readable, 6) if readable else None,
        "rmbPerAcceptedAction": round(total_rmb / expected_accepted, 6) if expected_accepted else None,
        "warning": "Planning estimate only; replace with final usage tokens and current official price."
        if actual_tokens is None
        else "Uses actual usage tokens; confirm price basis at submission time.",
    }


def self_test() -> None:
    planned = estimate("480p", 2, 4, 0.625, 23.0)
    assert planned["tokens"] == 79782
    assert planned["requestedDistinctActions"] == 8
    assert planned["expectedAcceptedActions"] == 5.0
    assert math.isclose(planned["rmbPerAcceptedAction"], 0.366997, abs_tol=1e-6)
    actual = estimate("720p", 1, 8, 1.0, 23.0, actual_tokens=87850, accepted_actions=2, readable_actions=8)
    assert actual["tokenSource"] == "actual-usage"
    assert actual["rmb"] == 2.02055
    assert actual["rmbPerAcceptedAction"] == 1.010275
    print("estimate_action_cost self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate or reconcile cost per game-ready action")
    parser.add_argument("--resolution", choices=("480p", "720p"))
    parser.add_argument("--clips", type=int, default=1)
    parser.add_argument("--actions-per-clip", type=int, default=2)
    parser.add_argument("--acceptance-rate", type=float, default=1.0)
    parser.add_argument("--price-per-million", type=float, default=23.0)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--actual-tokens", type=int)
    parser.add_argument("--accepted-actions", type=int)
    parser.add_argument("--readable-actions", type=int)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.resolution:
        parser.error("--resolution is required unless --self-test is used")
    result = estimate(
        args.resolution,
        args.clips,
        args.actions_per_clip,
        args.acceptance_rate,
        args.price_per_million,
        args.seconds,
        args.actual_tokens,
        args.accepted_actions,
        args.readable_actions,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

