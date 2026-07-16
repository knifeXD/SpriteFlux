#!/usr/bin/env python3
"""Create one Seedance task with write-ahead idempotency and private receipts."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from preflight_billable_task import preflight

CREATE_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def build_provider_request(request_path: Path) -> tuple[dict, dict]:
    spec = json.loads(request_path.read_text(encoding="utf-8"))
    content = [{"type": "text", "text": spec["prompt"]}]
    reference_hashes = []
    for raw in spec["referencePaths"]:
        path = (request_path.parent / raw).resolve()
        reference_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        content.append({"type": "image_url", "image_url": {"url": _data_uri(path)}, "role": "reference_image"})
    body = {
        "model": spec["model"], "content": content, "resolution": spec["resolution"],
        "ratio": spec["ratio"], "duration": int(spec["durationSeconds"]),
        "generate_audio": bool(spec["generateAudio"]), "watermark": bool(spec["watermark"]),
        "return_last_frame": bool(spec.get("returnLastFrame", False)),
    }
    safe = {
        "model": body["model"], "resolution": body["resolution"], "ratio": body["ratio"],
        "duration": body["duration"], "generate_audio": body["generate_audio"],
        "watermark": body["watermark"], "return_last_frame": body["return_last_frame"],
        "promptSha256": hashlib.sha256(spec["prompt"].encode("utf-8")).hexdigest(),
        "referenceSha256": reference_hashes,
    }
    return body, safe


def submit(args: argparse.Namespace) -> dict:
    gate = preflight(args.plan, args.ledger, args.price_lock, args.request, args.receipt_dir, args.credential_env)
    if not gate["ok"]:
        return {"ok": False, "state": "preflight_rejected", "errors": gate["errors"]}
    task_key = gate["taskKey"]
    intent_path = args.receipt_dir / f"{task_key}.intent.json"
    submitted_path = args.receipt_dir / f"{task_key}.submitted.json"
    args.receipt_dir.mkdir(parents=True, exist_ok=True)
    intent = {
        "schemaVersion": 1, "taskKey": task_key, "state": "submitting",
        "requestFingerprint": gate["requestFingerprint"], "estimatedTokens": gate["estimatedTokens"],
        "estimatedRmb": gate["estimatedRmb"], "isRetry": gate["isRetry"],
        "retryOfTaskKey": gate["retryOfTaskKey"], "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    try:
        with intent_path.open("x", encoding="utf-8") as stream:
            json.dump(intent, stream, ensure_ascii=False, indent=2)
    except FileExistsError:
        return {"ok": False, "state": "duplicate_blocked", "errors": ["submission_intent_already_exists"]}
    body, safe_request = build_provider_request(args.request)
    provider_request = urllib.request.Request(
        args.endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get(args.credential_env, "").strip()},
    )
    try:
        with urllib.request.urlopen(provider_request, timeout=args.timeout_seconds) as response:
            response_body, status_code = response.read().decode("utf-8"), int(response.status)
    except urllib.error.HTTPError as error:
        response_body, status_code = error.read().decode("utf-8", errors="replace"), int(error.code)
        _atomic_json(intent_path, {**intent, "state": "create_failed", "httpStatus": status_code, "errorBody": response_body[:4000]})
        return {"ok": False, "state": "create_failed", "httpStatus": status_code, "errors": ["provider_http_error"]}
    except Exception as error:
        _atomic_json(intent_path, {**intent, "state": "create_uncertain", "errorType": type(error).__name__})
        return {"ok": False, "state": "create_uncertain", "errors": [type(error).__name__]}
    try:
        provider_response = json.loads(response_body)
    except json.JSONDecodeError:
        _atomic_json(intent_path, {**intent, "state": "create_uncertain", "httpStatus": status_code, "errorType": "invalid_json_response"})
        return {"ok": False, "state": "create_uncertain", "errors": ["invalid_json_response"]}
    task_id = str(provider_response.get("id", ""))
    if not task_id:
        _atomic_json(intent_path, {**intent, "state": "create_uncertain", "httpStatus": status_code, "response": provider_response})
        return {"ok": False, "state": "create_uncertain", "errors": ["missing_provider_task_id"]}
    submitted_at = dt.datetime.now(dt.timezone.utc).isoformat()
    task_hash = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
    submitted = {**intent, "state": "submitted", "httpStatus": status_code, "taskId": task_id,
                 "taskIdSha256": task_hash, "safeRequest": safe_request,
                 "providerResponse": provider_response, "submittedAt": submitted_at}
    _atomic_json(submitted_path, submitted)
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    ledger.setdefault("tasks", {})[task_key] = {
        "state": "submitted", "taskId": task_id, "taskIdSha256": task_hash,
        "requestFingerprint": gate["requestFingerprint"], "estimatedTokens": gate["estimatedTokens"],
        "estimatedRmb": gate["estimatedRmb"], "isRetry": gate["isRetry"],
        "retryOfTaskKey": gate["retryOfTaskKey"], "submittedAt": submitted_at,
    }
    ledger["estimatedCommittedRmb"] = round(float(ledger.get("estimatedCommittedRmb", 0)) + gate["estimatedRmb"], 6)
    ledger["paidTaskCount"] = int(ledger.get("paidTaskCount", 0)) + 1
    if gate["isRetry"]:
        ledger["paidRetryCount"] = int(ledger.get("paidRetryCount", 0)) + 1
    ledger["lastUpdatedAt"] = submitted_at
    _atomic_json(args.ledger, ledger)
    intent_path.unlink(missing_ok=True)
    return {"ok": True, "state": "submitted", "taskKey": task_key, "taskIdStored": True,
            "taskIdSha256": task_hash, "estimatedRmb": gate["estimatedRmb"],
            "projectedCommittedRmb": gate["projectedCommittedRmb"], "isRetry": gate["isRetry"]}


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        (root / "ref.png").write_bytes(b"png")
        request = root / "request.json"
        request.write_text(json.dumps({"model": "m", "prompt": "p", "referencePaths": ["ref.png"],
            "resolution": "480p", "ratio": "4:3", "durationSeconds": 4,
            "generateAudio": False, "watermark": False, "returnLastFrame": True}), encoding="utf-8")
        body, safe = build_provider_request(request)
        assert body["content"][1]["role"] == "reference_image"
        assert body["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
        assert "promptSha256" in safe and "text" not in safe
    print("submit_seedance_task self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("plan", "ledger", "price-lock", "request", "receipt-dir"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--credential-env", default="ARK_API_KEY")
    parser.add_argument("--endpoint", default=CREATE_ENDPOINT)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if any(value is None for value in (args.plan, args.ledger, args.price_lock, args.request, args.receipt_dir)):
        parser.error("plan, ledger, price-lock, request and receipt-dir are required")
    result = submit(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
