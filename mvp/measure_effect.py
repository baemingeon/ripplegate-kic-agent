from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from server import run_agent


ROOT = Path(__file__).resolve().parent
DEFAULT_LOG = ROOT / "data" / "effect_measurement_log.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_agent_record(
    packet_id: str,
    scenario: str,
    *,
    use_llm: bool = False,
    result: dict[str, Any] | None = None,
    elapsed_ms: float | int | None = None,
    observed_minutes: float | None = None,
    timing_scope: str = "server_runtime_only",
) -> dict[str, Any]:
    """Create a non-human performance record without inventing analyst metrics."""
    if result is None:
        started = time.perf_counter()
        result = run_agent(scenario, use_llm=use_llm)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    if elapsed_ms is None:
        raise ValueError("elapsed_ms is required when result is supplied")
    if observed_minutes is not None:
        if observed_minutes < 0:
            raise ValueError("observed_minutes must be non-negative")
        if timing_scope == "server_runtime_only":
            raise ValueError("observed_minutes requires an end-to-end timing_scope")
        elapsed_ms = round(observed_minutes * 60000)
    memo = result.get("memo") or {}
    return {
        "schema_version": "effect-measurement.v1",
        "record_id": f"agent-{packet_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
        "recorded_at": utc_now(),
        "packet_id": packet_id,
        "condition": "agent",
        "scenario": scenario,
        "execution_mode": "approved_llm" if use_llm else "deterministic",
        "timing_scope": timing_scope,
        "elapsed_ms": round(float(elapsed_ms), 3),
        "elapsed_minutes": round(float(elapsed_ms) / 60000, 6),
        "decision": memo.get("decision", result.get("status")),
        "agent_trace_count": len(result.get("trace", [])),
        "evidence_count": len(result.get("evidence", [])),
        "human_rework_count": None,
        "human_source_gaps": None,
        "human_calculation_inconsistencies": None,
        "measurement_type": "human_observed_agent" if observed_minutes is not None else "automated_runtime",
        "disclosure": (
            "Agent 결과는 실행했고 elapsed는 사용자가 측정한 end-to-end workflow 시간"
            if observed_minutes is not None
            else "Agent 실행시간만 자동 측정했으며 사람의 수작업 시간·재작업·누락은 측정하지 않음"
        ),
    }


def build_manual_record(
    packet_id: str,
    elapsed_minutes: float,
    *,
    scenario: str = "manual_review",
    decision: str = "REVIEW",
    rework_count: int | None = None,
    source_gaps: int | None = None,
    calculation_inconsistencies: int | None = None,
    timing_scope: str = "end_to_end_workflow",
) -> dict[str, Any]:
    """Create a human-entered record; all values must come from the operator."""
    if elapsed_minutes < 0:
        raise ValueError("elapsed_minutes must be non-negative")
    return {
        "schema_version": "effect-measurement.v1",
        "record_id": f"manual-{packet_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
        "recorded_at": utc_now(),
        "packet_id": packet_id,
        "condition": "manual",
        "scenario": scenario,
        "execution_mode": "human_entered",
        "timing_scope": timing_scope,
        "elapsed_ms": round(elapsed_minutes * 60000),
        "elapsed_minutes": round(elapsed_minutes, 3),
        "decision": decision,
        "agent_trace_count": None,
        "evidence_count": None,
        "human_rework_count": rework_count,
        "human_source_gaps": source_gaps,
        "human_calculation_inconsistencies": calculation_inconsistencies,
        "measurement_type": "human_entered",
        "disclosure": "분석가가 실제 stopwatch와 review log를 바탕으로 입력해야 하는 값",
    }


def append_record(log_path: Path, record: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_records(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at line {line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"record at line {line_number} is not an object")
        records.append(record)
    return records


def summarize_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    by_packet: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        packet_id = str(row.get("packet_id", "")).strip()
        condition = str(row.get("condition", "")).strip()
        if packet_id and condition in {"manual", "agent"}:
            by_packet.setdefault(packet_id, {}).setdefault(condition, []).append(row)

    paired_packets = []
    missing_manual: list[str] = []
    missing_agent: list[str] = []
    for packet_id, conditions in sorted(by_packet.items()):
        if not conditions.get("manual"):
            missing_manual.append(packet_id)
        if not conditions.get("agent"):
            missing_agent.append(packet_id)
        if conditions.get("manual") and conditions.get("agent"):
            manual_times = [float(row["elapsed_minutes"]) for row in conditions["manual"]]
            agent_times = [float(row["elapsed_minutes"]) for row in conditions["agent"]]
            manual_mean = statistics.mean(manual_times)
            agent_mean = statistics.mean(agent_times)
            manual_scopes = {str(row.get("timing_scope", "")) for row in conditions["manual"]}
            agent_scopes = {str(row.get("timing_scope", "")) for row in conditions["agent"]}
            comparable = len(manual_scopes) == 1 and manual_scopes == agent_scopes
            paired_packets.append(
                {
                    "packet_id": packet_id,
                    "manual_observations": len(manual_times),
                    "agent_observations": len(agent_times),
                    "manual_mean_minutes": round(manual_mean, 3),
                    "agent_mean_minutes": round(agent_mean, 3),
                    "manual_timing_scope": sorted(manual_scopes),
                    "agent_timing_scope": sorted(agent_scopes),
                    "timing_status": "comparable" if comparable else "scope_mismatch",
                    "time_saving_rate": round((manual_mean - agent_mean) / manual_mean, 4)
                    if comparable and manual_mean > 0
                    else None,
                }
            )

    comparable_count = sum(item["timing_status"] == "comparable" for item in paired_packets)
    return {
        "schema_version": "effect-measurement-summary.v1",
        "generated_at": utc_now(),
        "status": "ready" if paired_packets and comparable_count else "insufficient_observations",
        "record_count": len(rows),
        "packet_count": len(by_packet),
        "paired_packet_count": len(paired_packets),
        "comparable_timing_packet_count": comparable_count,
        "paired_packets": paired_packets,
        "missing_manual_for": missing_manual,
        "missing_agent_for": missing_agent,
        "disclosure": "동일 timing_scope의 paired packet과 표본 수가 확보되기 전에는 시간 절감률을 주장하지 않음",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KIC Agent 업무효과 측정 기록기")
    parser.add_argument("--condition", choices=("agent", "manual", "summary"), required=True)
    parser.add_argument("--packet-id", help="같은 업무 packet을 수작업과 Agent에 연결할 ID")
    parser.add_argument("--scenario", default="clean")
    parser.add_argument("--mode", choices=("deterministic", "approved_llm"), default="deterministic")
    parser.add_argument("--elapsed-minutes", type=float)
    parser.add_argument("--rework-count", type=int)
    parser.add_argument("--source-gaps", type=int)
    parser.add_argument("--calculation-inconsistencies", type=int)
    parser.add_argument("--decision", choices=("REVIEW", "HOLD", "REQUEST_INFO"), default="REVIEW")
    parser.add_argument(
        "--timing-scope",
        choices=("server_runtime_only", "end_to_end_workflow"),
        default=None,
        help="server 내부 실행시간 또는 사용자가 잰 end-to-end workflow 시간",
    )
    parser.add_argument(
        "--observed-minutes",
        type=float,
        help="Agent 결과는 실행하되 사용자가 stopwatch로 측정한 end-to-end 시간(분)",
    )
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.condition in {"agent", "manual"} and not args.packet_id:
        raise SystemExit("--packet-id is required for agent/manual records")

    if args.condition == "agent":
        timing_scope = args.timing_scope or "server_runtime_only"
        record = build_agent_record(
            args.packet_id,
            args.scenario,
            use_llm=args.mode == "approved_llm",
            observed_minutes=args.observed_minutes,
            timing_scope=timing_scope,
        )
        append_record(args.log, record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    if args.condition == "manual":
        if args.elapsed_minutes is None:
            raise SystemExit("--elapsed-minutes is required for manual records")
        record = build_manual_record(
            args.packet_id,
            args.elapsed_minutes,
            scenario=args.scenario,
            decision=args.decision,
            rework_count=args.rework_count,
            source_gaps=args.source_gaps,
            calculation_inconsistencies=args.calculation_inconsistencies,
            timing_scope=args.timing_scope or "end_to_end_workflow",
        )
        append_record(args.log, record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(summarize_records(read_records(args.log)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
