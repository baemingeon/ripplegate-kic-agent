from __future__ import annotations

"""Convert a completed pilot-console export into the guarded paired log.

The explicit --observed-by-human flag is required. The converter never turns
the Agent-only runtime artifact into a paired result by itself.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ripplegate_paired_eval import DEFAULT_LOG, PACKET_IDS, paired_status


MANIFEST_PATH = Path(__file__).resolve().parent / "data" / "ripplegate_pilot_packet_manifest_v1.json"


def read_manifest() -> dict[str, dict[str, Any]]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    packets = payload.get("packets")
    if not isinstance(packets, list):
        raise SystemExit("canonical packet manifest is invalid")
    result = {str(packet.get("packet_id")): packet for packet in packets if isinstance(packet, dict)}
    if set(result) != PACKET_IDS:
        raise SystemExit("canonical packet manifest must contain exactly P01~P05")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a human-observed RippleGate pilot console export")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--observed-by-human", action="store_true")
    args = parser.parse_args()
    if not args.observed_by_human:
        raise SystemExit("refusing to record invented values; add --observed-by-human after checking the real logs")
    data = json.loads(args.input.read_text(encoding="utf-8"))
    if data.get("status") != "READY_TO_RECORD":
        raise SystemExit("console export is not READY_TO_RECORD")
    operator = str(data.get("operator_id_anonymous", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", operator):
        raise SystemExit("operator_id_anonymous must be an anonymous ASCII identifier")
    rows = data.get("rows")
    manifest = read_manifest()
    if not isinstance(rows, list) or len(rows) != len(PACKET_IDS) or {str(row.get("packet_id")) for row in rows} != PACKET_IDS:
        raise SystemExit("console export must contain exactly P01~P05")
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    output: list[dict[str, Any]] = []
    for row in rows:
        packet_id = str(row["packet_id"])
        packet = manifest[packet_id]
        for field in ("dataset", "user_goal", "expected_decision"):
            if row.get(field) != packet.get(field):
                raise SystemExit(f"{packet_id}: {field} does not match the canonical packet manifest")
        base = {
            "schema_version": "ripplegate-paired-eval.v1",
            "packet_id": packet_id,
            "dataset": packet["dataset"],
            "user_goal": packet["user_goal"],
            "expected_decision": packet["expected_decision"],
            "operator_id_anonymous": operator,
            "timing_scope": "end_to_end_workflow",
            "created_at": created_at,
            "review_log_reference": str(row["review_log"]),
            "agent_trace_reference": str(row["trace"]),
            "evidence_ledger_reference": str(row["ledger"]),
        }
        for prefix, condition in (("manual", "manual"), ("agent", "agent")):
            output.append({
                **base,
                "condition": condition,
                "measurement_type": "human_observed_agent" if condition == "agent" else "human_observed_manual",
                "observed_minutes": float(row[prefix]),
                "rework_count": int(row[f"{prefix}_rework"]),
                "source_gaps": int(row[f"{prefix}_gap"]),
                "calculation_inconsistencies": int(row[f"{prefix}_calc"]),
                "decision": str(row[f"{prefix}_decision"]),
            })
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a", encoding="utf-8") as handle:
        for record in output:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    all_records = []
    for line in args.log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            all_records.append(json.loads(line))
    print(json.dumps({"recorded": len(output), "readiness": paired_status(all_records), "disclosure": "실제 관찰 입력만 기록했으며 P01~P05가 모두 paired 되기 전에는 효과 수치를 발표하지 않는다."}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
