from __future__ import annotations

import json
import http.client
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import Handler, route_user_goal, run_agent, sanitize_planner_plan  # noqa: E402
from llm_adapter import ApprovedLLMClient  # noqa: E402
from measure_effect import build_agent_record, build_manual_record, summarize_records  # noqa: E402
from validate_public_submission import run_public_submission_smoke  # noqa: E402
from benchmark import HOLDOUT_CASES_PATH, forensics_agent, run as run_benchmark  # noqa: E402


DATA = Path(__file__).resolve().parent / "data"


def run_http_smoke() -> dict[str, object]:
    """Exercise the actual browser/API boundary on an ephemeral local port."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    result: dict[str, object] = {}
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/")
        page = connection.getresponse()
        page_body = page.read().decode("utf-8")
        result["root_status"] = page.status
        result["root_contains_title"] = "IC Preflight" in page_body
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/health")
        health = connection.getresponse()
        health_body = json.loads(health.read().decode("utf-8"))
        result["health_status"] = health.status
        result["health_ok"] = health_body.get("status") == "ok"
        result["health_version"] = health_body.get("version")
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        payload = json.dumps({
            "scenario": "period_mismatch",
            "mode": "deterministic",
            "user_goal": "대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘",
        }, ensure_ascii=False).encode("utf-8")
        connection.request(
            "POST",
            "/api/run",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        api = connection.getresponse()
        api_body = json.loads(api.read().decode("utf-8"))
        result["api_status"] = api.status
        result["api_decision"] = api_body.get("status")
        comparison = api_body.get("comparison", {})
        result["comparison_baseline"] = comparison.get("baseline", {}).get("decision")
        result["comparison_forensics"] = comparison.get("forensics", {}).get("decision")
        result["user_goal"] = api_body.get("user_goal")
        result["passed"] = (
            page.status == 200
            and result["root_contains_title"] is True
            and health.status == 200
            and result["health_ok"] is True
            and result["health_version"] == "0.9.2"
            and api.status == 200
            and api_body.get("status") == "hold"
            and result["comparison_baseline"] == "REVIEW"
            and result["comparison_forensics"] == "HOLD"
            and result["user_goal"] == "대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘"
        )
        connection.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    return result


def run_case_packet_http_smoke() -> dict[str, object]:
    """Exercise the local JSON packet contract through the real HTTP boundary."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    result: dict[str, object] = {}
    try:
        packet = json.loads((DATA / "case_packet_template.json").read_text(encoding="utf-8"))
        payload = json.dumps(
            {
                "scenario": "clean",
                "mode": "deterministic",
                "user_goal": "로컬 packet의 FY2025 매출과 EBITDA를 Peer와 비교해줘",
                "case_packet": packet,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("POST", "/api/run", body=payload, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        result["status"] = response.status
        result["case_origin"] = body.get("case_origin")
        result["company"] = body.get("company_name")
        result["decision"] = body.get("investment_pack", {}).get("decision")
        connection.close()

        invalid = dict(packet)
        invalid["schema_version"] = "unsupported.v0"
        invalid_payload = json.dumps(
            {"scenario": "clean", "case_packet": invalid}, ensure_ascii=False
        ).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("POST", "/api/run", body=invalid_payload, headers={"Content-Type": "application/json"})
        invalid_response = connection.getresponse()
        invalid_body = json.loads(invalid_response.read().decode("utf-8"))
        result["invalid_status"] = invalid_response.status
        result["invalid_error"] = invalid_body.get("error")
        connection.close()
        result["passed"] = (
            result["status"] == 200
            and result["case_origin"] == "local_case_packet"
            and result["company"] == "Company A"
            and result["decision"] == "진행"
            and result["invalid_status"] == 400
            and result["invalid_error"] == "invalid_case_packet"
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    return result


def run_observable_policy_smoke() -> dict[str, object]:
    """Prove the holdout policy reads observable signals, not hidden labels."""
    hold_case = {
        "id": "synthetic-period",
        "gold_decision": "REVIEW",
        "fault_type": "clean",
        "typed_state": {"unresolved_critical_issue": "should_not_be_read"},
        "observable_state": {"period_aligned": False},
    }
    pass_case = {
        "id": "synthetic-clean",
        "gold_decision": "HOLD",
        "fault_type": "period_mismatch",
        "typed_state": {"unresolved_critical_issue": "should_not_be_read"},
        "observable_state": {"period_aligned": True},
    }
    hold_result = forensics_agent(hold_case)
    pass_result = forensics_agent(pass_case)
    benchmark_result = run_benchmark(cases_path=HOLDOUT_CASES_PATH)
    metrics = benchmark_result["models"]["forensics_deterministic"]["metrics"]
    passed = (
        hold_result["decision"] == "HOLD"
        and "period_mismatch" in hold_result["reason"]
        and pass_result["decision"] == "REVIEW"
        and benchmark_result.get("observation_policy") == "observable_policy_v1"
        and metrics["critical_error_detection_rate"] == 1.0
        and metrics["false_hold_rate"] == 0.0
    )
    return {
        "passed": passed,
        "policy": benchmark_result.get("observation_policy"),
        "metrics": metrics,
        "hidden_label_ignored": pass_result["decision"] == "REVIEW",
    }


def run_approved_gateway_smoke() -> dict[str, object]:
    """Verify the provider-neutral gateway contract without using a real model."""

    class GatewayHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            prompt = json.dumps(body.get("messages", []), ensure_ascii=False)
            if "Reflection/Critic" in prompt:
                content = {
                    "risk_flags": ["gateway-contract-test"],
                    "challenge": "approved gateway response",
                    "recommended_action": "REVIEW",
                }
            else:
                content = {
                    "plan_steps": ["retrieve primary evidence", "recalculate"],
                    "tool_calls": ["retrieve_primary_filings", "recalculate_valuation", "invent_private_tool"],
                    "risk_flags": [],
                    "needs_replan": False,
                }
            payload = json.dumps(
                {"choices": [{"message": {"content": json.dumps(content)}}]},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), GatewayHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    names = [
        "KIC_LLM_POLICY",
        "KIC_LLM_PROVIDER",
        "KIC_LLM_URL",
        "KIC_LLM_MODEL",
        "KIC_LLM_API_KEY",
        "KIC_LLM_ALLOWED_MODELS",
    ]
    saved = {name: os.environ.get(name) for name in names}
    try:
        os.environ["KIC_LLM_POLICY"] = "approved"
        os.environ["KIC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["KIC_LLM_URL"] = f"http://127.0.0.1:{port}"
        os.environ["KIC_LLM_MODEL"] = "approved-gateway-contract-test"
        os.environ["KIC_LLM_API_KEY"] = "unit-test-secret"
        os.environ["KIC_LLM_ALLOWED_MODELS"] = "approved-gateway-contract-test"
        result = run_agent("conflict", use_llm=True)
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    passed = (
        result["status"] == "ready_for_review"
        and result["agent_runtime"]["planner"]["ok"] is True
        and result["agent_runtime"]["reflection"]["ok"] is True
        and result["agent_runtime"]["provider"] == "openai_compatible"
        and "invent_private_tool" in result["plan"]["unknown_tool_calls"]
        and any(item["node"] == "REPLAN" for item in result["trace"])
    )
    return {
        "passed": passed,
        "status": result["status"],
        "provider": result["agent_runtime"].get("provider"),
        "planner_ok": result["agent_runtime"]["planner"]["ok"],
        "reflection_ok": result["agent_runtime"]["reflection"]["ok"],
        "unknown_tool_calls": result["plan"]["unknown_tool_calls"],
    }


def run_model_allowlist_smoke() -> dict[str, object]:
    """Verify that an unapproved model is rejected before any network call."""
    names = [
        "KIC_LLM_POLICY",
        "KIC_LLM_PROVIDER",
        "KIC_LLM_MODEL",
        "KIC_LLM_ALLOWED_MODELS",
    ]
    saved = {name: os.environ.get(name) for name in names}
    try:
        os.environ["KIC_LLM_POLICY"] = "approved"
        os.environ["KIC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["KIC_LLM_MODEL"] = "unapproved-model"
        os.environ["KIC_LLM_ALLOWED_MODELS"] = "approved-model"
        result = ApprovedLLMClient().generate_json("{}", "allowlist-test")
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    passed = result.get("ok") is False and result.get("error") == "model_not_allowlisted"
    return {
        "passed": passed,
        "ok": result.get("ok"),
        "error": result.get("error"),
        "model": result.get("model"),
    }


def main() -> None:
    clean = run_agent("clean")
    conflict = run_agent("conflict")
    hold = run_agent("hold")
    period_mismatch = run_agent("period_mismatch")
    currency_mismatch = run_agent("currency_mismatch")
    missing_evidence = run_agent("missing_evidence")
    real = run_agent("real")
    auto_period = run_agent("auto", user_goal="대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘")
    auto_real = run_agent("auto", user_goal="Mastercard 공개자료로 Peer screening과 시장가격을 확인해줘")
    case_packet = json.loads((DATA / "case_packet_template.json").read_text(encoding="utf-8"))
    packet_run = run_agent(
        "clean",
        user_goal="로컬 packet의 FY2025 매출과 EBITDA를 Peer와 비교해줘",
        case_packet=case_packet,
    )

    route_holdout = json.loads((DATA / "goal_route_holdout_v1.json").read_text(encoding="utf-8"))
    route_results = [
        {
            "case_id": case["case_id"],
            "expected": case["expected_scenario"],
            "observed": route_user_goal(case["user_goal"])[0],
        }
        for case in route_holdout["cases"]
    ]
    assert all(item["expected"] == item["observed"] for item in route_results)

    assert clean["status"] == "ready_for_review"
    assert clean["investment_pack"]["decision"] == "진행"
    assert clean["investment_pack"]["title"] == "투자심의팩"
    assert clean["investment_pack"]["request"] == clean["user_goal"]
    custom_goal = "Company A의 FY2025와 Peer 3개를 비교해줘"
    assert run_agent("clean", user_goal=custom_goal)["user_goal"] == custom_goal
    assert "투자심의 전 자료·수치·리스크를 확인하는 공개자료 MVP" in clean["investment_pack"]["workflow_position"]
    assert "투자 승인·거래·한도 변경" in clean["investment_pack"]["automation_boundary"]
    assert packet_run["status"] == "ready_for_review"
    assert packet_run["company_name"] == "Company A"
    assert packet_run["case_origin"] == "local_case_packet"
    assert packet_run["investment_pack"]["data_origin"] == "local_case_packet"
    assert packet_run["investment_pack"]["company"] == "Company A"
    assert packet_run["investment_pack"]["decision"] == "진행"
    assert all(len(item["evidence_hash"]) == 64 for item in packet_run["evidence"])
    assert [item["node"] for item in clean["trace"] if item["node"] != "TOOL"] == [
        "PLAN",
        "RETRIEVE",
        "PLAN",
        "NORMALIZE",
        "VERIFY",
        "CALCULATE",
        "CRITIC",
        "MEMO",
    ]
    assert clean["plan"]["controller"] == "typed_policy_v1"
    assert clean["planning_history"][0]["phase"] == "initial"
    assert "retrieve_primary_filings" in clean["planning_history"][0]["requested_tool_calls"]
    assert clean["investment_pack"]["audit_contract"]["planning_history"] == clean["planning_history"]
    assert all(len(item["evidence_hash"]) == 64 for item in clean["evidence"])
    assert clean["investment_pack"]["audit_contract"]["calculator"] == "Decimal"
    assert clean["investment_pack"]["audit_contract"]["final_decision"] == "REVIEW"
    assert len(clean["tool_results"]) == 7
    assert any(
        item["tool"] == "recalculate_valuation"
        and item["phase"] == "initial"
        and item["status"] == "blocked_precondition"
        and item["postcondition_status"] == "not_run"
        and item["postconditions_met"] is False
        for item in clean["tool_results"]
    )
    assert any(
        item["tool"] == "recalculate_valuation"
        and item["phase"] == "verified"
        and item["status"] == "executed"
        and item["postcondition_status"] == "pass"
        and item["postconditions_met"] is True
        for item in clean["tool_results"]
    )
    assert all(item["contract_version"] == "tool_contract_v1" for item in clean["tool_results"])
    assert clean["investment_pack"]["audit_contract"]["tool_contract_version"] == "tool_contract_v1"
    assert clean["investment_pack"]["audit_contract"]["tool_state"]["valuation_recalculated"] is True
    assert clean["investment_pack"]["audit_contract"]["tool_state"]["human_gate_recorded"] is True
    assert any(
        item["tool"] == "request_human_review"
        and item["phase"] == "handoff"
        and item["status"] == "executed"
        and item["postcondition_status"] == "pass"
        for item in clean["tool_results"]
    )
    assert route_user_goal("대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘")[0] == "period_mismatch"
    assert route_user_goal("필수 근거가 부족하니 추가자료를 요청해줘")[0] == "missing_evidence"
    assert route_user_goal("통화가 다르니 환율 기준을 확인해줘")[0] == "currency_mismatch"
    assert auto_period["scenario"] == "period_mismatch"
    assert auto_period["routing"]["mode"] == "auto"
    assert auto_period["status"] == "hold"
    assert auto_period["plan"]["requested_tool_calls"] == [
        "retrieve_primary_filings",
        "normalize_metric_definitions",
        "request_human_review",
    ]
    assert auto_real["scenario"] == "real"
    assert auto_real["routing"]["mode"] == "auto"
    assert conflict["status"] == "ready_for_review"
    assert any(item["node"] == "REPLAN" and item["status"] == "retry" for item in conflict["trace"])
    assert any(
        item["phase"] == "replan"
        and "retrieve_primary_filings" in item["requested_tool_calls"]
        and item["stop_condition"] == "primary_evidence_verified -> CALCULATE"
        for item in conflict["planning_history"]
    )
    assert any(item["phase"] == "replan" for item in conflict["tool_results"])
    assert all(item["verification_status"] == "verified_primary" for item in conflict["evidence"])
    assert hold["status"] == "hold"
    assert hold["investment_pack"]["decision"] == "보류"
    assert any(item["node"] == "TOOL" and item["status"] == "hold" for item in hold["trace"])
    assert len(hold["unresolved"]) == 1
    assert hold["memo"]["decision"] == "HOLD"
    assert period_mismatch["status"] == "hold"
    assert period_mismatch["unresolved"][0]["type"] == "period_mismatch"
    assert period_mismatch["comparison"]["baseline"]["decision"] == "REVIEW"
    assert period_mismatch["comparison"]["forensics"]["decision"] == "HOLD"
    assert period_mismatch["investment_pack"]["decision"] == "보류"
    assert period_mismatch["investment_pack"]["audit_contract"]["calculator"] == "not_run"
    assert period_mismatch["investment_pack"]["audit_contract"]["tool_state"]["human_gate_recorded"] is True
    assert any(item["node"] == "REPLAN" and item["status"] == "hold" for item in period_mismatch["trace"])
    assert any(
        item["phase"] == "replan" and item["stop_condition"] == "period_alignment_unresolved -> HOLD"
        for item in period_mismatch["planning_history"]
    )
    assert currency_mismatch["status"] == "hold"
    assert currency_mismatch["unresolved"][0]["type"] == "currency_mismatch"
    assert currency_mismatch["investment_pack"]["decision"] == "보류"
    assert currency_mismatch["investment_pack"]["audit_contract"]["calculator"] == "not_run"
    assert any(item["node"] == "VERIFY" and item["status"] == "fail" for item in currency_mismatch["trace"])
    assert any(item["node"] == "REPLAN" and item["status"] == "hold" for item in currency_mismatch["trace"])
    assert any(
        item["phase"] == "replan" and item["stop_condition"] == "currency_alignment_unresolved -> HOLD"
        for item in currency_mismatch["planning_history"]
    )
    assert not currency_mismatch["valuation"]
    assert missing_evidence["status"] == "needs_more_info"
    assert missing_evidence["investment_pack"]["decision"] == "추가자료"
    assert missing_evidence["memo"]["decision"] == "REQUEST_INFO"
    assert missing_evidence["missing_evidence"] == ["EBITDA"]
    assert any(item["node"] == "VERIFY" and item["status"] == "fail" for item in missing_evidence["trace"])
    assert any(item["node"] == "REPLAN" and item["status"] == "retry" for item in missing_evidence["trace"])
    assert any(
        item["phase"] == "replan" and item["stop_condition"] == "required_evidence_missing -> REQUEST_INFO"
        for item in missing_evidence["planning_history"]
    )
    assert missing_evidence["valuation"] is None
    assert missing_evidence["investment_pack"]["audit_contract"]["tool_state"]["human_gate_recorded"] is True
    assert any(item["node"] == "TOOL" and item["status"] == "retry" for item in missing_evidence["trace"])
    measured_agent = build_agent_record("TEST-01", "period_mismatch", result=period_mismatch, elapsed_ms=120)
    measured_manual = build_manual_record("TEST-01", 10.0, rework_count=2, source_gaps=1, calculation_inconsistencies=0)
    measured_request_info = build_manual_record("TEST-REQUEST", 4.0, decision="REQUEST_INFO")
    assert measured_request_info["decision"] == "REQUEST_INFO"
    measurement_summary = summarize_records([measured_agent, measured_manual])
    assert measurement_summary["status"] == "insufficient_observations"
    assert measurement_summary["paired_packet_count"] == 1
    assert measurement_summary["comparable_timing_packet_count"] == 0
    assert measurement_summary["paired_packets"][0]["time_saving_rate"] is None
    comparable_agent = build_agent_record(
        "TEST-02",
        "period_mismatch",
        result=period_mismatch,
        elapsed_ms=120,
        observed_minutes=2.0,
        timing_scope="end_to_end_workflow",
    )
    comparable_manual = build_manual_record("TEST-02", 10.0, timing_scope="end_to_end_workflow")
    comparable_summary = summarize_records([comparable_agent, comparable_manual])
    assert comparable_summary["status"] == "ready"
    assert comparable_summary["comparable_timing_packet_count"] == 1
    assert comparable_summary["paired_packets"][0]["time_saving_rate"] == 0.8
    assert real["status"] == "ready_for_review"
    assert real["valuation"]["peer_median"] == 3.6
    assert real["investment_pack"]["audit_contract"]["tool_state"]["human_gate_recorded"] is True
    assert any("Visa" in item["message"] or "V" in item["message"] for item in real["trace"] if item["node"] == "VERIFY")

    plan = sanitize_planner_plan(
        {
            "ok": True,
            "parsed": {
                "tool_calls": ["retrieve SEC 10-K", "invent_private_tool", "recalculate valuation"],
                "needs_replan": True,
            },
        }
    )
    assert plan["requested_tool_calls"] == ["retrieve_primary_filings", "recalculate_valuation"]
    assert plan["unknown_tool_calls"] == ["invent_private_tool"]
    assert plan["needs_replan"] is True

    failure_env_names = [
        "KIC_LLM_POLICY",
        "KIC_LLM_PROVIDER",
        "KIC_LLM_URL",
        "KIC_LLM_MODEL",
        "KIC_LLM_API_KEY",
        "KIC_LLM_ALLOWED_MODELS",
        "KIC_LLM_TIMEOUT",
    ]
    saved_failure_env = {name: os.environ.get(name) for name in failure_env_names}
    try:
        os.environ["KIC_LLM_POLICY"] = "approved"
        os.environ["KIC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["KIC_LLM_URL"] = "http://127.0.0.1:1"
        os.environ["KIC_LLM_MODEL"] = "approved-fallback-test"
        os.environ["KIC_LLM_API_KEY"] = "unit-test-secret"
        os.environ["KIC_LLM_ALLOWED_MODELS"] = "approved-fallback-test"
        os.environ["KIC_LLM_TIMEOUT"] = "1"
        fallback = run_agent("conflict", use_llm=True)
    finally:
        for name, value in saved_failure_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    assert fallback["status"] == "ready_for_review"
    assert fallback["agent_runtime"]["planner"]["ok"] is False
    assert fallback["agent_runtime"]["reflection"]["ok"] is False
    assert any(item["node"] == "PLAN" and item["status"] == "retry" for item in fallback["trace"])
    assert any(item["node"] == "REFLECTION" and item["status"] == "retry" for item in fallback["trace"])

    http_smoke = run_http_smoke()
    assert http_smoke["passed"] is True

    case_packet_http_smoke = run_case_packet_http_smoke()
    assert case_packet_http_smoke["passed"] is True

    observable_policy_smoke = run_observable_policy_smoke()
    assert observable_policy_smoke["passed"] is True

    approved_gateway_smoke = run_approved_gateway_smoke()
    assert approved_gateway_smoke["passed"] is True

    model_allowlist_smoke = run_model_allowlist_smoke()
    assert model_allowlist_smoke["passed"] is True

    saved_submission_env = {
        name: os.environ.get(name)
        for name in (
            "IC_PREFLIGHT_DEMO_URL",
            "IC_PREFLIGHT_GITHUB_URL",
            "IC_PREFLIGHT_VIDEO_URL",
            "IC_PROOF_DEMO_URL",
            "IC_PROOF_GITHUB_URL",
            "IC_PROOF_VIDEO_URL",
        )
    }
    try:
        submission_httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        submission_thread = threading.Thread(target=submission_httpd.serve_forever, daemon=True)
        submission_thread.start()
        submission_port = submission_httpd.server_address[1]
        os.environ["IC_PREFLIGHT_DEMO_URL"] = f"http://127.0.0.1:{submission_port}"
        os.environ["IC_PREFLIGHT_GITHUB_URL"] = f"http://127.0.0.1:{submission_port}"
        os.environ.pop("IC_PREFLIGHT_VIDEO_URL", None)
        os.environ.pop("IC_PROOF_DEMO_URL", None)
        os.environ.pop("IC_PROOF_GITHUB_URL", None)
        os.environ.pop("IC_PROOF_VIDEO_URL", None)
        public_submission_smoke = run_public_submission_smoke()
    finally:
        if "submission_httpd" in locals():
            submission_httpd.shutdown()
            submission_httpd.server_close()
            submission_thread.join(timeout=5)
        for name, value in saved_submission_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    assert public_submission_smoke["passed"] is True

    report = {
        "clean": {
            "status": clean["status"],
            "trace": [item["node"] + ":" + item["status"] for item in clean["trace"]],
            "memo": clean["memo"]["decision"],
        },
        "conflict": {
            "status": conflict["status"],
            "replan": [item["status"] for item in conflict["trace"] if item["node"] == "REPLAN"],
            "evidence": [item["id"] + ":" + item["verification_status"] for item in conflict["evidence"]],
            "memo": conflict["memo"]["decision"],
        },
        "hold": {
            "status": hold["status"],
            "unresolved_count": len(hold["unresolved"]),
            "memo": hold["memo"]["decision"],
        },
        "period_mismatch": {
            "status": period_mismatch["status"],
            "unresolved_type": period_mismatch["unresolved"][0]["type"],
            "baseline": period_mismatch["comparison"]["baseline"]["decision"],
            "forensics": period_mismatch["comparison"]["forensics"]["decision"],
            "memo": period_mismatch["memo"]["decision"],
        },
        "currency_mismatch": {
            "status": currency_mismatch["status"],
            "unresolved_type": currency_mismatch["unresolved"][0]["type"],
            "currencies": currency_mismatch["unresolved"][0].get("currencies", []),
            "memo": currency_mismatch["memo"]["decision"],
        },
        "missing_evidence": {
            "status": missing_evidence["status"],
            "missing_metrics": missing_evidence["missing_evidence"],
            "decision": missing_evidence["investment_pack"]["decision"],
            "memo": missing_evidence["memo"]["decision"],
        },
        "real": {
            "status": real["status"],
            "eligible_peer_count": len(real["valuation"]["peer_rows"]),
            "peer_median": real["valuation"]["peer_median"],
            "memo": real["memo"]["decision"],
        },
        "local_case_packet": {
            "status": packet_run["status"],
            "company": packet_run["company_name"],
            "origin": packet_run["case_origin"],
            "memo": packet_run["memo"]["decision"],
        },
        "llm_failure_fallback": {
            "status": fallback["status"],
            "planner_ok": fallback["agent_runtime"]["planner"]["ok"],
            "reflection_ok": fallback["agent_runtime"]["reflection"]["ok"],
            "retry_nodes": [
                item["node"] for item in fallback["trace"] if item["status"] == "retry"
            ],
        },
        "http_smoke": http_smoke,
        "case_packet_http_smoke": case_packet_http_smoke,
        "observable_policy_smoke": observable_policy_smoke,
        "approved_gateway_smoke": approved_gateway_smoke,
        "model_allowlist_smoke": model_allowlist_smoke,
        "public_submission_smoke": public_submission_smoke,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
