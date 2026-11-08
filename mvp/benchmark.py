from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "data" / "benchmark_cases.json"
HOLDOUT_CASES_PATH = ROOT / "data" / "benchmark_holdout_cases.json"
OBSERVATIONS_PATH = ROOT / "data" / "benchmark_observations_v1.json"


CRITICAL_FAULTS = {
    "period_mismatch",
    "currency_mismatch",
    "unit_mismatch",
    "source_conflict",
    "stale_price",
    "peer_contamination",
    "missing_source",
    "definition_mismatch",
    "fx_stale",
    "scale_mismatch",
    "ttm_fy_mismatch",
    "share_basis_mismatch",
    "price_currency_mismatch",
    "formula_sign_error",
    "business_model_mismatch",
    "missing_footnote",
    "rounding_out_of_tolerance",
}


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_observations(path: Path = OBSERVATIONS_PATH) -> dict[str, Any]:
    """Load observable packet signals separately from gold decisions."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("cases", {}) if isinstance(payload, dict) else {}


def evaluate_observations(observations: dict[str, Any]) -> dict[str, Any]:
    """Apply typed safety rules to observable signals, without reading gold labels."""
    obs = observations if isinstance(observations, dict) else {}
    checks: list[dict[str, Any]] = []
    issue: str | None = None

    def boolean_gate(key: str, fault: str, label: str) -> None:
        nonlocal issue
        value = obs.get(key, True)
        passed = value is not False
        checks.append({"check": key, "label": label, "passed": passed, "value": value})
        if issue is None and not passed:
            issue = fault

    boolean_gate("period_aligned", "period_mismatch", "보고기간 정합성")
    boolean_gate("currency_aligned", "currency_mismatch", "보고통화 정합성")
    boolean_gate("unit_aligned", "unit_mismatch", "단위 정합성")
    boolean_gate("source_reconciled", "source_conflict", "출처 대조")

    age = obs.get("price_age_days")
    age_limit = obs.get("price_age_limit_days", 31)
    age_passed = not isinstance(age, (int, float)) or age <= age_limit
    checks.append({"check": "price_age_days", "label": "가격 기준일", "passed": age_passed, "value": age, "limit": age_limit})
    if issue is None and not age_passed:
        issue = "stale_price"

    boolean_gate("peer_fit", "peer_contamination", "Peer 경제적 적합성")
    boolean_gate("quantitative_claims_sourced", "missing_source", "정량 주장 출처")
    boolean_gate("definition_aligned", "definition_mismatch", "지표 정의 정합성")
    boolean_gate("fx_date_aligned", "fx_stale", "환율 기준일")
    boolean_gate("scale_aligned", "scale_mismatch", "금액 scale 정합성")
    boolean_gate("period_bridge_approved", "ttm_fy_mismatch", "TTM·FY 기간 보정")
    boolean_gate("share_basis_aligned", "share_basis_mismatch", "주식수 기준")
    boolean_gate("price_currency_aligned", "price_currency_mismatch", "가격 통화")
    boolean_gate("formula_sign_valid", "formula_sign_error", "수식 부호")
    boolean_gate("business_model_fit", "business_model_mismatch", "사업모델 적합성")
    boolean_gate("footnotes_complete", "missing_footnote", "각주·원문 위치")

    difference = obs.get("rounding_difference_pct")
    tolerance = obs.get("rounding_tolerance_pct", 1.0)
    rounding_passed = not isinstance(difference, (int, float)) or difference <= tolerance
    checks.append({"check": "rounding_difference_pct", "label": "반올림 허용오차", "passed": rounding_passed, "value": difference, "limit": tolerance})
    if issue is None and not rounding_passed:
        issue = "rounding_out_of_tolerance"

    return {
        "policy": "observable_policy_v1",
        "unresolved_critical_issue": issue,
        "checks": checks,
        "replan_resolved": bool(obs.get("replan_resolved", False)),
    }


def direct_llm_proxy(case: dict[str, Any]) -> dict[str, Any]:
    """Offline proxy for a fluent answer without a typed verification gate."""
    return {
        "decision": "REVIEW",
        "reason": "Proxy returns a plausible answer from the prompt without a typed hold rule.",
        "provider": "offline_proxy",
    }


def rag_proxy(case: dict[str, Any]) -> dict[str, Any]:
    """Offline proxy for retrieval plus answer generation without normalization or critic."""
    fault = case["fault_type"]
    decision = "HOLD" if fault == "missing_source" else "REVIEW"
    return {
        "decision": decision,
        "reason": "Proxy checks whether a source string exists but does not reconcile definitions, periods, or units.",
        "provider": "offline_proxy",
    }


def forensics_agent(case: dict[str, Any]) -> dict[str, Any]:
    """Deterministic control boundary used by the MVP benchmark.

    This is deliberately not presented as an LLM result. It tests the typed
    verification policy that should remain outside free-form generation.
    """
    # The preferred holdout path reads observable signals produced by a
    # normalizer. It deliberately does not read gold_decision, fault_type, or
    # the legacy typed_state fixture.
    observable_state = case.get("observable_state")
    if isinstance(observable_state, dict):
        typed_state = evaluate_observations(observable_state)
        critical_issue = typed_state.get("unresolved_critical_issue")
        if critical_issue:
            return {
                "decision": "HOLD",
                "reason": f"observable policy detected {critical_issue}",
                "provider": "deterministic_forensics",
                "policy": typed_state["policy"],
                "check_trace": typed_state["checks"],
            }
        return {
            "decision": "REVIEW",
            "reason": "observable checks aligned or replan resolved the issue",
            "provider": "deterministic_forensics",
            "policy": typed_state["policy"],
            "check_trace": typed_state["checks"],
        }

    # Legacy smoke cases use only evidence bullets, so infer the policy
    # outcome from those bullets as a backwards-compatible control.
    evidence_text = " ".join(str(item).lower() for item in case.get("evidence", []))
    evidence_signals = {
        "period_mismatch": ("different period", "target fy", "candidate fy"),
        "currency_mismatch": ("target usd", "candidate krw", "no fx"),
        "unit_mismatch": ("millions", "thousands"),
        "source_conflict": ("secondary summary", "ir revenue"),
        "stale_price": ("stale", "price date"),
        "peer_contamination": ("business model", "margin profile"),
        "missing_source": ("no source", "without a source"),
    }
    detected_faults = [
        fault
        for fault, signals in evidence_signals.items()
        if any(signal in evidence_text for signal in signals)
    ]
    if detected_faults:
        fault = detected_faults[0]
        return {
            "decision": "HOLD",
            "reason": f"typed verifier detected {fault}",
            "provider": "deterministic_forensics",
        }
    return {
        "decision": "REVIEW",
        "reason": "evidence and calculation gates passed or replan completed",
        "provider": "deterministic_forensics",
    }


def score(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    gold = [case["gold_decision"] for case in cases]
    predicted = [item["decision"] for item in predictions]
    critical = [index for index, case in enumerate(cases) if case["gold_decision"] == "HOLD"]
    normal = [index for index, case in enumerate(cases) if case["gold_decision"] == "REVIEW"]
    critical_detected = sum(predicted[index] == "HOLD" for index in critical)
    false_holds = sum(predicted[index] == "HOLD" for index in normal)
    accuracy = sum(a == b for a, b in zip(gold, predicted)) / len(cases)

    def rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 3) if denominator else None

    return {
        "decision_accuracy": round(accuracy, 3),
        "critical_error_detection_rate": rate(critical_detected, len(critical)),
        "false_hold_rate": rate(false_holds, len(normal)),
        "critical_case_count": len(critical),
        "normal_case_count": len(normal),
        "counts": dict(Counter(predicted)),
    }


def run(
    *,
    mode: str = "offline",
    max_cases: int | None = None,
    cases_path: Path = CASES_PATH,
) -> dict[str, Any]:
    if mode != "offline":
        raise ValueError("benchmark mode is offline-only; connect an approved LLM through llm_adapter.py")
    cases = load_cases(cases_path)
    if max_cases is not None:
        cases = cases[:max_cases]
    runners = {
        "direct_llm_offline_proxy": direct_llm_proxy,
        "rag_offline_proxy": rag_proxy,
        "forensics_deterministic": forensics_agent,
    }
    disclosure = "Offline proxy smoke test. It is not evidence of a live LLM model's quality."
    result: dict[str, Any] = {
        "disclosure": disclosure,
        "mode": mode,
        "case_set": cases_path.name,
        "case_count": len(cases),
        "gold_distribution": dict(Counter(case["gold_decision"] for case in cases)),
        "observation_policy": "observable_policy_v1" if OBSERVATIONS_PATH.exists() else "legacy_evidence_fallback",
        "models": {},
    }
    observations = load_observations() if OBSERVATIONS_PATH.exists() else {}
    runnable_cases = []
    for case in cases:
        runnable = dict(case)
        if case.get("id") in observations:
            runnable["observable_state"] = observations[case["id"]]
        runnable_cases.append(runnable)
    for name, runner in runners.items():
        predictions = [runner(case) for case in runnable_cases]
        result["models"][name] = {
            "metrics": score(cases, predictions),
            "predictions": [
                {"case_id": case["id"], "gold": case["gold_decision"], **prediction}
                for case, prediction in zip(runnable_cases, predictions)
            ],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="optional JSON output path")
    parser.add_argument("--mode", choices=("offline",), default="offline")
    parser.add_argument("--max-cases", type=int, help="optional limit for a quick smoke run")
    parser.add_argument("--cases", default=str(CASES_PATH), help="JSON case set path")
    args = parser.parse_args()
    result = run(
        mode=args.mode,
        max_cases=args.max_cases,
        cases_path=Path(args.cases),
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
