from __future__ import annotations

"""Record and summarize real human/Agent paired observations.

The command intentionally requires --observed-by-human. It never invents
timings, logs, or effectiveness numbers for a missing pair.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKET_IDS = {f"P0{index}" for index in range(1, 6)}
DECISIONS = {"REVIEW", "HOLD", "REQUEST_INFO"}
DEFAULT_LOG = Path(__file__).resolve().parent / "paired_eval_log.jsonl"


def positive_number(name: str, value: float) -> float:
    if value < 0:
        raise SystemExit(f"{name} must be non-negative")
    return float(value)


def non_negative_int(name: str, value: int) -> int:
    if value < 0:
        raise SystemExit(f"{name} must be non-negative")
    return int(value)


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
    return records


def paired_status(records: list[dict[str, Any]]) -> dict[str, Any]:
    pairs: dict[str, set[str]] = {packet_id: set() for packet_id in sorted(PACKET_IDS)}
    for record in records:
        packet_id = str(record.get("packet_id", ""))
        condition = str(record.get("condition", ""))
        if packet_id in pairs and condition in {"manual", "agent"}:
            pairs[packet_id].add(condition)
    complete = sorted(packet_id for packet_id, conditions in pairs.items() if conditions == {"manual", "agent"})
    if len(complete) == len(PACKET_IDS):
        status = "READY_TO_REPORT"
    elif complete:
        status = "INCOMPLETE"
    else:
        status = "AWAITING_HUMAN_PAIRING"
    return {"status": status, "complete_packet_ids": complete, "pairs": {key: sorted(value) for key, value in pairs.items()}}


def main() -> int:
    parser = argparse.ArgumentParser(description="Record one real RippleGate human/Agent paired observation")
    parser.add_argument("--packet-id", required=True, choices=sorted(PACKET_IDS))
    parser.add_argument("--operator-id", required=True, help="익명 operator ID; 실명·이메일을 넣지 않음")
    parser.add_argument("--review-log-reference", required=True)
    parser.add_argument("--agent-trace-reference", required=True)
    parser.add_argument("--evidence-ledger-reference", required=True)
    parser.add_argument("--manual-minutes", type=float, required=True)
    parser.add_argument("--agent-minutes", type=float, required=True)
    parser.add_argument("--manual-rework-count", type=int, required=True)
    parser.add_argument("--agent-rework-count", type=int, required=True)
    parser.add_argument("--manual-source-gaps", type=int, required=True)
    parser.add_argument("--agent-source-gaps", type=int, required=True)
    parser.add_argument("--manual-calculation-inconsistencies", type=int, required=True)
    parser.add_argument("--agent-calculation-inconsistencies", type=int, required=True)
    parser.add_argument("--manual-decision", choices=sorted(DECISIONS), required=True)
    parser.add_argument("--agent-decision", choices=sorted(DECISIONS), required=True)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--observed-by-human", action="store_true", help="실제 stopwatch·review log·trace를 확인했음을 명시")
    args = parser.parse_args()

    if not args.observed_by_human:
        raise SystemExit("refusing to record invented values; add --observed-by-human after checking the real logs")
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", args.operator_id):
        raise SystemExit("operator-id must be an anonymous ASCII identifier")
    for name, value in (("manual-minutes", args.manual_minutes), ("agent-minutes", args.agent_minutes)):
        positive_number(name, value)
    for name, value in (
        ("manual-rework-count", args.manual_rework_count),
        ("agent-rework-count", args.agent_rework_count),
        ("manual-source-gaps", args.manual_source_gaps),
        ("agent-source-gaps", args.agent_source_gaps),
        ("manual-calculation-inconsistencies", args.manual_calculation_inconsistencies),
        ("agent-calculation-inconsistencies", args.agent_calculation_inconsistencies),
    ):
        non_negative_int(name, value)
    for name, value in (("review-log-reference", args.review_log_reference), ("agent-trace-reference", args.agent_trace_reference), ("evidence-ledger-reference", args.evidence_ledger_reference)):
        if not str(value).strip():
            raise SystemExit(f"{name} is required")

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = {
        "schema_version": "ripplegate-paired-eval.v1",
        "packet_id": args.packet_id,
        "operator_id_anonymous": args.operator_id,
        "timing_scope": "end_to_end_workflow",
        "created_at": created_at,
        "review_log_reference": args.review_log_reference,
        "agent_trace_reference": args.agent_trace_reference,
        "evidence_ledger_reference": args.evidence_ledger_reference,
    }
    records = [
        {**base, "condition": "manual", "observed_minutes": args.manual_minutes, "rework_count": args.manual_rework_count, "source_gaps": args.manual_source_gaps, "calculation_inconsistencies": args.manual_calculation_inconsistencies, "decision": args.manual_decision},
        {**base, "condition": "agent", "measurement_type": "human_observed_agent", "observed_minutes": args.agent_minutes, "rework_count": args.agent_rework_count, "source_gaps": args.agent_source_gaps, "calculation_inconsistencies": args.agent_calculation_inconsistencies, "decision": args.agent_decision},
    ]
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    all_records = read_records(args.log)
    print(json.dumps({"recorded": records, "readiness": paired_status(all_records), "disclosure": "실제 입력한 paired 관찰값만 기록했다. P01~P05가 모두 paired 되기 전에는 효과 수치를 발표하지 않는다."}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
