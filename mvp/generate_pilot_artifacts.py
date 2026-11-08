from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from server import run_agent


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MANIFEST_PATH = DATA / "pilot_packet_manifest_v0.1.json"
RUNTIME_PATH = DATA / "pilot_agent_runtime_2026-11-07.json"


PACKETS = [
    {
        "packet_id": "P01",
        "scenario": "clean",
        "user_goal": "Company A의 Peer 3개와 valuation을 계산하고 취약한 가정을 검증",
        "expected_decision": "REVIEW",
        "purpose": "정상 자료에서 false-hold를 확인하는 기준 packet",
    },
    {
        "packet_id": "P02",
        "scenario": "period_mismatch",
        "user_goal": "대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘",
        "expected_decision": "HOLD",
        "purpose": "기간 불일치 후 재계획·보류 packet",
    },
    {
        "packet_id": "P03",
        "scenario": "missing_evidence",
        "user_goal": "필수 EBITDA 근거가 없으면 계산하지 말고 자료를 요청해줘",
        "expected_decision": "REQUEST_INFO",
        "purpose": "필수 근거 누락 packet",
    },
    {
        "packet_id": "P04",
        "scenario": "conflict",
        "user_goal": "서로 다른 Revenue 수치를 원문 재조회 후 검증해줘",
        "expected_decision": "REVIEW",
        "purpose": "보조자료 충돌 후 primary evidence로 재계산하는 packet",
    },
    {
        "packet_id": "P05",
        "scenario": "real",
        "user_goal": "Mastercard 공개자료와 Peer의 P/S valuation을 검증해줘",
        "expected_decision": "REVIEW",
        "purpose": "공개자료 snapshot과 실제 source link를 사용하는 packet",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def memo_decision(result: dict) -> str:
    memo = result.get("memo") or {}
    return str(memo.get("decision") or result.get("status") or "")


def run_agent_only() -> dict:
    records = []
    for packet in PACKETS:
        started = time.perf_counter()
        result = run_agent(packet["scenario"], use_llm=False, user_goal=packet["user_goal"])
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        records.append(
            {
                "packet_id": packet["packet_id"],
                "scenario": packet["scenario"],
                "expected_decision": packet["expected_decision"],
                "observed_decision": memo_decision(result),
                "status": result.get("status"),
                "elapsed_ms": elapsed_ms,
                "trace_count": len(result.get("trace", [])),
                "tool_count": len(result.get("tool_results", [])),
                "evidence_count": len(result.get("evidence", [])),
                "timing_scope": "server_runtime_only",
                "measurement_type": "automated_runtime",
            }
        )
    elapsed_values = [item["elapsed_ms"] for item in records]
    return {
        "schema_version": "pilot-agent-runtime.v1",
        "generated_at": utc_now(),
        "status": "agent_only_no_human_claim",
        "timing_scope": "server_runtime_only",
        "packet_count": len(records),
        "decision_match_count": sum(
            item["expected_decision"] == item["observed_decision"] for item in records
        ),
        "records": records,
        "summary": {
            "median_elapsed_ms": round(statistics.median(elapsed_values), 1),
            "min_elapsed_ms": min(elapsed_values),
            "max_elapsed_ms": max(elapsed_values),
        },
        "disclosure": "Agent 내부 실행시간만 기록했다. 사람의 수작업 시간·재작업·출처 누락을 측정하거나 추정하지 않는다.",
    }


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "pilot-packet-manifest.v1",
        "generated_at": utc_now(),
        "status": "awaiting_human_pairing",
        "design": "동일 packet_id에 분석가 수작업 stopwatch와 Agent end-to-end 시간을 각각 입력",
        "timing_scope": "end_to_end_workflow",
        "packets": PACKETS,
        "human_entry_fields": [
            "elapsed_minutes",
            "rework_count",
            "source_gaps",
            "calculation_inconsistencies",
            "decision",
        ],
        "rules": [
            "사람의 시간·품질 수치는 실제 stopwatch와 review log가 있을 때만 입력",
            "server_runtime_only와 end_to_end_workflow를 직접 비교하지 않음",
            "표본 5개가 확보되기 전 시간절감률을 발표하지 않음",
        ],
    }
    RUNTIME_PATH.write_text(json.dumps(run_agent_only(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST_PATH), "runtime": str(RUNTIME_PATH), "packet_count": len(PACKETS)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
