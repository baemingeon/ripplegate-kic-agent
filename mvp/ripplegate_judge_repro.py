from __future__ import annotations

import argparse
import json

from ripplegate_baseline import summary_only_baseline
from ripplegate_server import load_graph, run_ripplegate


def main() -> None:
    parser = argparse.ArgumentParser(description="One-command RippleGate judge reproduction")
    parser.add_argument("--dataset", default="public_snapshot", choices=("public_snapshot", "synthetic"))
    args = parser.parse_args()
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
