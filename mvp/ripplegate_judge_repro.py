from __future__ import annotations

import argparse
import copy
import json

from ripplegate_baseline import summary_only_baseline
from ripplegate_llm import validate_planner_proposal
from ripplegate_public_adapter import _host_allowed, validate_public_snapshot
from ripplegate_server import calculate_path, critic_check, default_assumptions, load_graph, run_ripplegate, source_map


def run_controlled_holdout() -> int:
    """Exercise contract violations with controlled local mutations.

    This is a fail-closed contract check, not an accuracy benchmark or a
    claim about unseen production errors. Each mutation is local and the
    expected result is a HOLD or a rejected proposal.
    """
    graph = load_graph("public_snapshot")
    sources = source_map(graph)
    edges = graph.get("edges", [])
    base_edge = copy.deepcopy(edges[0])
    observed_edge = copy.deepcopy(next(edge for edge in edges if edge.get("observed_only")))
    assumptions = default_assumptions(str(base_edge["id"]))
    plan = {"tools": [{"name": "evidence_check"}], "selected_tools": ["evidence_check"]}
    portfolio_gate = {"status": "NOT_REQUESTED"}
    cases: list[dict[str, object]] = []

    def add_case(case_id: str, expected: str, observed: str, detail: str) -> None:
        cases.append({
            "id": case_id,
            "expected": expected,
            "observed": observed,
            "passed": observed == expected,
            "detail": detail,
        })

    missing_edge = copy.deepcopy(base_edge)
    missing_edge["evidence_ids"] = ["MISSING-SOURCE"]
    missing_result = calculate_path(missing_edge, assumptions, sources)
    add_case("missing_evidence", "HOLD", str(missing_result["status"]), str(missing_result["unresolved"]))

    conflict_edge = copy.deepcopy(base_edge)
    conflict_edge["status"] = "HOLD"
    conflict_edge["unresolved"] = ["period_conflict"]
    conflict_result = calculate_path(conflict_edge, assumptions, sources)
    add_case("period_conflict", "HOLD", str(conflict_result["status"]), str(conflict_result["unresolved"]))

    invalid_observation_edge = copy.deepcopy(observed_edge)
    invalid_observation_edge.setdefault("observed", {})["delta"] = None
    invalid_result = calculate_path(invalid_observation_edge, assumptions, sources)
    add_case("invalid_observation", "HOLD", str(invalid_result["status"]), str(invalid_result["evidence_quality"]))

    hold_with_number = {
        "id": "hold-with-number",
        "status": "HOLD",
        "impact": {"low": 1, "base": 2, "high": 3},
        "evidence_ids": ["PUB-UNCTAD-001"],
        "evidence_quality": "linked",
    }
    critic_result = critic_check([hold_with_number], plan, portfolio_gate)
    add_case("hold_number_leak", "HOLD", str(critic_result["status"]), str(critic_result["findings"]))

    inverted_range = {
        "id": "inverted-range",
        "status": "SCENARIO",
        "impact": {"low": 4, "base": 2, "high": 3},
        "evidence_ids": ["PUB-UNCTAD-001"],
        "evidence_quality": "linked",
    }
    range_result = critic_check([inverted_range], plan, portfolio_gate)
    add_case("inverted_impact_range", "HOLD", str(range_result["status"]), str(range_result["findings"]))

    unknown_tool_valid, unknown_tool_reason, _ = validate_planner_proposal({
        "tool_calls": ["invent_tool"],
        "risk_flags": [],
        "needs_replan": False,
    })
    add_case("unknown_tool", "REJECT", "PASS" if unknown_tool_valid else "REJECT", unknown_tool_reason)

    forbidden_valid, forbidden_reason, _ = validate_planner_proposal({
        "tool_calls": ["event_lookup"],
        "risk_flags": [],
        "needs_replan": False,
        "numbers": {"shock": 99},
    })
    add_case("llm_controlled_number", "REJECT", "PASS" if forbidden_valid else "REJECT", forbidden_reason)

    add_case(
        "unsafe_source_url",
        "REJECT",
        "PASS" if _host_allowed("https://unctad.org.evil.example/source") else "REJECT",
        "subdomain-suffix confusion must not pass the exact host allowlist",
    )

    promoted_graph = copy.deepcopy(graph)
    not_loaded_ids = {
        str(source.get("id"))
        for source in promoted_graph.get("sources", [])
        if source.get("verification_status") == "not_loaded"
    }
    promoted_edge = next(edge for edge in promoted_graph["edges"] if not_loaded_ids.intersection(edge.get("evidence_ids", [])))
    promoted_edge["status"] = "INFERRED"
    promoted_edge["unresolved"] = []
    promoted_report = validate_public_snapshot(promoted_graph)
    add_case("not_loaded_source_promotion", "REJECT", "PASS" if promoted_report["passed"] else "REJECT", str(promoted_report["errors"]))

    passed = sum(1 for case in cases if case["passed"])
    overall = passed == len(cases)
    output = {
        "reproduction": "PASS" if overall else "FAIL",
        "mode": "controlled_contract_holdout",
        "case_count": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "cases": cases,
        "disclosure": "통제된 로컬 mutation에 대한 계약·fail-closed 검사이며, 정확도·환각률·실제 업무효과·처음 보는 운영 오류의 탐지율을 의미하지 않음",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if overall else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="One-command RippleGate judge reproduction")
    parser.add_argument("--dataset", default="public_snapshot", choices=("public_snapshot", "synthetic"))
    parser.add_argument("--holdout", action="store_true", help="run controlled contract holdout mutations")
    args = parser.parse_args()
    if args.holdout:
        raise SystemExit(run_controlled_holdout())
    event_id = "event_red_sea" if args.dataset == "public_snapshot" else "event_middle_east"
    common = {
        "dataset": args.dataset,
        "event_id": event_id,
        "horizon_months": 3,
        "user_goal": "이 글로벌 이슈가 어떤 경로로 산업·자산에 전이되는지 확인하고 검토 가능한 영향 범위를 만들어줘.",
    }
    plan = run_ripplegate({**common, "phase": "plan"})
    result = run_ripplegate({**common, "phase": "run", "human_confirmed": True, "assumptions": {}})
    baseline = summary_only_baseline(load_graph(args.dataset), common["user_goal"])
    expected = {"VERIFIED": 1, "SCENARIO": 1, "HOLD": 1}
    if result["status_counts"] != expected:
        raise SystemExit(f"unexpected status_counts: {result['status_counts']} != {expected}")
    if not any(item.get("url", "").startswith("https://") for item in result["evidence_ledger"]):
        raise SystemExit("no HTTPS evidence in ledger")
    if not result["replan"]["triggered"]:
        raise SystemExit("expected a HOLD/REPLAN path")
    if baseline["path_count"] != 0 or baseline["numeric_result"] is not None:
        raise SystemExit("control group unexpectedly produced a typed numeric result")
    output = {
        "reproduction": "PASS",
        "dataset": result["scenario"]["dataset"],
        "scenario": result["scenario"]["title"],
        "planner": {
            "mode": plan["plan"]["planner"]["mode"],
            "selected_tools": plan["plan"]["selected_tools"],
            "tool_selection": plan["plan"]["tool_selection"],
        },
        "plan_trace": [item["stage"] + ":" + item["state"] for item in plan["trace"]],
        "run_trace": [item["stage"] + ":" + item["state"] for item in result["trace"]],
        "status_counts": result["status_counts"],
        "same_input_control_group": {
            "baseline_version": baseline["baseline_version"],
            "path_count": baseline["path_count"],
            "numeric_result": baseline["numeric_result"],
            "controls_absent": baseline["controls_absent"],
        },
        "path_results": [
            {"path": f"{item['from_label']} → {item['to_label']}", "status": item["status"], "impact": item["impact"], "next_action": item["next_action"]}
            for item in result["paths"]
        ],
        "evidence_ids": [item["id"] for item in result["evidence_ledger"]],
        "replan": result["replan"],
        "portfolio_gate": result["portfolio_gate"],
        "planning_history": result["planning_history"],
        "disclosure": result["disclosure"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
