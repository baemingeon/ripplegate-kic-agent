from __future__ import annotations

"""Validate the current RippleGate P01~P05 human/Agent paired evidence.

This validator deliberately keeps automated browser runtime evidence separate
from human-observed end-to-end measurements. It never creates a paired result
and it only permits an effect claim when all five packets have both conditions.
"""

import argparse
import json
import re
import statistics
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "data" / "ripplegate_pilot_packet_manifest_v1.json"
DEFAULT_LOG = ROOT / "paired_eval_log.jsonl"
DEFAULT_RUNTIME = ROOT / "data" / "ripplegate_agent_runtime_p01_p05_20261108.json"
PACKET_IDS = {f"P0{index}" for index in range(1, 6)}
CONDITIONS = {"manual", "agent"}
DECISIONS = {"REVIEW", "HOLD", "REQUEST_INFO"}
MEASUREMENT_TYPES = {
    "manual": "human_observed_manual",
    "agent": "human_observed_agent",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return records, errors
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:{line_number}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path.name}:{line_number}: record must be an object")
            continue
        records.append(value)
    return records, errors


def manifest_packets(path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not path.exists():
        return {}, [f"manifest missing: {path}"]
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"manifest unreadable: {exc}"]
    packets = payload.get("packets") if isinstance(payload, dict) else None
    if not isinstance(packets, list):
        return {}, ["manifest packets must be a list"]
    result: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for packet in packets:
        if not isinstance(packet, dict):
            errors.append("manifest packet must be an object")
            continue
        packet_id = str(packet.get("packet_id", ""))
        if packet_id in result:
            errors.append(f"duplicate manifest packet: {packet_id}")
        result[packet_id] = packet
    if set(result) != PACKET_IDS:
        errors.append(f"manifest packet IDs must be exactly {sorted(PACKET_IDS)}")
    return result, errors


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_record(record: dict[str, Any], manifest: dict[str, dict[str, Any]], index: int) -> list[str]:
    errors: list[str] = []
    prefix = f"record[{index}]"
    packet_id = str(record.get("packet_id", ""))
    condition = str(record.get("condition", ""))
    if packet_id not in PACKET_IDS:
        errors.append(f"{prefix}: unknown packet_id {packet_id!r}")
        return errors
    if condition not in CONDITIONS:
        errors.append(f"{prefix} {packet_id}: condition must be manual or agent")
    if record.get("schema_version") != "ripplegate-paired-eval.v1":
        errors.append(f"{prefix} {packet_id}: schema_version mismatch")
    if record.get("timing_scope") != "end_to_end_workflow":
        errors.append(f"{prefix} {packet_id}: timing_scope mismatch")
    if condition in CONDITIONS and record.get("measurement_type") != MEASUREMENT_TYPES[condition]:
        errors.append(f"{prefix} {packet_id}: measurement_type does not match condition")
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", str(record.get("operator_id_anonymous", ""))):
        errors.append(f"{prefix} {packet_id}: anonymous operator ID is missing or invalid")
    for field in ("dataset", "user_goal", "expected_decision"):
        if field not in record:
            errors.append(f"{prefix} {packet_id}: {field} is required from the canonical packet manifest")
    for field in ("review_log_reference", "agent_trace_reference", "evidence_ledger_reference"):
        if not nonempty(record.get(field)):
            errors.append(f"{prefix} {packet_id}: {field} is required")
    try:
        observed_minutes = float(record.get("observed_minutes"))
        if observed_minutes <= 0:
            errors.append(f"{prefix} {packet_id}: observed_minutes must be positive")
    except (TypeError, ValueError):
        errors.append(f"{prefix} {packet_id}: observed_minutes must be numeric")
    for field in ("rework_count", "source_gaps", "calculation_inconsistencies"):
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{prefix} {packet_id}: {field} must be a non-negative integer")
    if record.get("decision") not in DECISIONS:
        errors.append(f"{prefix} {packet_id}: decision must be one of {sorted(DECISIONS)}")

    expected = manifest[packet_id]
    for field in ("dataset", "user_goal", "expected_decision"):
        if field in record and record[field] != expected.get(field):
            errors.append(f"{prefix} {packet_id}: {field} does not match the canonical manifest")
    return errors


def validate_runtime(path: Path, manifest: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {"status": "NOT_PRESENT", "claim_allowed": False}, []
    errors: list[str] = []
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "INVALID", "claim_allowed": False}, [f"runtime unreadable: {exc}"]
    if payload.get("status") != "AGENT_RUNTIME_ONLY":
        errors.append("runtime artifact must be marked AGENT_RUNTIME_ONLY")
    records = payload.get("records")
    if not isinstance(records, list):
        errors.append("runtime records must be a list")
        records = []
    observed_ids: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"runtime record[{index}] must be an object")
            continue
        packet_id = str(record.get("packet_id", ""))
        observed_ids.add(packet_id)
        if packet_id not in PACKET_IDS:
            errors.append(f"runtime record[{index}] has unknown packet_id {packet_id!r}")
            continue
        if record.get("dataset") != manifest[packet_id].get("dataset"):
            errors.append(f"runtime {packet_id}: dataset does not match manifest")
        if record.get("measurement_type") != "agent_end_to_end_browser_observed":
            errors.append(f"runtime {packet_id}: measurement_type must remain runtime-only")
    if observed_ids != PACKET_IDS:
        errors.append("runtime packet IDs must be exactly P01~P05")
    return {
        "status": "INVALID" if errors else "AGENT_RUNTIME_ONLY",
        "packet_ids": sorted(observed_ids),
        "claim_allowed": False,
        "disclosure": "자동 브라우저 실행값이며 사람 수작업 baseline 또는 paired 효과 수치가 아님",
    }, errors


def validate(manifest_path: Path, log_path: Path, runtime_path: Path) -> dict[str, Any]:
    manifest, errors = manifest_packets(manifest_path)
    records, log_errors = read_jsonl(log_path)
    errors.extend(log_errors)
    runtime, runtime_errors = validate_runtime(runtime_path, manifest) if manifest else ({"status": "NOT_CHECKED", "claim_allowed": False}, [])
    errors.extend(runtime_errors)

    seen: set[tuple[str, str]] = set()
    valid_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        record_errors = validate_record(record, manifest, index)
        errors.extend(record_errors)
        key = (str(record.get("packet_id", "")), str(record.get("condition", "")))
        if key in seen:
            errors.append(f"duplicate paired condition: {key[0]} / {key[1]}")
        seen.add(key)
        if not record_errors:
            valid_records.append(record)

    required_pairs = {(packet_id, condition) for packet_id in PACKET_IDS for condition in CONDITIONS}
    complete_pairs = sorted(seen & required_pairs)
    missing_pairs = sorted(required_pairs - seen)
    if errors:
        status = "INVALID"
    elif not records:
        status = "AWAITING_HUMAN_PAIRING"
    elif missing_pairs:
        status = "INCOMPLETE"
    else:
        status = "READY_TO_REPORT"

    result: dict[str, Any] = {
        "status": status,
        "claim_allowed": status == "READY_TO_REPORT",
        "manifest": str(manifest_path),
        "log": str(log_path),
        "runtime": runtime,
        "record_count": len(records),
        "complete_pair_count": len(complete_pairs),
        "missing_pairs": [f"{packet_id}/{condition}" for packet_id, condition in missing_pairs],
        "errors": errors,
        "disclosure": "P01~P05의 실제 사람 관찰 paired 기록이 모두 유효할 때만 파일럿 효과 수치를 계산할 수 있음",
    }
    if status == "READY_TO_REPORT":
        manual = [float(record["observed_minutes"]) for record in valid_records if record["condition"] == "manual"]
        agent = [float(record["observed_minutes"]) for record in valid_records if record["condition"] == "agent"]
        manual_mean = statistics.mean(manual)
        agent_mean = statistics.mean(agent)
        result["effect"] = {
            "sample_size_packets": len(manual),
            "manual_mean_minutes": round(manual_mean, 4),
            "agent_mean_minutes": round(agent_mean, 4),
            "manual_median_minutes": round(statistics.median(manual), 4),
            "agent_median_minutes": round(statistics.median(agent), 4),
            "time_reduction_percent": round((manual_mean - agent_mean) / manual_mean * 100, 2) if manual_mean else None,
            "scope": "5-packet pilot only; not an institution-wide performance claim",
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate RippleGate P01~P05 paired evidence")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--strict", action="store_true", help="exit 0 only when READY_TO_REPORT")
    args = parser.parse_args()
    result = validate(args.manifest, args.log, args.runtime)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and result["status"] != "READY_TO_REPORT":
        return 1
    return 0 if result["status"] != "INVALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
