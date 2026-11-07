from __future__ import annotations

"""A transparent retrieval-and-summary control group.

This is not presented as a measured live LLM benchmark. It uses the same
packet and preserves source IDs, but stops at a free-form summary. The control
is intentionally workflow-level: it represents a search/retrieval result that
still needs a human to structure paths, align periods, calculate impacts, and
decide what to do with unresolved evidence.
"""

from typing import Any


def summary_only_baseline(graph: dict[str, Any], user_goal: str = "") -> dict[str, Any]:
    nodes = {str(node.get("id")): node for node in graph.get("nodes", [])}
    origin = graph.get("origin", {})
    destinations = []
    evidence_ids: list[str] = []
    for edge in graph.get("edges", []):
        destination = nodes.get(str(edge.get("to")), {})
        if destination.get("label"):
            destinations.append(destination["label"])
        evidence_ids.extend(str(item) for item in edge.get("evidence_ids", [])[:1])
    return {
        "baseline_version": "retrieval_summary_control_v2",
        "same_input": {
            "user_goal": str(user_goal)[:800],
            "origin": origin.get("label"),
            "destinations": destinations,
        },
        "decision": "REVIEW",
        "answer": f"{origin.get('label', '선택된 이슈')}는 {', '.join(destinations[:3])}에 영향을 줄 수 있습니다.",
        "evidence_ids": evidence_ids[:3],
        "retrieved_source_count": len(set(evidence_ids)),
        "path_count": 0,
        "numeric_result": None,
        "status_counts": {"VERIFIED": 0, "SCENARIO": 0, "HOLD": 0},
        "controls_present": [
            "same input packet",
            "source IDs retained",
            "free-form summary",
        ],
        "controls_absent": [
            "typed impact path",
            "human assumption gate",
            "deterministic formula",
            "evidence status per path",
            "HOLD / REPLAN",
        ],
        "disclosure": "정확도·환각률 비교가 아니라, 동일 packet에서 검색·요약 경로와 RippleGate의 업무 구조 차이를 보여주는 통제 경로다. 검색·요약 경로도 source ID는 보존하지만 경로별 상태·계산·REPLAN은 생성하지 않는다.",
    }
