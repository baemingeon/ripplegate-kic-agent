from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "data" / "pilot_packet_manifest_v0.1.json"
DEFAULT_RUNTIME = ROOT / "data" / "pilot_agent_runtime_2026-11-07.json"
DEFAULT_LOG = ROOT / "data" / "effect_measurement_log.jsonl"
EXPECTED_PACKET_IDS = ("P01", "P02", "P03", "P04", "P05")
ALLOWED_DECISIONS = {"REVIEW", "HOLD", "REQUEST_INFO"}
COMPARABLE_SCOPE = "end_to_end_workflow"


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"JSON object required at {path}:{line_number}")
        rows.append(payload)
    return rows


def validate_runtime(runtime: dict[str, Any], packet_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if runtime.get("status") != "agent_only_no_human_claim":
        errors.append("agent runtime status must remain agent_only_no_human_claim")
    if runtime.get("timing_scope") != "server_runtime_only":
        errors.append("pilot runtime must be disclosed as server_runtime_only")
    records = runtime.get("records")
    if not isinstance(records, list):
        return errors + ["pilot runtime records must be a list"]
    observed_ids = {str(row.get("packet_id")) for row in records if isinstance(row, dict)}
    if observed_ids != packet_ids:
        errors.append(f"pilot runtime packet ids mismatch: {sorted(observed_ids)}")
    for row in records:
        if not isinstance(row, dict):
            errors.append("pilot runtime contains a non-object record")
            continue
        if row.get("expected_decision") != row.get("observed_decision"):
            errors.append(f"pilot runtime decision mismatch: {row.get('packet_id')}")
        if row.get("measurement_type") != "automated_runtime":
            errors.append(f"pilot runtime measurement type is not automated_runtime: {row.get('packet_id')}")
    return errors


def complete_manual(row: dict[str, Any]) -> bool:
    required = (
        "elapsed_minutes",
        "human_rework_count",
        "human_source_gaps",
        "human_calculation_inconsistencies",
    )
    return (
        row.get("condition") == "manual"
        and row.get("measurement_type") == "human_entered"
        and row.get("timing_scope") == COMPARABLE_SCOPE
        and isinstance(row.get("elapsed_minutes"), (int, float))
        and float(row["elapsed_minutes"]) >= 0
        and all(isinstance(row.get(field), int) and row[field] >= 0 for field in required[1:])
        and row.get("decision") in ALLOWED_DECISIONS
    )


def complete_observed_agent(row: dict[str, Any]) -> bool:
    return (
        row.get("condition") == "agent"
        and row.get("measurement_type") == "human_observed_agent"
        and row.get("timing_scope") == COMPARABLE_SCOPE
        and isinstance(row.get("elapsed_minutes"), (int, float))
        and float(row["elapsed_minutes"]) >= 0
        and row.get("decision") in ALLOWED_DECISIONS
    )


def build_report(
    manifest: dict[str, Any], runtime: dict[str, Any], records: list[dict[str, Any]], *, log_exists: bool
) -> dict[str, Any]:
    manifest_packets = manifest.get("packets") if isinstance(manifest.get("packets"), list) else []
    packet_ids = {str(row.get("packet_id")) for row in manifest_packets if isinstance(row, dict)}
    errors = validate_runtime(runtime, packet_ids)
    if packet_ids != set(EXPECTED_PACKET_IDS):
        errors.append(f"manifest must contain exactly {list(EXPECTED_PACKET_IDS)}")

    by_packet: dict[str, dict[str, list[dict[str, Any]]]] = {
        packet_id: {"manual": [], "agent": []} for packet_id in EXPECTED_PACKET_IDS
    }
    unexpected_records: list[str] = []
    for row in records:
        packet_id = str(row.get("packet_id", ""))
        condition = str(row.get("condition", ""))
        if packet_id not in by_packet or condition not in {"manual", "agent"}:
            unexpected_records.append(f"{packet_id}:{condition}")
            continue
        by_packet[packet_id][condition].append(row)

    paired_packets: list[dict[str, Any]] = []
    missing_manual: list[str] = []
    missing_observed_agent: list[str] = []
    incomplete_packets: list[str] = []
    scope_mismatch_packets: list[str] = []
    for packet_id in EXPECTED_PACKET_IDS:
        manual_rows = by_packet[packet_id]["manual"]
        agent_rows = by_packet[packet_id]["agent"]
        valid_manual = [row for row in manual_rows if complete_manual(row)]
        valid_agent = [row for row in agent_rows if complete_observed_agent(row)]
        if not valid_manual:
            missing_manual.append(packet_id)
        if not valid_agent:
            missing_observed_agent.append(packet_id)
        if manual_rows and agent_rows:
            manual_scopes = sorted({str(row.get("timing_scope", "")) for row in manual_rows})
            agent_scopes = sorted({str(row.get("timing_scope", "")) for row in agent_rows})
            if manual_scopes != agent_scopes or manual_scopes != [COMPARABLE_SCOPE]:
                scope_mismatch_packets.append(packet_id)
        if valid_manual and valid_agent:
            manual_minutes = [float(row["elapsed_minutes"]) for row in valid_manual]
            agent_minutes = [float(row["elapsed_minutes"]) for row in valid_agent]
            manual_mean = statistics.mean(manual_minutes)
            agent_mean = statistics.mean(agent_minutes)
            paired_packets.append(
                {
                    "packet_id": packet_id,
                    "manual_observations": len(valid_manual),
                    "agent_observations": len(valid_agent),
                    "manual_mean_minutes": round(manual_mean, 3),
                    "agent_mean_minutes": round(agent_mean, 3),
                    "timing_scope": COMPARABLE_SCOPE,
                    "time_saving_rate": round((manual_mean - agent_mean) / manual_mean, 4)
                    if manual_mean > 0
                    else None,
                }
            )
        elif manual_rows or agent_rows:
            incomplete_packets.append(packet_id)

    if unexpected_records:
        errors.append(f"unexpected measurement records: {unexpected_records}")
    ready = not errors and len(paired_packets) == len(EXPECTED_PACKET_IDS)
    if not records and not log_exists:
        status = "AWAITING_HUMAN_PAIRING"
    elif ready:
        status = "READY_TO_REPORT"
    else:
        status = "INCOMPLETE"

    return {
        "schema_version": "effect-measurement-readiness.v1",
        "status": status,
        "claim_allowed": ready,
        "packet_count_required": len(EXPECTED_PACKET_IDS),
        "paired_packet_count": len(paired_packets),
        "paired_packets": paired_packets,
        "missing_manual_for": missing_manual,
        "missing_observed_agent_for": missing_observed_agent,
        "incomplete_packets": sorted(set(incomplete_packets)),
        "scope_mismatch_packets": sorted(set(scope_mismatch_packets)),
        "runtime_validation_errors": errors,
        "record_count": len(records),
        "disclosure": (
            "수작업 stopwatch와 Agent end-to-end 시간을 같은 packet·같은 범위로 입력하기 전에는 "
            "시간절감률·업무효과를 주장하지 않는다. server_runtime_only 기록은 paired 효과측정에 사용할 수 없다."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IC Preflight paired 업무효과 측정 준비도 검증기")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true", help="5개 paired 측정이 없으면 실패 코드 반환")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = read_json(args.manifest)
        runtime = read_json(args.runtime)
        records = read_jsonl(args.log)
        report = build_report(manifest, runtime, records, log_exists=args.log.exists())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"schema_version": "effect-measurement-readiness.v1", "status": "ERROR", "error": str(exc)}

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("status") == "ERROR":
        return 1
    if args.strict and report.get("status") != "READY_TO_REPORT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
