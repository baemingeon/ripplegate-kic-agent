from __future__ import annotations

"""Run a reproducible loopback LLM Planner trace for the public demo.

This helper never sends private or portfolio data.  It starts the existing
RippleGate server in-process, calls the plan and run endpoints with the
synthetic public-demo packet, and prints a compact evidence record.  The
model remains optional: the deterministic fallback is still the default.
"""

import argparse
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any

from ripplegate_server import Handler, load_graph


def request_json(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/analyze",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def compact_llm(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": value.get("mode"),
        "accepted": value.get("accepted"),
        "fallback": value.get("fallback"),
        "network_call": value.get("network_call"),
        "provider": value.get("provider"),
        "model": value.get("model"),
        "security_flags": value.get("security_flags", []),
        "reason": value.get("reason"),
        "proposal": value.get("proposal"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="RippleGate loopback LLM Planner trace")
    parser.add_argument("--goal", default="공개 합성 데이터로 글로벌 에너지 충격의 영향 경로와 검증 순서를 구성해줘")
    parser.add_argument("--horizon-months", type=int, default=3)
    args = parser.parse_args()

    graph = load_graph("synthetic")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        common = {
            "dataset": "synthetic",
            "event_id": graph["origin"]["id"],
            "horizon_months": args.horizon_months,
            "user_goal": args.goal,
        }
        plan = request_json(base_url, {**common, "phase": "plan"})
        run = request_json(base_url, {**common, "phase": "run", "human_confirmed": True, "assumptions": {}})
        plan_llm = compact_llm(plan["plan"]["llm_planner"])
        run_llm = compact_llm(run["plan"]["llm_planner"])
        result = {
            "schema_version": "ripplegate-llm-trace.v1",
            "execution": "local_loopback_public_synthetic",
            "input_boundary": {
                "dataset": "synthetic",
                "private_data_sent": False,
                "portfolio_context_sent": False,
                "human_confirmed_before_run": True,
            },
            "plan": {
                "planner_mode": plan["plan"]["planner"]["mode"],
                "llm": plan_llm,
                "selected_tools": plan["plan"]["selected_tools"],
            },
            "run": {
                "planner_mode": run["plan"]["planner"]["mode"],
                "llm": run_llm,
                "decision": run["decision"],
                "status_counts": run["status_counts"],
                "trace": [f"{item['stage']}:{item['state']}" for item in run["trace"]],
                "replan": run["replan"],
            },
            "disclosure": "실제 투자판단·포트폴리오 자료가 아닌 공개 합성 packet의 Planner trace이며, 숫자·가정·승인·거래는 LLM이 통제하지 않는다.",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
