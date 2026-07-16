#!/usr/bin/env python3
"""Resume one existing Seedance task without ever creating a second task.

The provider task id and signed download URLs are private production data. This
tool stores them only in the caller-selected private receipt directory and
prints hashes/statuses instead of secret-bearing values.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TASK_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
TERMINAL_FAILURES = {"failed", "expired", "cancelled", "canceled"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _content(response: dict) -> dict:
    value = response.get("content", {})
    return value if isinstance(value, dict) else {}


def extract_artifact_urls(response: dict) -> dict[str, str]:
    content = _content(response)
    candidates = {
        "video": content.get("video_url") or response.get("video_url"),
        "last_frame": (
            content.get("last_frame_url")
            or content.get("last_frame_image_url")
            or response.get("last_frame_url")
            or response.get("last_frame_image_url")
        ),
    }
    return {key: value for key, value in candidates.items() if isinstance(value, str) and value.startswith(("http://", "https://"))}


def extract_total_tokens(response: dict) -> int | None:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        usage = _content(response).get("usage")
    if not isinstance(usage, dict):
        return None
    value = usage.get("total_tokens")
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def reconcile_usage(ledger: dict, task_key: str, total_tokens: int, rate: float, timestamp: str) -> bool:
    task = ledger["tasks"][task_key]
    if task.get("usageReconciled"):
        if int(task.get("actualUsageTokens", -1)) != total_tokens:
            raise ValueError("provider_usage_changed_after_reconciliation")
        return False
    actual_cost = round(total_tokens / 1_000_000 * rate, 6)
    estimated = float(task.get("estimatedRmb", 0))
    ledger["estimatedCommittedRmb"] = round(max(0.0, float(ledger.get("estimatedCommittedRmb", 0)) - estimated), 6)
    ledger["actualUsageTokens"] = int(ledger.get("actualUsageTokens", 0)) + total_tokens
    ledger["actualSpentRmb"] = round(float(ledger.get("actualSpentRmb", 0)) + actual_cost, 6)
    task.update({
        "usageReconciled": True,
        "actualUsageTokens": total_tokens,
        "actualRmb": actual_cost,
        "usageReconciledAt": timestamp,
    })
    ledger["lastUpdatedAt"] = timestamp
    return True


def _download(url: str, path: Path, timeout_seconds: int) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "SpriteFlux/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response, temporary.open("wb") as output:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            output.write(block)
    temporary.replace(path)
    return {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}


def resume(args: argparse.Namespace) -> dict:
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    price_lock = json.loads(args.price_lock.read_text(encoding="utf-8"))
    task = ledger.get("tasks", {}).get(args.task_key)
    if not isinstance(task, dict) or not task.get("taskId"):
        return {"ok": False, "state": "local_error", "errors": ["task_not_found_in_ledger"]}
    credential = os.environ.get(args.credential_env, "").strip()
    if not credential:
        return {"ok": False, "state": "local_error", "errors": ["credential_missing"]}
    task_id = str(task["taskId"])
    task_hash = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
    if task.get("taskIdSha256") not in (None, task_hash):
        return {"ok": False, "state": "local_error", "errors": ["task_id_hash_mismatch"]}
    timestamp = _now()
    request = urllib.request.Request(
        args.endpoint.rstrip("/") + "/" + urllib.parse.quote(task_id, safe=""),
        headers={"Authorization": "Bearer " + credential, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
            http_status = int(response.status)
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        receipt = {"schemaVersion": 1, "taskKey": args.task_key, "taskIdSha256": task_hash,
                   "state": "poll_failed", "httpStatus": int(error.code), "errorBody": error_body[:4000], "polledAt": timestamp}
        _atomic_json(args.receipt_dir / f"{args.task_key}.poll-error.json", receipt)
        return {"ok": False, "state": "poll_failed", "httpStatus": int(error.code), "taskIdSha256": task_hash,
                "errors": ["provider_http_error"]}
    except Exception as error:
        receipt = {"schemaVersion": 1, "taskKey": args.task_key, "taskIdSha256": task_hash,
                   "state": "poll_uncertain", "errorType": type(error).__name__, "polledAt": timestamp}
        _atomic_json(args.receipt_dir / f"{args.task_key}.poll-error.json", receipt)
        return {"ok": False, "state": "poll_uncertain", "taskIdSha256": task_hash, "errors": [type(error).__name__]}
    try:
        provider_response = json.loads(response_body)
    except json.JSONDecodeError:
        return {"ok": False, "state": "poll_uncertain", "taskIdSha256": task_hash, "errors": ["invalid_json_response"]}
    provider_status = str(provider_response.get("status", "unknown")).lower()
    raw_receipt = {"schemaVersion": 1, "taskKey": args.task_key, "taskIdSha256": task_hash,
                   "httpStatus": http_status, "providerStatus": provider_status,
                   "providerResponse": provider_response, "polledAt": timestamp}
    _atomic_json(args.receipt_dir / f"{args.task_key}.latest-response.json", raw_receipt)
    task["state"] = provider_status
    task["lastPolledAt"] = timestamp
    ledger["lastUpdatedAt"] = timestamp
    if provider_status != "succeeded":
        _atomic_json(args.ledger, ledger)
        state = "terminal_failure" if provider_status in TERMINAL_FAILURES else provider_status
        return {"ok": provider_status not in TERMINAL_FAILURES, "state": state,
                "providerStatus": provider_status, "taskIdSha256": task_hash}

    urls = extract_artifact_urls(provider_response)
    if "video" not in urls:
        task["state"] = "succeeded_missing_video_url"
        _atomic_json(args.ledger, ledger)
        return {"ok": False, "state": "succeeded_missing_video_url", "taskIdSha256": task_hash,
                "errors": ["missing_video_url"]}
    artifacts: dict[str, dict] = {}
    targets = {"video": args.output_dir / "provider.mp4", "last_frame": args.output_dir / "last-frame.png"}
    for key, url in urls.items():
        target = targets[key]
        artifacts[key] = ({"path": str(target), "sha256": _sha256(target), "bytes": target.stat().st_size}
                          if target.exists() else _download(url, target, args.timeout_seconds))
    total_tokens = extract_total_tokens(provider_response)
    reconciled = False
    if total_tokens is not None:
        rate = float(price_lock["noVideoInputRmbPerMillionTokens"])
        reconciled = reconcile_usage(ledger, args.task_key, total_tokens, rate, timestamp)
    task["state"] = "downloaded_pending_qa"
    task["artifacts"] = artifacts
    _atomic_json(args.ledger, ledger)
    completed = {"schemaVersion": 1, "taskKey": args.task_key, "taskIdSha256": task_hash,
                 "state": "downloaded_pending_qa", "providerStatus": provider_status,
                 "actualUsageTokens": total_tokens, "usageReconciledThisRun": reconciled,
                 "artifacts": artifacts, "completedAt": timestamp}
    _atomic_json(args.receipt_dir / f"{args.task_key}.completed.json", completed)
    return {"ok": True, "state": "downloaded_pending_qa", "taskIdSha256": task_hash,
            "actualUsageTokens": total_tokens, "actualRmb": task.get("actualRmb"),
            "usageReconciledThisRun": reconciled,
            "artifacts": {key: {"sha256": value["sha256"], "bytes": value["bytes"]} for key, value in artifacts.items()}}


def self_test() -> None:
    response = {"status": "succeeded", "content": {"video_url": "https://example.invalid/v.mp4",
                "last_frame_url": "https://example.invalid/f.png"}, "usage": {"total_tokens": 12345}}
    assert extract_artifact_urls(response) == {"video": "https://example.invalid/v.mp4", "last_frame": "https://example.invalid/f.png"}
    assert extract_total_tokens(response) == 12345
    ledger = {"estimatedCommittedRmb": 2.0, "actualSpentRmb": 0, "actualUsageTokens": 0,
              "tasks": {"task": {"estimatedRmb": 2.0}}}
    assert reconcile_usage(ledger, "task", 100000, 23.0, "time")
    assert not reconcile_usage(ledger, "task", 100000, 23.0, "time2")
    assert ledger["actualSpentRmb"] == 2.3 and ledger["actualUsageTokens"] == 100000
    safe = {"state": "running", "taskIdSha256": hashlib.sha256(b"private-id").hexdigest()}
    rendered = json.dumps(safe)
    assert "private-id" not in rendered and "http" not in rendered
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "value.json"
        _atomic_json(path, {"ok": True})
        assert json.loads(path.read_text(encoding="utf-8"))["ok"]
    print("resume_seedance_task self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--receipt-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--price-lock", type=Path)
    parser.add_argument("--task-key")
    parser.add_argument("--credential-env", default="ARK_API_KEY")
    parser.add_argument("--endpoint", default=TASK_ENDPOINT)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if any(value is None for value in (args.ledger, args.receipt_dir, args.output_dir, args.price_lock, args.task_key)):
        parser.error("ledger, receipt-dir, output-dir, price-lock and task-key are required")
    result = resume(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
