#!/usr/bin/env python3
"""Fail-closed billable video task preflight without exposing credentials or prompts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase.casefold() in text for phrase in phrases)


def _validate_clean_chroma_prompt(request: dict, prompt_folded: str) -> list[str]:
    if not request.get("chromaExtraction", False):
        return []
    errors: list[str] = []
    if request.get("promptContractVersion") != "clean-chroma-v2":
        errors.append("clean_chroma_prompt_contract_version_missing")
    key_rgb = request.get("keyRgb")
    if not (isinstance(key_rgb, list) and len(key_rgb) == 3 and
            all(isinstance(value, int) and 0 <= value <= 255 for value in key_rgb) and
            max(key_rgb) >= 240 and min(key_rgb) <= 15):
        errors.append("clean_chroma_key_rgb_invalid")
    semantic_groups = {
        "camera_lock": ("locked camera", "fixed camera", "锁定镜头", "固定镜头"),
        "neutral_albedo": ("neutral albedo", "albedo-reference", "中性固有色", "中性参考照明"),
        "stable_exposure": ("stable exposure", "constant exposure", "曝光稳定", "固定曝光"),
        "uniform_field": ("uniform solid", "perfectly uniform", "完全均匀纯色", "均匀纯色"),
        "no_baked_lighting": ("no rim light", "no baked", "无轮廓光", "无烘焙光影"),
        "no_detached_vfx": ("no attack arc", "no detached", "无攻击弧", "无外部特效"),
        "no_attached_aura": (
            "no fist/foot glow", "no circular or elliptical blur",
            "无拳脚发光", "无圆形或椭圆形模糊",
        ),
    }
    for name, alternatives in semantic_groups.items():
        if not _contains_any(prompt_folded, alternatives):
            errors.append(f"clean_chroma_prompt_semantic_missing:{name}")
    if isinstance(key_rgb, list) and len(key_rgb) == 3:
        hex_key = "#" + "".join(f"{value:02x}" for value in key_rgb)
        csv_key = ",".join(str(value) for value in key_rgb)
        if hex_key not in prompt_folded and csv_key not in prompt_folded:
            errors.append("clean_chroma_prompt_key_value_missing")
    if request.get("runtimeIdleReferenceRequired", False):
        reference = request.get("identityReference")
        if not isinstance(reference, dict) or reference.get("kind") != "approved_runtime_idle":
            errors.append("runtime_idle_identity_reference_missing")
        else:
            for field in ("nativeSize", "canonicalCanvas"):
                value = reference.get(field)
                if not (isinstance(value, list) and len(value) == 2 and
                        all(isinstance(item, int) and item > 0 for item in value)):
                    errors.append(f"runtime_idle_identity_reference_invalid:{field}")
            visible_height = reference.get("visibleHeightPx")
            if not isinstance(visible_height, int) or visible_height <= 0:
                errors.append("runtime_idle_identity_reference_invalid:visibleHeightPx")
    return errors


def _validate_packing(request: dict) -> list[str]:
    """Block ambiguous same-character interaction scenes before a paid call."""
    errors: list[str] = []
    subjects = request.get("simultaneousSubjects")
    mode = request.get("packingMode")
    actions = request.get("actions", [])
    if not isinstance(subjects, int) or subjects < 1:
        return ["simultaneous_subject_count_missing_or_invalid"]
    valid_modes = ("sequential_distinct_actions", "repeated_same_action", "independent_grid_distinct_actions")
    if mode not in valid_modes:
        errors.append("packing_mode_missing_or_invalid")
    if subjects > 1:
        if mode == "repeated_same_action":
            if not isinstance(actions, list) or len(actions) != 1:
                errors.append("multi_subject_requires_exactly_one_shared_action")
        elif mode == "independent_grid_distinct_actions":
            isolation = request.get("cellIsolation")
            required = ("independentAnchors", "disjointMotionEnvelopes", "noContact", "noSharedTarget", "noComplementaryRoles")
            if not isinstance(isolation, dict) or not all(isolation.get(field) is True for field in required):
                errors.append("independent_grid_isolation_contract_incomplete")
            prompt_requirements = (
                "independent animation previews", "never interact", "no shared target",
                "empty isolation corridor", "no contact",
            )
            for phrase in prompt_requirements:
                if phrase not in request.get("prompt", "").casefold():
                    errors.append(f"independent_grid_prompt_missing:{phrase}")
        else:
            errors.append("multi_subject_packing_mode_invalid")
    return errors


def preflight(
    plan_path: Path,
    ledger_path: Path,
    price_lock_path: Path,
    request_path: Path,
    receipt_dir: Path,
    credential_env: str,
    today: dt.date | None = None,
) -> dict:
    today = today or dt.date.today()
    errors: list[str] = []
    plan, ledger, price, request = map(_read, (plan_path, ledger_path, price_lock_path, request_path))
    task_key = str(request.get("taskKey", ""))
    tasks = {str(task.get("taskKey", "")): task for task in plan.get("tasks", [])}
    task = tasks.get(task_key)
    if task is None:
        errors.append("task_not_in_plan")
        task = {}
    if plan.get("characterId") != ledger.get("characterId") or plan.get("characterId") != request.get("characterId"):
        errors.append("character_identity_mismatch")
    hard_limit = float(plan.get("authorization", {}).get("hardLimit", -1))
    if hard_limit <= 0 or hard_limit != float(ledger.get("hardLimit", -2)):
        errors.append("hard_limit_mismatch")
    retry_of = str(request.get("retryOfTaskKey", "")).strip()
    is_retry = bool(retry_of)
    if is_retry:
        retry_source = tasks.get(retry_of)
        if retry_of == task_key:
            errors.append("retry_source_matches_task_key")
        if retry_source is None or retry_of not in ledger.get("tasks", {}):
            errors.append("retry_source_not_in_plan_and_ledger")
        elif not set(request.get("actions", [])).issubset(set(retry_source.get("actions", []))):
            errors.append("retry_actions_not_subset_of_source")
        maximum_retries = int(plan.get("authorization", {}).get("maximumPaidRetries", -1))
        paid_retries = int(ledger.get("paidRetryCount", 0))
        if maximum_retries < 0 or paid_retries >= maximum_retries:
            errors.append("paid_retry_limit_exhausted")
    verified_at = dt.date.fromisoformat(str(price.get("verifiedAt")))
    if (today - verified_at).days not in (0, 1):
        errors.append("official_price_lock_stale")
    if not str(price.get("officialSource", "")).startswith("https://www.volcengine.com/"):
        errors.append("price_source_not_official")
    price_per_million = float(price.get("noVideoInputRmbPerMillionTokens", -1))
    if price_per_million <= 0:
        errors.append("invalid_price_basis")
    provider = plan.get("provider", {})
    for field in ("model", "defaultResolution", "ratio", "generateAudio", "watermark"):
        expected = task.get("resolution") if field == "defaultResolution" else provider.get(field)
        actual_field = "resolution" if field == "defaultResolution" else field
        if request.get(actual_field) != expected:
            errors.append(f"request_field_mismatch:{actual_field}")
    if int(request.get("durationSeconds", -1)) != int(task.get("durationSeconds", -2)):
        errors.append("request_field_mismatch:durationSeconds")
    if request.get("actions") != task.get("actions"):
        errors.append("request_actions_mismatch")
    token_anchor = int(plan.get("costBasis", {}).get(f"measuredTokensPerFourSeconds{task.get('resolution', '')}", 0))
    estimated_tokens = round(token_anchor * float(task.get("durationSeconds", 0)) / 4.0)
    estimated_rmb = round(estimated_tokens / 1_000_000 * price_per_million, 6)
    projected = round(float(ledger.get("actualSpentRmb", 0)) + float(ledger.get("estimatedCommittedRmb", 0)) + estimated_rmb, 6)
    if token_anchor <= 0:
        errors.append("missing_measured_token_anchor")
    if projected > hard_limit:
        errors.append("projected_cumulative_cost_exceeds_hard_limit")
    if float(plan.get("costBasis", {}).get("plannedPlusReserveRmb", hard_limit + 1)) > hard_limit:
        errors.append("planned_batch_plus_reserve_exceeds_hard_limit")
    if task_key in ledger.get("tasks", {}):
        errors.append("ledger_task_already_exists")
    if receipt_dir.exists() and any(receipt_dir.glob(f"{task_key}.*.json")):
        errors.append("task_receipt_already_exists")
    credential_present = bool(os.environ.get(credential_env, "").strip())
    if not credential_present:
        errors.append("credential_unavailable")
    prompt = str(request.get("prompt", ""))
    if not prompt.strip():
        errors.append("missing_prompt")
    prompt_folded = prompt.casefold()
    for phrase in request.get("requiredPromptPhrases", []):
        if str(phrase).casefold() not in prompt_folded:
            errors.append(f"required_prompt_phrase_missing:{phrase}")
    errors.extend(_validate_clean_chroma_prompt(request, prompt_folded))
    errors.extend(_validate_packing(request))
    references = []
    for raw in request.get("referencePaths", []):
        path = (request_path.parent / str(raw)).resolve()
        if not path.is_file():
            errors.append(f"reference_missing:{raw}")
            continue
        references.append({"path": str(raw), "sha256": _hash(path), "bytes": path.stat().st_size})
    if not references:
        errors.append("no_valid_reference")
    fingerprint_payload = {
        "taskKey": task_key, "model": request.get("model"), "resolution": request.get("resolution"),
        "durationSeconds": request.get("durationSeconds"), "ratio": request.get("ratio"),
        "generateAudio": request.get("generateAudio"), "watermark": request.get("watermark"),
        "actions": request.get("actions"), "retryOfTaskKey": retry_of or None,
        "promptSha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "references": references,
    }
    fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {
        "ok": not errors, "errors": errors, "taskKey": task_key,
        "estimatedTokens": estimated_tokens, "estimatedRmb": estimated_rmb,
        "projectedCommittedRmb": projected, "hardLimitRmb": hard_limit,
        "officialPriceVerifiedAt": str(verified_at), "credentialPresent": credential_present,
        "requestFingerprint": fingerprint, "isRetry": is_retry,
        "retryOfTaskKey": retry_of or None, "references": references,
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        reference = root / "ref.png"
        reference.write_bytes(b"fixture")
        plan = {
            "characterId": "c", "authorization": {"hardLimit": 10, "maximumPaidRetries": 1},
            "provider": {"model": "m", "defaultResolution": "480p", "ratio": "4:3", "generateAudio": False, "watermark": False},
            "costBasis": {"measuredTokensPerFourSeconds480p": 40000, "plannedPlusReserveRmb": 9},
            "tasks": [
                {"taskKey": "t", "actions": ["idle"], "durationSeconds": 4, "resolution": "480p"},
                {"taskKey": "rt", "actions": ["idle"], "durationSeconds": 4, "resolution": "480p"},
            ],
        }
        ledger = {"characterId": "c", "hardLimit": 10, "actualSpentRmb": 0, "estimatedCommittedRmb": 0,
                  "paidRetryCount": 0, "tasks": {}}
        price = {"verifiedAt": "2026-07-16", "officialSource": "https://www.volcengine.com/product/ark", "noVideoInputRmbPerMillionTokens": 23}
        clean_prompt = ("clean motion; locked camera; neutral albedo-reference lighting; stable exposure; "
                        "perfectly uniform solid #00ff00 background; no rim light or baked shadow; "
                        "no attack arc or detached VFX; no fist/foot glow; "
                        "no circular or elliptical blur")
        request = {"characterId": "c", "taskKey": "t", "model": "m", "resolution": "480p", "durationSeconds": 4, "ratio": "4:3", "generateAudio": False, "watermark": False, "actions": ["idle"], "simultaneousSubjects": 1, "packingMode": "sequential_distinct_actions", "prompt": clean_prompt, "requiredPromptPhrases": ["clean motion"], "referencePaths": ["ref.png"], "chromaExtraction": True, "promptContractVersion": "clean-chroma-v2", "keyRgb": [0, 255, 0], "runtimeIdleReferenceRequired": True, "identityReference": {"kind": "approved_runtime_idle", "nativeSize": [256, 256], "canonicalCanvas": [384, 320], "visibleHeightPx": 256}}
        for name, value in (("plan.json", plan), ("ledger.json", ledger), ("price.json", price), ("request.json", request)):
            (root / name).write_text(json.dumps(value), encoding="utf-8")
        os.environ["TEST_VIDEO_KEY"] = "present"
        result = preflight(root / "plan.json", root / "ledger.json", root / "price.json", root / "request.json", root / "receipts", "TEST_VIDEO_KEY", dt.date(2026, 7, 16))
        assert result["ok"] and result["estimatedRmb"] == 0.92
        invalid_request = dict(request); invalid_request["promptContractVersion"] = "old"
        (root / "request.json").write_text(json.dumps(invalid_request), encoding="utf-8")
        invalid = preflight(root / "plan.json", root / "ledger.json", root / "price.json", root / "request.json", root / "receipts", "TEST_VIDEO_KEY", dt.date(2026, 7, 16))
        assert "clean_chroma_prompt_contract_version_missing" in invalid["errors"]
        missing_idle = dict(request); missing_idle.pop("identityReference")
        (root / "request.json").write_text(json.dumps(missing_idle), encoding="utf-8")
        missing_idle_result = preflight(root / "plan.json", root / "ledger.json", root / "price.json", root / "request.json", root / "receipts", "TEST_VIDEO_KEY", dt.date(2026, 7, 16))
        assert "runtime_idle_identity_reference_missing" in missing_idle_result["errors"]
        ambiguous_grid = dict(request); ambiguous_grid.update({"simultaneousSubjects": 2, "packingMode": "independent_grid_distinct_actions", "actions": ["idle", "jab"]})
        (root / "request.json").write_text(json.dumps(ambiguous_grid), encoding="utf-8")
        ambiguous_grid_result = preflight(root / "plan.json", root / "ledger.json", root / "price.json", root / "request.json", root / "receipts", "TEST_VIDEO_KEY", dt.date(2026, 7, 16))
        assert "independent_grid_isolation_contract_incomplete" in ambiguous_grid_result["errors"]
        (root / "request.json").write_text(json.dumps(request), encoding="utf-8")
        ledger["tasks"]["t"] = {"state": "submitted"}
        (root / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        assert "ledger_task_already_exists" in preflight(root / "plan.json", root / "ledger.json", root / "price.json", root / "request.json", root / "receipts", "TEST_VIDEO_KEY", dt.date(2026, 7, 16))["errors"]
        request.update({"taskKey": "rt", "retryOfTaskKey": "t"})
        (root / "request.json").write_text(json.dumps(request), encoding="utf-8")
        retry_result = preflight(root / "plan.json", root / "ledger.json", root / "price.json", root / "request.json", root / "receipts", "TEST_VIDEO_KEY", dt.date(2026, 7, 16))
        assert retry_result["ok"] and retry_result["isRetry"] and retry_result["retryOfTaskKey"] == "t"
        ledger["paidRetryCount"] = 1
        (root / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        assert "paid_retry_limit_exhausted" in preflight(root / "plan.json", root / "ledger.json", root / "price.json", root / "request.json", root / "receipts", "TEST_VIDEO_KEY", dt.date(2026, 7, 16))["errors"]
    print("preflight_billable_task self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--price-lock", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--receipt-dir", type=Path)
    parser.add_argument("--credential-env", default="ARK_API_KEY")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    required = (args.plan, args.ledger, args.price_lock, args.request, args.receipt_dir)
    if any(value is None for value in required):
        parser.error("plan, ledger, price-lock, request and receipt-dir are required")
    result = preflight(args.plan, args.ledger, args.price_lock, args.request, args.receipt_dir, args.credential_env)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
