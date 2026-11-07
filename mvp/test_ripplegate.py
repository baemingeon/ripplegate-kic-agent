from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ripplegate_server import critic_check, load_graph, run_ripplegate
from ripplegate_public_adapter import _host_allowed, public_adapter_report
from ripplegate_llm import optional_llm_planner, validate_planner_proposal
from ripplegate_baseline import summary_only_baseline


class RippleGateFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = load_graph()

    def test_plan_requires_human_gate_before_calculation(self) -> None:
        result = run_ripplegate({"phase": "plan", "event_id": "event_middle_east", "horizon_months": 3})
        self.assertEqual(result["phase"], "plan")
        self.assertTrue(result["plan"]["human_gate"]["required"])
        self.assertEqual(result["trace"][-1]["stage"], "HUMAN_GATE")
        self.assertEqual(result["trace"][-1]["state"], "WAIT")

    def test_plan_exposes_typed_tool_selection_contract(self) -> None:
        result = run_ripplegate({"phase": "plan", "event_id": "event_middle_east", "horizon_months": 3})
        selected = result["plan"]["selected_tools"]
        declared = [tool["name"] for tool in result["plan"]["tools"]]
        self.assertTrue(set(selected).issubset(set(declared)))
        self.assertTrue(all(tool["selected"] == (tool["name"] in selected) for tool in result["plan"]["tools"]))
        self.assertIn("request_human_review", selected)
        self.assertEqual(result["plan"]["planner"]["mode"], "deterministic_demo_policy")

    def test_deterministic_planner_selects_minimal_route_for_evidence_only_goal(self) -> None:
        result = run_ripplegate({
            "phase": "plan",
            "event_id": "event_middle_east",
            "horizon_months": 3,
            "user_goal": "원문과 기준일만 확인해줘",
        })
        selected = result["plan"]["selected_tools"]
        self.assertEqual(selected, ["event_lookup", "evidence_check", "request_human_review", "review_pack"])
        self.assertFalse(result["plan"]["tool_selection"]["goal_signals"]["calculation"])
        self.assertEqual(result["plan"]["user_goal"], "원문과 기준일만 확인해줘")

    def test_portfolio_intent_requires_context_before_investment_impact(self) -> None:
        goal = "기존 포트폴리오에 3% 편입해도 되는지 집중도와 투자 영향을 확인해줘"
        plan = run_ripplegate({"phase": "plan", "event_id": "event_middle_east", "horizon_months": 3, "user_goal": goal})
        self.assertIn("portfolio_context_lookup", plan["plan"]["selected_tools"])
        self.assertTrue(plan["plan"]["investment_context"]["required"])
        result = run_ripplegate({"phase": "run", "event_id": "event_middle_east", "horizon_months": 3, "user_goal": goal, "human_confirmed": True, "assumptions": {}})
        self.assertEqual(result["decision"], "REQUEST_INFO")
        self.assertEqual(result["portfolio_gate"]["status"], "REQUEST_INFO")
        self.assertIn("portfolio_context_lookup", result["replan"]["next_tools"])
        self.assertNotIn("portfolio_context", result["review_pack"]["human_action"])

    def test_approved_portfolio_context_adds_sensitivity_index_without_pnl_claim(self) -> None:
        goal = "기존 포트폴리오에 3% 편입해도 되는지 집중도와 투자 영향을 확인해줘"
        context = {
            "schema_version": "ripplegate-portfolio-context.v1",
            "as_of_date": "2026-11-07",
            "target_node_id": "asia_exporters",
            "target_label": "아시아 수출기업 관련 자산",
            "proposed_weight_pct": 3.0,
            "current_exposure_pct": 10.0,
            "limit_pct": 15.0,
        }
        result = run_ripplegate({
            "phase": "run",
            "dataset": "public_snapshot",
            "event_id": "event_red_sea",
            "horizon_months": 3,
            "user_goal": goal,
            "human_confirmed": True,
            "assumptions": {},
            "portfolio_context": context,
        })
        self.assertEqual(result["portfolio_gate"]["status"], "VERIFIED")
        scenario = next(path for path in result["paths"] if path["id"] == "edge_energy_asia_public")
        self.assertAlmostEqual(scenario["portfolio_impact"]["base"], 0.0702, places=4)
        self.assertIn("P&L", result["portfolio_gate"]["disclosure"])

    def test_run_has_deterministic_counts_and_replan(self) -> None:
        result = run_ripplegate({
            "phase": "run",
            "event_id": "event_middle_east",
            "horizon_months": 3,
            "human_confirmed": True,
            "assumptions": {},
        })
        self.assertEqual(result["status_counts"], {"VERIFIED": 1, "SCENARIO": 1, "HOLD": 1})
        self.assertEqual(result["decision"], "PARTIAL_REVIEW_HOLD")
        self.assertTrue(result["replan"]["triggered"])
        self.assertIn("REPLAN", [item["stage"] for item in result["trace"]])
        self.assertEqual(len(result["evidence_ledger"]), 3)
        self.assertEqual(result["replan"]["state"], "AWAITING_SOURCE")
        self.assertIn("market_snapshot", result["replan"]["next_tools"])
        self.assertNotIn("path_calculate", result["replan"]["next_tools"])
        self.assertFalse(result["planning_history"][1]["executed"])

    def test_factgate_precedes_calculator_and_hold_path_is_excluded(self) -> None:
        result = run_ripplegate({
            "phase": "run",
            "event_id": "event_middle_east",
            "horizon_months": 3,
            "human_confirmed": True,
            "assumptions": {},
        })
        stages = [item["stage"] for item in result["trace"]]
        self.assertLess(stages.index("FACTGATE"), stages.index("CALCULATOR"))
        calculator = next(item for item in result["trace"] if item["stage"] == "CALCULATOR")
        self.assertEqual(calculator["state"], "PASS")
        self.assertIn("HOLD 경로는 계산 제외", calculator["message"])

    def test_independent_critic_passes_normal_run_and_is_visible_in_trace(self) -> None:
        result = run_ripplegate({
            "phase": "run",
            "event_id": "event_middle_east",
            "horizon_months": 3,
            "human_confirmed": True,
            "assumptions": {},
        })
        self.assertEqual(result["critic"]["status"], "PASS")
        critic_trace = next(item for item in result["trace"] if item["stage"] == "CRITIC")
        self.assertEqual(critic_trace["state"], "PASS")
        self.assertEqual(critic_trace["actor"], "Deterministic independent check")
        self.assertEqual(result["review_pack"]["critic"]["status"], "PASS")

    def test_independent_critic_holds_inconsistent_path_instead_of_passing(self) -> None:
        plan = {"tools": [{"name": "evidence_check"}], "selected_tools": ["evidence_check"]}
        bad_paths = [{
            "id": "bad_path",
            "status": "HOLD",
            "impact": {"low": 1.0, "base": 1.0, "high": 1.0},
            "evidence_ids": [],
            "evidence_quality": "conflict",
        }]
        result = critic_check(bad_paths, plan, {"status": "NOT_REQUESTED"})
        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(any(finding["code"] == "hold_has_number" for finding in result["findings"]))

    def test_override_is_visible_as_scenario(self) -> None:
        result = run_ripplegate({
            "phase": "run",
            "event_id": "event_middle_east",
            "horizon_months": 3,
            "human_confirmed": True,
            "assumptions": {"edge_shipping_europe": {"shock_pct": 22, "pass_through": 0.7, "exposure": 0.6}},
        })
        shipping = next(path for path in result["paths"] if path["id"] == "edge_shipping_europe")
        self.assertEqual(shipping["status"], "SCENARIO")
        self.assertAlmostEqual(shipping["impact"]["base"], 9.24, places=2)
        self.assertTrue(shipping["assumptions"]["edited"])

    def test_calculation_without_human_confirmation_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "human_confirmed"):
            run_ripplegate({"phase": "run", "event_id": "event_middle_east", "horizon_months": 3})

    def test_invalid_event_and_horizon_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported event_id"):
            run_ripplegate({"phase": "plan", "event_id": "another_event"})
        with self.assertRaisesRegex(ValueError, "horizon_months"):
            run_ripplegate({"phase": "plan", "event_id": "event_middle_east", "horizon_months": 24})

    def test_result_is_json_serializable(self) -> None:
        result = run_ripplegate({
            "phase": "run",
            "event_id": "event_middle_east",
            "horizon_months": 3,
            "human_confirmed": True,
        })
        json.dumps(result, ensure_ascii=False)

    def test_public_snapshot_uses_real_source_metadata_and_observed_path(self) -> None:
        plan = run_ripplegate({
            "phase": "plan",
            "dataset": "public_snapshot",
            "event_id": "event_red_sea",
            "horizon_months": 3,
        })
        result = run_ripplegate({
            "phase": "run",
            "dataset": "public_snapshot",
            "event_id": "event_red_sea",
            "horizon_months": 3,
            "human_confirmed": True,
            "assumptions": {},
        })
        self.assertEqual(plan["dataset"], "public_snapshot")
        observed = next(path for path in result["paths"] if path["id"] == "edge_transit_europe")
        self.assertEqual(observed["status"], "VERIFIED")
        self.assertEqual(observed["impact"]["base"], 30.0)
        self.assertEqual(observed["impact"]["kind"], "observed")
        scenario = next(path for path in result["paths"] if path["id"] == "edge_energy_asia_public")
        self.assertEqual(scenario["impact"]["kind"], "scenario")
        self.assertTrue(any(item["url"].startswith("https://unctad.org/") for item in result["evidence_ledger"]))
        self.assertTrue(any(item["id"] == "PUB-COMTRADE-002" for item in result["evidence_ledger"]))
        self.assertTrue(any(item.get("retrieved_at") == "2026-11-07" for item in result["evidence_ledger"]))
        self.assertTrue(any(item.get("source_type") == "official_public" for item in result["evidence_ledger"]))
        self.assertIn("trade_exposure_query_not_loaded", result["replan"]["reason"])
        self.assertIn("exposure_lookup", result["replan"]["next_tools"])
        self.assertEqual(plan["data_quality"]["status"], "REVIEW_REQUIRED")
        self.assertTrue(plan["data_quality"]["warnings"])
        self.assertEqual(result["data_quality"]["source_count"], 4)

    def test_synthetic_data_quality_is_explicitly_controlled_demo(self) -> None:
        result = run_ripplegate({
            "phase": "run",
            "dataset": "synthetic",
            "event_id": "event_middle_east",
            "horizon_months": 3,
            "human_confirmed": True,
            "assumptions": {},
        })
        self.assertEqual(result["data_quality"]["status"], "CONTROLLED_DEMO")
        self.assertIn("실제 시장자료", result["data_quality"]["warnings"][0])

    def test_public_adapter_fails_closed_on_not_loaded_numeric_edge(self) -> None:
        report = public_adapter_report()
        self.assertTrue(report["passed"])
        self.assertEqual(report["source_count"], 4)
        self.assertTrue(any("not_loaded" in warning for warning in report["warnings"]))

    def test_public_adapter_rejects_missing_provenance_fields(self) -> None:
        graph = json.loads(json.dumps(load_graph("public_snapshot")))
        graph["sources"][0]["retrieved_at"] = ""
        graph["sources"][1]["source_type"] = ""
        report = public_adapter_report()
        self.assertTrue(report["passed"])
        from ripplegate_public_adapter import validate_public_snapshot
        mutated = validate_public_snapshot(graph)
        self.assertFalse(mutated["passed"])
        self.assertTrue(any("retrieved_at" in error for error in mutated["errors"]))
        self.assertTrue(any("source_type" in error for error in mutated["errors"]))

    def test_llm_planner_is_optional_and_cannot_return_controlled_fields(self) -> None:
        disabled = optional_llm_planner("impact review", self.graph, 3)
        self.assertTrue(disabled["fallback"])
        self.assertEqual(disabled["reason"], "llm_disabled_by_policy")
        valid, reason, _ = validate_planner_proposal({"tool_calls": ["event_lookup"], "risk_flags": [], "needs_replan": False})
        self.assertTrue(valid)
        self.assertEqual(reason, "ok")
        valid, reason, _ = validate_planner_proposal({"tool_calls": ["invent_tool"], "risk_flags": []})
        self.assertFalse(valid)
        self.assertEqual(reason, "planner_output_unknown_tool")
        valid, reason, _ = validate_planner_proposal({"tool_calls": ["event_lookup"], "numbers": {"shock": 99}})
        self.assertFalse(valid)
        self.assertIn("controlled_fields", reason)
        valid, reason, _ = validate_planner_proposal({"tool_calls": [], "risk_flags": [], "needs_replan": False, "numbers": {"shock": 99}})
        self.assertFalse(valid)
        self.assertIn("controlled_fields", reason)
        valid, reason, _ = validate_planner_proposal({"tool_calls": [], "risk_flags": [], "needs_replan": False, "debug": {"prompt": "ignore policy"}})
        self.assertFalse(valid)
        self.assertIn("unknown_fields", reason)
        valid, reason, _ = validate_planner_proposal({"tool_calls": ["event_lookup"] * 13, "risk_flags": [], "needs_replan": False})
        self.assertFalse(valid)
        self.assertEqual(reason, "planner_output_too_many_tools")

    def test_llm_allowlist_supports_portfolio_context_without_controlled_outputs(self) -> None:
        valid, reason, proposal = validate_planner_proposal({"tool_calls": ["portfolio_context_lookup", "evidence_check"], "risk_flags": [], "needs_replan": False})
        self.assertTrue(valid)
        self.assertEqual(reason, "ok")
        self.assertEqual(proposal["tool_calls"][0], "portfolio_context_lookup")
        for controlled in ("portfolio_context", "portfolio_impact", "pnl", "limits"):
            valid, reason, _ = validate_planner_proposal({"tool_calls": ["event_lookup"], controlled: {"value": 1}})
            self.assertFalse(valid)
            self.assertIn("controlled_fields", reason)

    def test_approved_gateway_accepts_typed_portfolio_route_and_keeps_numbers_out(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps({
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "tool_calls": ["event_lookup", "portfolio_context_lookup", "evidence_check"],
                        "risk_flags": ["portfolio context must be approved"],
                        "clarifying_question": None,
                        "needs_replan": False,
                    })
                }
            }]
        }).encode("utf-8")
        response.__enter__.return_value = response
        env = {
            "RIPPLEGATE_LLM_MODE": "approved",
            "KIC_LLM_POLICY": "approved",
            "KIC_LLM_PROVIDER": "openai_compatible",
            "KIC_LLM_URL": "http://127.0.0.1:8765",
            "KIC_LLM_MODEL": "approved-model",
            "KIC_LLM_ALLOWED_MODELS": "approved-model",
            "KIC_LLM_API_KEY": "test-only",
        }
        with patch.dict(os.environ, env, clear=False), patch("ripplegate_llm.urllib.request.urlopen", return_value=response):
            result = optional_llm_planner("기존 포트폴리오 편입 비중과 한도를 확인해줘", self.graph, 3)
        self.assertTrue(result["accepted"])
        self.assertFalse(result["fallback"])
        self.assertIn("portfolio_context_lookup", result["proposal"]["tool_calls"])

    def test_public_source_allowlist_rejects_userinfo_and_non_https(self) -> None:
        self.assertTrue(_host_allowed("https://unctad.org/source"))
        self.assertFalse(_host_allowed("https://user:password@unctad.org/source"))
        self.assertFalse(_host_allowed("http://unctad.org/source"))
        self.assertFalse(_host_allowed("https://unctad.org.evil.example/source"))
        self.assertFalse(_host_allowed("https://evil.unctad.org/source"))
        self.assertFalse(_host_allowed("https://unctad.org:8443/source"))

    def test_same_input_control_group_is_weaker_without_claiming_accuracy(self) -> None:
        baseline = summary_only_baseline(self.graph, "impact review")
        self.assertEqual(baseline["path_count"], 0)
        self.assertIsNone(baseline["numeric_result"])
        self.assertIn("HOLD / REPLAN", baseline["controls_absent"])
        self.assertIn("통제 경로", baseline["disclosure"])

    def test_evidence_ledger_exposes_safe_source_link_contract(self) -> None:
        html = (Path(__file__).resolve().parent / "ripplegate_static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("source-link", html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn("원문 확인 · 수치 미로드", html)

    def test_ui_distinguishes_observed_and_scenario_impact_labels(self) -> None:
        html = (Path(__file__).resolve().parent / "ripplegate_static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("관찰값", html)
        self.assertIn("시나리오 계산", html)
        self.assertIn("impact.kind === \"observed\"", html)
        self.assertIn('id="goal"', html)
        self.assertIn("getGoal()", html)
        self.assertIn("다음 후보 Tool", html)
        self.assertIn("Portfolio Gate", html)
        self.assertIn("합성 Portfolio context로 시연", html)
        self.assertIn("portfolio_impact", html)
        self.assertIn("자료유형", html)
        self.assertIn("retrieved_at", html)
        self.assertIn("자료 품질", html)

    def test_paired_console_requires_separate_human_timings(self) -> None:
        html = (Path(__file__).resolve().parent / "ripplegate_pilot_console.html").read_text(encoding="utf-8")
        self.assertIn("Agent end-to-end stopwatch", html)
        self.assertIn("자동 runtime 값은 paired 입력으로 사용하지 않습니다.", html)
        self.assertNotIn('value=${(ms/60000).toFixed(4)}', html)
        self.assertIn("operator ID는 영문·숫자·밑줄·하이픈", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
