from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> int:
    required = [
        ROOT / "server.py",
        ROOT / "llm_adapter.py",
        ROOT / "Dockerfile",
        ROOT / "render.yaml",
        ROOT / "DEPLOYMENT.md",
        ROOT / "static" / "index.html",
        ROOT / "test_mvp.py",
        ROOT / "JUDGE_REPRO.md",
        ROOT / "validate_public_submission.py",
        ROOT / "measure_effect.py",
        ROOT / "validate_effect_measurement.py",
        ROOT / "generate_pilot_artifacts.py",
        ROOT / "RELEASE_MANIFEST_v0.9.2.md",
        ROOT / "THIRD_PARTY_NOTICES_v0.9.2.md",
        ROOT / "benchmark.py",
        ROOT / "fetch_real_case.py",
        ROOT / "data" / "demo_case.json",
        ROOT / "data" / "case_packet_template.json",
        ROOT / "data" / "real_case_snapshot_2026-11-05.json",
        ROOT / "data" / "benchmark_holdout20_offline_result.json",
        ROOT / "data" / "benchmark_holdout20_offline_repeat01_result.json",
        ROOT / "data" / "benchmark_observations_v1.json",
        ROOT / "data" / "model_policy_2026-11-07.json",
        ROOT / "data" / "source_policy_2026-11-07.json",
        ROOT / "data" / "ui_run_results_2026-11-07.json",
        ROOT / "data" / "effect_measurement_template.json",
        ROOT / "data" / "goal_route_holdout_v1.json",
        ROOT / "data" / "pilot_measurement_sheet_v0.2.json",
        ROOT / "data" / "pilot_packet_manifest_v0.1.json",
        ROOT / "data" / "pilot_agent_runtime_2026-11-07.json",
        ROOT / "assets" / "ui-real.png",
        ROOT / "assets" / "ui-hold.png",
        ROOT / "assets" / "ui-period-mismatch.png",
        ROOT / "assets" / "ui-currency-mismatch.png",
        ROOT / "assets" / "ui-missing-evidence.png",
        ROOT / "assets" / "ui-local-packet.png",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]

    # Check the archive before importing local modules, because Python creates
    # __pycache__ during a normal rehearsal.
    unwanted = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file() and ("__pycache__" in path.parts or path.suffix == ".pyc")
    ]

    sys.path.insert(0, str(ROOT))
    from server import route_user_goal, run_agent  # type: ignore
    from validate_effect_measurement import build_report, read_json, read_jsonl  # type: ignore
    from test_mvp import run_approved_gateway_smoke, run_case_packet_http_smoke, run_http_smoke, run_model_allowlist_smoke  # type: ignore

    rehearsal = {}
    for scenario, expected in {
        "clean": "ready_for_review",
        "conflict": "ready_for_review",
        "hold": "hold",
        "period_mismatch": "hold",
        "currency_mismatch": "hold",
        "missing_evidence": "needs_more_info",
        "real": "ready_for_review",
    }.items():
        result = run_agent(scenario, use_llm=False)
        human_gate_recorded = bool(
            result.get("investment_pack", {})
            .get("audit_contract", {})
            .get("tool_state", {})
            .get("human_gate_recorded")
        )
        rehearsal[scenario] = {
            "status": result.get("status"),
            "passed": result.get("status") == expected and human_gate_recorded,
            "human_gate_recorded": human_gate_recorded,
        }

    try:
        packet = json.loads((ROOT / "data" / "case_packet_template.json").read_text(encoding="utf-8"))
        packet_result = run_agent(
            "clean",
            user_goal="로컬 packet의 FY2025 매출과 EBITDA를 Peer와 비교해줘",
            case_packet=packet,
        )
        case_packet_smoke = {
            "passed": (
                packet_result.get("status") == "ready_for_review"
                and packet_result.get("case_origin") == "local_case_packet"
                and packet_result.get("investment_pack", {}).get("data_origin") == "local_case_packet"
                and packet_result.get("investment_pack", {}).get("decision") == "진행"
            ),
            "company": packet_result.get("company_name"),
            "status": packet_result.get("status"),
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        case_packet_smoke = {"passed": False, "error": str(exc)}

    static_text = (ROOT / "static" / "index.html").read_text(encoding="utf-8") if (ROOT / "static" / "index.html").exists() else ""
    brand_consistency = "IC Preflight" in static_text and "IC Proof" not in static_text
    investment_pack_export = all(
        marker in static_text
        for marker in (
            'id="download-pack"',
            "function downloadPack()",
            "ic-preflight-investment-pack-",
        )
    )

    holdout = json.loads(
        (ROOT / "data" / "benchmark_holdout20_offline_result.json").read_text(encoding="utf-8")
    ) if (ROOT / "data" / "benchmark_holdout20_offline_result.json").exists() else {}
    repeat = json.loads(
        (ROOT / "data" / "benchmark_holdout20_offline_repeat01_result.json").read_text(encoding="utf-8")
    ) if (ROOT / "data" / "benchmark_holdout20_offline_repeat01_result.json").exists() else {}
    def decisions(payload: dict, model: str) -> list[tuple[str, str]]:
        predictions = payload.get("models", {}).get(model, {}).get("predictions", [])
        return [(str(item.get("case_id")), str(item.get("decision"))) for item in predictions]

    reproducible = (
        all(
            decisions(holdout, model) == decisions(repeat, model)
            for model in ("direct_llm_offline_proxy", "rag_offline_proxy", "forensics_deterministic")
        )
        and holdout.get("case_count") == 20
        and repeat.get("case_count") == 20
        and holdout.get("observation_policy") == "observable_policy_v1"
        and repeat.get("observation_policy") == "observable_policy_v1"
    )
    http_smoke = run_http_smoke()
    case_packet_http_smoke = run_case_packet_http_smoke()
    approved_gateway_smoke = run_approved_gateway_smoke()
    model_allowlist_smoke = run_model_allowlist_smoke()
    try:
        effect_readiness = build_report(
            read_json(ROOT / "data" / "pilot_packet_manifest_v0.1.json"),
            read_json(ROOT / "data" / "pilot_agent_runtime_2026-11-07.json"),
            read_jsonl(ROOT / "data" / "effect_measurement_log.jsonl"),
            log_exists=(ROOT / "data" / "effect_measurement_log.jsonl").exists(),
        )
        effect_readiness_valid = effect_readiness.get("status") in {
            "AWAITING_HUMAN_PAIRING",
            "INCOMPLETE",
            "READY_TO_REPORT",
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        effect_readiness = {"status": "ERROR", "error": str(exc)}
        effect_readiness_valid = False
    try:
        route_holdout = json.loads((ROOT / "data" / "goal_route_holdout_v1.json").read_text(encoding="utf-8"))
        route_observations = [
            {
                "case_id": case.get("case_id"),
                "expected": case.get("expected_scenario"),
                "observed": route_user_goal(str(case.get("user_goal", "")))[0],
            }
            for case in route_holdout.get("cases", [])
        ]
        route_holdout_check = {
            "passed": bool(route_observations)
            and all(item["expected"] == item["observed"] for item in route_observations),
            "case_count": len(route_observations),
            "observations": route_observations,
            "disclosure": route_holdout.get("disclosure", ""),
        }
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        route_holdout_check = {"passed": False, "case_count": 0, "error": str(exc)}
    passed = (
        not missing
        and not unwanted
        and all(item["passed"] for item in rehearsal.values())
        and case_packet_smoke.get("passed") is True
        and brand_consistency
        and investment_pack_export
        and reproducible
        and http_smoke.get("passed") is True
        and case_packet_http_smoke.get("passed") is True
        and approved_gateway_smoke.get("passed") is True
        and model_allowlist_smoke.get("passed") is True
        and effect_readiness_valid
        and route_holdout_check.get("passed") is True
    )
    report = {
        "status": "READY" if passed else "BLOCKED",
        "required_files": {"passed": not missing, "missing": missing},
        "no_cache_artifacts": {"passed": not unwanted, "unwanted": unwanted},
        "deterministic_rehearsal": rehearsal,
        "local_case_packet_smoke": case_packet_smoke,
        "brand_consistency": brand_consistency,
        "investment_pack_export": investment_pack_export,
        "holdout_repeat_match": reproducible,
        "http_smoke": http_smoke,
        "case_packet_http_smoke": case_packet_http_smoke,
        "approved_gateway_smoke": approved_gateway_smoke,
        "model_allowlist_smoke": model_allowlist_smoke,
        "effect_measurement_readiness": effect_readiness,
        "goal_route_holdout": route_holdout_check,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
