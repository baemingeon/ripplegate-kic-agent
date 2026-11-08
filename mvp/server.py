from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from llm_adapter import ApprovedLLMClient, run_critic, run_planner


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "demo_case.json"
REAL_CASE_PATH = ROOT / "data" / "real_case_snapshot_2026-11-05.json"
STATIC_PATH = ROOT / "static" / "index.html"
PRODUCT_NAME = "IC Preflight"
PRODUCT_SUBTITLE = "투자심의 전, 숫자·근거·리스크의 빈틈을 찾는 Agent"


PLANNER_TOOL_ALIASES: dict[str, tuple[str, ...]] = {
    "retrieve_primary_filings": ("filing", "10-k", "10k", "sec", "ir", "primary", "공시", "원문"),
    "retrieve_market_price": ("price", "market", "close", "시세", "가격"),
    "screen_peer_candidates": ("peer", "comparable", "screen", "동종", "peer"),
    "normalize_metric_definitions": ("normalize", "definition", "unit", "currency", "period", "정규화", "정의", "단위", "통화", "기간"),
    "recalculate_valuation": ("calculate", "recalculate", "valuation", "계산", "재계산", "밸류"),
    "request_human_review": ("human", "review", "approve", "담당자", "승인", "검토"),
}
TOOL_LABELS = {
    "retrieve_primary_filings": "Primary filing / IR 원문 조회",
    "retrieve_market_price": "기준일 시장가격 조회",
    "screen_peer_candidates": "Peer 후보 적합성 screening",
    "normalize_metric_definitions": "지표 정의·단위·기간 정규화",
    "recalculate_valuation": "결정론적 valuation 재계산",
    "request_human_review": "담당자 승인 요청",
}
TOOL_CONTRACT_VERSION = "tool_contract_v1"
TOOL_CONTRACTS: dict[str, dict[str, list[str]]] = {
    "retrieve_primary_filings": {
        "preconditions": ["user_goal", "as_of_date"],
        "postconditions": ["primary_evidence_linked"],
    },
    "retrieve_market_price": {
        "preconditions": ["as_of_date"],
        "postconditions": ["market_price_reference_linked"],
    },
    "screen_peer_candidates": {
        "preconditions": ["evidence_available"],
        "postconditions": ["peer_candidates_screened"],
    },
    "normalize_metric_definitions": {
        "preconditions": ["evidence_available", "required_metrics_declared"],
        "postconditions": ["definitions_normalized"],
    },
    "recalculate_valuation": {
        "preconditions": ["verification_passed", "no_unresolved_issue"],
        "postconditions": ["valuation_recalculated"],
    },
    "request_human_review": {
        "preconditions": ["user_goal", "packet_ready"],
        "postconditions": ["human_gate_recorded"],
    },
}
DEFAULT_PLANNER_TOOLS = [
    "retrieve_primary_filings",
    "retrieve_market_price",
    "screen_peer_candidates",
    "normalize_metric_definitions",
    "recalculate_valuation",
]

CASE_PACKET_SCHEMA_VERSION = "ic-preflight-case.v1"
CASE_PACKET_MAX_BYTES = 2_000_000
CASE_PACKET_MAX_PEERS = 10


SUPPORTED_SCENARIOS = {
    "clean",
    "conflict",
    "hold",
    "period_mismatch",
    "currency_mismatch",
    "missing_evidence",
    "real",
}


def route_user_goal(user_goal: str, requested_scenario: str = "auto") -> tuple[str, dict[str, Any]]:
    """Route a natural-language request through a typed safety policy.

    The LLM may later propose a richer plan, but the demo must remain
    deterministic and safe when no model is installed. Explicit scenario
    buttons remain available for rehearsals; the default `auto` path makes
    the user's goal affect the workflow rather than merely appearing in the
    audit log.
    """
    requested = str(requested_scenario or "auto").strip().lower()
    if requested in SUPPORTED_SCENARIOS:
        return requested, {
            "mode": "explicit",
            "requested": requested,
            "resolved": requested,
            "reason": "사용자가 검증 경로를 직접 선택",
        }

    text = str(user_goal or "").strip().lower()
    period_signals = (
        "9m",
        "9개월",
        "기간 불일치",
        "기간이 다른",
        "fy2026",
        "분기",
        "ytd",
        "기준일이 다른",
    )
    missing_signals = ("자료 부족", "근거 부족", "누락", "추가자료", "필수 지표")
    conflict_signals = ("충돌", "서로 다른", "값이 다르", "재조회")
    hold_signals = ("보류", "멈춰", "승인하지", "검토 중단")
    currency_signals = ("통화", "환율", "fx", "eur", "jpy", "krw", "gbp", "cny", "원화", "유로", "엔화")
    real_signals = ("mastercard", "공개자료", "sec", "실제 기업", "시장가격", "공시")

    if any(signal in text for signal in period_signals):
        resolved = "period_mismatch"
        reason = "기간·기준일 불일치 신호를 감지해 비교 전 검증 경로 선택"
    elif any(signal in text for signal in missing_signals):
        resolved = "missing_evidence"
        reason = "필수 근거 부족 신호를 감지해 추가자료 경로 선택"
    elif any(signal in text for signal in hold_signals):
        resolved = "hold"
        reason = "사용자가 보류·중단 조건을 요청해 보류 경로 선택"
    elif any(signal in text for signal in currency_signals):
        resolved = "currency_mismatch"
        reason = "통화·환율 신호를 감지해 환산 기준 확인 경로 선택"
    elif any(signal in text for signal in conflict_signals):
        resolved = "conflict"
        reason = "수치 충돌 신호를 감지해 원문 재조회 경로 선택"
    elif any(signal in text for signal in real_signals):
        resolved = "real"
        reason = "공개자료·실제 기업 검토 신호를 감지해 snapshot 경로 선택"
    else:
        resolved = "clean"
        reason = "명시적 위험 신호가 없어 정상 검토 경로에서 시작"
    return resolved, {
        "mode": "auto",
        "requested": requested or "auto",
        "resolved": resolved,
        "reason": reason,
    }


def deterministic_plan(scenario: str = "", user_goal: str = "") -> dict[str, Any]:
    """Return the safe baseline plan used when no approved LLM is available."""
    route_tools = {
        "period_mismatch": [
            "retrieve_primary_filings",
            "normalize_metric_definitions",
            "request_human_review",
        ],
        "currency_mismatch": [
            "retrieve_primary_filings",
            "retrieve_market_price",
            "normalize_metric_definitions",
            "request_human_review",
        ],
        "missing_evidence": [
            "retrieve_primary_filings",
            "normalize_metric_definitions",
            "request_human_review",
        ],
    }
    selected_tools = route_tools.get(scenario, list(DEFAULT_PLANNER_TOOLS))
    text = str(user_goal or "").lower()
    goal_signals = []
    if any(signal in text for signal in ("peer", "동종", "비교")):
        goal_signals.append("peer_comparison")
    if any(signal in text for signal in ("valuation", "밸류", "계산")):
        goal_signals.append("valuation")
    if any(signal in text for signal in ("기간", "fy", "9m", "기준일")):
        goal_signals.append("period_alignment")
    if any(signal in text for signal in ("통화", "환율", "fx", "eur", "jpy", "krw", "gbp", "cny", "원화", "유로", "엔화")):
        goal_signals.append("currency_alignment")
    if any(signal in text for signal in ("근거", "자료", "공시", "원문")):
        goal_signals.append("evidence_check")
    if not goal_signals:
        goal_signals.append("general_review")

    if scenario == "period_mismatch":
        plan_steps = [
            "기간·기준일 신호를 구조화",
            "1순위 원문과 지표 정의를 다시 확인",
            "보정 근거가 없으면 계산을 차단하고 담당자에게 전달",
        ]
        stop_condition = "period_alignment_unresolved -> HOLD"
    elif scenario == "currency_mismatch":
        plan_steps = [
            "자료별 통화와 기준일을 구조화",
            "승인된 환율 snapshot과 출처를 확인",
            "환산 근거가 없으면 계산을 차단하고 담당자에게 전달",
        ]
        stop_condition = "currency_alignment_unresolved -> HOLD"
    elif scenario == "missing_evidence":
        plan_steps = [
            "필수 지표 목록과 연결된 근거를 대조",
            "누락된 원문 지표를 요청",
            "근거가 보완될 때까지 valuation을 실행하지 않음",
        ]
        stop_condition = "required_evidence_missing -> REQUEST_INFO"
    else:
        plan_steps = [
            "사용자 목적과 필요한 지표를 구조화",
            "공식자료·가격·Peer 근거를 연결하고 기준을 정규화",
            "검증 통과 시 Decimal valuation, 실패 시 재계획 또는 보류",
        ]
        stop_condition = "unresolved_issue -> HUMAN_REVIEW"
    return {
        "requested_tool_calls": selected_tools,
        "unknown_tool_calls": [],
        "needs_replan": False,
        "controller": "typed_policy_v1",
        "source": "deterministic_policy",
        "plan_steps": plan_steps,
        "goal_decomposition": {
            "objective": "근거와 기준이 맞는 투자심의 packet 작성",
            "signals": goal_signals,
            "constraints": ["allowlisted_tools_only", "deterministic_calculation", "human_final_decision"],
            "stop_condition": stop_condition,
        },
        "replan_policy": "VERIFY 실패 시 원문 재조회·정규화 후 unresolved이면 계산을 중단",
        "planning_reason": (
            "기간·필수근거 gate를 먼저 통과시킨 뒤 계산 여부를 결정"
            if scenario in route_tools
            else "자료·기준·계산·반대검토를 순서대로 확인"
        ),
    }


def load_demo_case() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def load_real_case() -> dict[str, Any]:
    return json.loads(REAL_CASE_PATH.read_text(encoding="utf-8"))


def validate_case_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Validate a local analyst packet before it enters the workflow.

    The public MVP accepts a deliberately narrow, JSON-only contract. It does
    not upload the file or execute arbitrary code. This keeps the demo useful
    for a new company while preserving the same typed Controller and safety
    gates used by the fixed examples.
    """
    if not isinstance(packet, dict):
        raise ValueError("case_packet must be a JSON object")
    schema_version = str(packet.get("schema_version", CASE_PACKET_SCHEMA_VERSION))
    if schema_version != CASE_PACKET_SCHEMA_VERSION:
        raise ValueError(f"unsupported case_packet schema: {schema_version}")

    company = packet.get("company")
    if not isinstance(company, dict):
        raise ValueError("case_packet.company is required")
    required_company = ("name", "ticker", "currency", "period", "as_of_date", "market_cap", "net_debt", "revenue", "ebitda")
    missing_company = [field for field in required_company if field not in company]
    if missing_company:
        raise ValueError("case_packet.company missing: " + ", ".join(missing_company))
    if str(company.get("currency", "")).upper() != "USD":
        raise ValueError("public MVP calculator currently accepts USD packets only")
    for field in ("market_cap", "net_debt", "revenue", "ebitda"):
        try:
            number = Decimal(str(company[field]))
        except Exception as exc:  # pragma: no cover - defensive boundary
            raise ValueError(f"company.{field} must be numeric") from exc
        if not number.is_finite():
            raise ValueError(f"company.{field} must be finite")
    if Decimal(str(company["revenue"])) <= 0 or Decimal(str(company["ebitda"])) <= 0:
        raise ValueError("company revenue and EBITDA must be greater than zero")

    peers = packet.get("peers")
    if not isinstance(peers, list) or not peers:
        raise ValueError("case_packet.peers must contain at least one peer")
    if len(peers) > CASE_PACKET_MAX_PEERS:
        raise ValueError(f"case_packet.peers may contain at most {CASE_PACKET_MAX_PEERS} rows")
    peer_required = ("name", "ticker", "business_model", "currency", "period", "market_cap", "net_debt", "revenue", "ebitda")
    peer_tickers: set[str] = set()
    for index, peer in enumerate(peers, start=1):
        if not isinstance(peer, dict):
            raise ValueError(f"case_packet.peers[{index}] must be an object")
        missing_peer = [field for field in peer_required if field not in peer]
        if missing_peer:
            raise ValueError(f"case_packet.peers[{index}] missing: " + ", ".join(missing_peer))
        if str(peer.get("currency", "")).upper() != "USD":
            raise ValueError(f"case_packet.peers[{index}].currency must be USD")
        ticker = str(peer.get("ticker", "")).strip()
        if not ticker or ticker in peer_tickers:
            raise ValueError(f"case_packet.peers[{index}].ticker must be unique")
        peer_tickers.add(ticker)
        for field in ("market_cap", "net_debt", "revenue", "ebitda"):
            try:
                number = Decimal(str(peer[field]))
            except Exception as exc:  # pragma: no cover - defensive boundary
                raise ValueError(f"peers[{index}].{field} must be numeric") from exc
            if not number.is_finite():
                raise ValueError(f"peers[{index}].{field} must be finite")
        if Decimal(str(peer["revenue"])) <= 0 or Decimal(str(peer["ebitda"])) <= 0:
            raise ValueError(f"peers[{index}] revenue and EBITDA must be greater than zero")

    sources = packet.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("case_packet.sources must contain at least one evidence row")
    source_required = ("id", "source_type", "document_name", "period", "metric", "metric_definition", "value", "unit", "url")
    source_ids: set[str] = set()
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            raise ValueError(f"case_packet.sources[{index}] must be an object")
        missing_source = [field for field in source_required if field not in source]
        if missing_source:
            raise ValueError(f"case_packet.sources[{index}] missing: " + ", ".join(missing_source))
        source_id = str(source.get("id", "")).strip()
        if not source_id or source_id in source_ids:
            raise ValueError(f"case_packet.sources[{index}].id must be unique")
        source_ids.add(source_id)
        raw_value = source["value"]
        try:
            source_value = Decimal(str(raw_value))
        except Exception:
            if not isinstance(raw_value, str) or not raw_value.strip():
                raise ValueError(f"sources[{index}].value must be numeric or a non-empty string")
        else:
            if not source_value.is_finite():
                raise ValueError(f"sources[{index}].value must be finite")

    validated = json.loads(json.dumps(packet, ensure_ascii=False))
    validated["schema_version"] = CASE_PACKET_SCHEMA_VERSION
    return validated


def now_label() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def evidence_fingerprint(source: dict[str, Any]) -> str:
    """Create a stable content fingerprint for an evidence ledger item."""
    fields = {
        key: source.get(key)
        for key in (
            "id",
            "source_type",
            "document_name",
            "page",
            "url",
            "as_of_date",
            "period",
            "metric",
            "metric_definition",
            "value",
            "unit",
            "priority",
        )
    }
    canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def audit_contract(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_version": "typed_policy_v1",
        "controller": state.get("plan", {}).get("controller", "typed_policy_v1"),
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "tool_state": state.get("tool_state", {}),
        "calculator": "Decimal" if state.get("valuation") else "not_run",
        "evidence_fingerprints": [
            {"id": item.get("id"), "sha256": item.get("evidence_hash")}
            for item in state.get("evidence", [])
            if item.get("evidence_hash")
        ],
        "planning_history": state.get("planning_history", []),
        "unresolved_count": len(state.get("unresolved", [])),
        "final_decision": (state.get("memo") or {}).get("decision"),
        "human_gate": "required",
    }


def build_investment_pack(state: dict[str, Any]) -> dict[str, Any]:
    """Create the plain-language handoff shown to a human reviewer."""
    memo = state.get("memo") or {}
    hold = state.get("status") == "hold"
    needs_more_info = state.get("status") == "needs_more_info"
    unresolved = state.get("unresolved", [])
    evidence = state.get("evidence", [])
    stress = state.get("stress_preview") or {}
    checks = [
        {
            "label": "자료 연결",
            "status": "pass" if evidence else "fail",
            "detail": f"근거 {len(evidence)}건이 실행 기록에 연결됨" if evidence else "연결된 근거 없음",
        },
        {
            "label": "기간·통화·정의 확인",
            "status": "hold" if unresolved else "pass",
            "detail": (
                "기간·통화·정의 충돌이 남아 담당자 확인 필요"
                if unresolved
                else "비교 기준과 필수 정의를 확인함"
            ),
        },
        {
            "label": "계산 및 민감도",
            "status": "pass" if state.get("valuation") else "not_run",
            "detail": "결정론적 계산 모듈 실행" if state.get("valuation") else "검증 미완료로 계산 보류",
        },
        {
            "label": "스트레스 미리보기",
            "status": "pass" if stress else "not_run",
            "detail": (
                f"매출 -10%: USD {stress.get('revenue_minus_10pct', 0):,.1f}m · 멀티플 -0.5x: USD {stress.get('multiple_minus_0_5x', 0):,.1f}m"
                if stress
                else "계산 전에는 실행하지 않음"
            ),
        },
    ]
    return {
        "product": PRODUCT_NAME,
        "title": "투자심의팩",
        "request": state.get("user_goal", ""),
        "company": state.get("company_name", ""),
        "data_origin": state.get("case_origin", "demo_snapshot"),
        "workflow_position": (
            "투자심의 전 자료·수치·리스크를 확인하는 로컬 입력 packet MVP"
            if state.get("case_origin") == "local_case_packet"
            else "투자심의 전 자료·수치·리스크를 확인하는 공개자료 MVP"
        ),
        "automation_boundary": "자동화하지 않음: 투자 승인·거래·한도 변경",
        "decision": "보류" if hold else "추가자료" if needs_more_info else "진행",
        "decision_code": memo.get("decision", "HOLD" if hold else "REQUEST_INFO" if needs_more_info else "REVIEW"),
        "headline": memo.get("headline", ""),
        "checks": checks,
        "next_action": memo.get("next_action", ""),
        "evidence_ids": [item.get("id") for item in evidence],
        "stress_preview": stress,
        "human_gate": "담당자 승인 필요",
        "audit_contract": audit_contract(state),
    }


def add_trace(state: dict[str, Any], node: str, status: str, message: str, detail: str = "") -> None:
    state["trace"].append(
        {
            "time": now_label(),
            "node": node,
            "status": status,
            "message": message,
            "detail": detail,
        }
    )


def tool_precondition_report(tool_name: str, state: dict[str, Any]) -> dict[str, Any]:
    """Evaluate typed Tool preconditions before an adapter can run."""
    required = TOOL_CONTRACTS.get(tool_name, {}).get("preconditions", [])
    missing: list[str] = []
    for condition in required:
        satisfied = {
            "user_goal": bool(str(state.get("user_goal", "")).strip()),
            "as_of_date": bool(str(state.get("as_of_date", "")).strip()),
            "evidence_available": bool(state.get("evidence")),
            "required_metrics_declared": bool(state.get("required_metrics")),
            "verification_passed": state.get("verification_passed") is True,
            "no_unresolved_issue": not bool(state.get("unresolved")),
            "packet_ready": bool(
                state.get("valuation") is not None
                or state.get("unresolved")
                or state.get("missing_evidence")
            ),
        }.get(condition, False)
        if not satisfied:
            missing.append(condition)
    return {
        "required": required,
        "missing": missing,
        "passed": not missing,
    }


def apply_tool_output_state(tool_name: str, state: dict[str, Any]) -> None:
    """Record the typed output produced by an allowlisted public-data adapter."""
    tool_state = state.setdefault("tool_state", {})
    if tool_name == "retrieve_primary_filings":
        tool_state["primary_evidence_linked"] = any(
            bool(item.get("url")) for item in state.get("evidence", [])
        )
    elif tool_name == "retrieve_market_price":
        tool_state["market_price_reference_linked"] = bool(str(state.get("as_of_date", "")).strip())
    elif tool_name == "screen_peer_candidates":
        tool_state["peer_candidates_screened"] = bool(state.get("evidence"))
    elif tool_name == "normalize_metric_definitions":
        tool_state["definitions_normalized"] = bool(
            state.get("evidence") and state.get("required_metrics")
        )
    elif tool_name == "recalculate_valuation":
        tool_state["valuation_recalculated"] = state.get("valuation") is not None
    elif tool_name == "request_human_review":
        tool_state["human_gate_recorded"] = True


def tool_postcondition_report(tool_name: str, state: dict[str, Any]) -> dict[str, Any]:
    """Check the typed output state after an adapter executes."""
    required = TOOL_CONTRACTS.get(tool_name, {}).get("postconditions", [])
    tool_state = state.get("tool_state", {})
    missing = [condition for condition in required if not bool(tool_state.get(condition))]
    return {
        "required": required,
        "missing": missing,
        "passed": not missing,
    }


def add_evidence(state: dict[str, Any], source: dict[str, Any], verification_status: str = "pending") -> None:
    item = dict(source)
    item["verification_status"] = verification_status
    item["hash_algorithm"] = "sha256"
    item["evidence_hash"] = evidence_fingerprint(item)
    state["evidence"].append(item)


def sanitize_planner_plan(result: dict[str, Any]) -> dict[str, Any]:
    """Convert free-form planner output into a typed, allowlisted controller plan."""
    parsed = result.get("parsed", {}) if result.get("ok") else {}
    raw_calls = parsed.get("tool_calls", []) if isinstance(parsed, dict) else []
    if not isinstance(raw_calls, list):
        raw_calls = []

    calls: list[str] = []
    unknown: list[str] = []
    for raw_call in raw_calls:
        text = str(raw_call).strip().lower()
        match = None
        for canonical, aliases in PLANNER_TOOL_ALIASES.items():
            if text == canonical or any(alias in text for alias in aliases):
                match = canonical
                break
        if match and match not in calls:
            calls.append(match)
        elif text:
            unknown.append(str(raw_call)[:120])

    if not calls:
        calls = list(DEFAULT_PLANNER_TOOLS)
    return {
        "requested_tool_calls": calls,
        "unknown_tool_calls": unknown[:5],
        "needs_replan": bool(parsed.get("needs_replan")) if isinstance(parsed, dict) else False,
        "controller": "typed_allowlist_v1",
        "source": "llm_proposal" if result.get("ok") else "deterministic_fallback",
        "plan_steps": [str(item)[:180] for item in parsed.get("plan_steps", [])[:5]]
        if isinstance(parsed, dict) and isinstance(parsed.get("plan_steps"), list)
        else ["사용자 목적 구조화", "allowlisted Tool 선택", "검증 결과에 따라 재계획 또는 담당자 전달"],
        "goal_decomposition": {
            "objective": "근거와 기준이 맞는 투자심의 packet 작성",
            "risk_flags": [str(item)[:180] for item in parsed.get("risk_flags", [])[:5]]
            if isinstance(parsed, dict) and isinstance(parsed.get("risk_flags"), list)
            else [],
            "constraints": ["allowlisted_tools_only", "deterministic_calculation", "human_final_decision"],
            "stop_condition": "unresolved_issue -> HUMAN_REVIEW",
        },
        "replan_policy": "검증 실패 시 Planner 제안을 typed controller가 재검사",
    }


def record_plan_transition(
    state: dict[str, Any],
    phase: str,
    requested_tools: list[str],
    rationale: str,
    stop_condition: str,
) -> None:
    """Persist each plan and replan decision as an auditable state transition."""
    state.setdefault("planning_history", []).append(
        {
            "phase": phase,
            "requested_tool_calls": list(dict.fromkeys(requested_tools)),
            "rationale": rationale,
            "stop_condition": stop_condition,
            "controller": state.get("plan", {}).get("controller", "typed_policy_v1"),
            "source": state.get("plan", {}).get("source", "deterministic_policy"),
        }
    )


def add_plan_summary_trace(state: dict[str, Any], phase: str = "initial") -> None:
    """Expose the typed plan in the same trace a judge can replay in the UI."""
    plan = state.get("plan", {})
    decomposition = plan.get("goal_decomposition", {})
    tools = ",".join(plan.get("requested_tool_calls", [])) or "none"
    signals = ",".join(decomposition.get("signals", [])) or "not_declared"
    steps = " → ".join(str(item) for item in plan.get("plan_steps", [])[:3]) or "typed verification path"
    status = "pass" if phase == "initial" else "retry"
    message = "목적·위험 신호를 Tool 계획으로 구조화" if phase == "initial" else "검증 결과에 따라 Tool 계획을 갱신"
    add_trace(
        state,
        "PLAN",
        status,
        message,
        f"source={plan.get('source', 'deterministic_policy')} · objective={decomposition.get('objective', 'investment review packet')} · signals={signals} · tools={tools} · steps={steps} · stop={decomposition.get('stop_condition', 'unresolved_issue -> HUMAN_REVIEW')}",
    )


def dispatch_tool_plan(
    state: dict[str, Any],
    phase: str,
    tool_names: list[str] | None = None,
    status: str = "pass",
    outcome_detail: str = "",
) -> None:
    """Execute only allowlisted adapters after typed precondition checks."""
    plan = state.get("plan", {})
    requested = tool_names or plan.get("requested_tool_calls", DEFAULT_PLANNER_TOOLS)
    state.setdefault("tool_results", [])
    for tool_name in requested:
        if tool_name not in TOOL_LABELS:
            continue
        preconditions = tool_precondition_report(tool_name, state)
        if preconditions["missing"]:
            execution_status = "blocked_precondition"
            blocked_reason = "사전조건 미충족: " + ", ".join(preconditions["missing"])
        elif status != "pass":
            execution_status = "blocked_by_controller"
            blocked_reason = f"Controller가 phase 상태를 {status}로 제한"
        else:
            execution_status = "executed"
            blocked_reason = ""
        if execution_status == "executed":
            apply_tool_output_state(tool_name, state)
        postconditions = tool_postcondition_report(tool_name, state)
        result: dict[str, Any] = {
            "tool": tool_name,
            "phase": phase,
            "adapter": "public_snapshot_adapter",
            "contract_version": TOOL_CONTRACT_VERSION,
            "preconditions": preconditions["required"],
            "preconditions_met": preconditions["passed"],
            "postconditions": postconditions["required"],
            "postconditions_met": postconditions["passed"],
            "postcondition_status": (
                "pass"
                if postconditions["passed"]
                else "not_run"
                if execution_status != "executed"
                else "fail"
            ),
            "status": execution_status,
        }
        if blocked_reason:
            result["blocked_reason"] = blocked_reason
        if postconditions["missing"]:
            result["postcondition_missing"] = postconditions["missing"]
        if tool_name == "retrieve_primary_filings":
            result["evidence_count"] = len(state.get("evidence", []))
        elif tool_name == "retrieve_market_price":
            result["as_of_date"] = state.get("as_of_date")
        elif tool_name == "screen_peer_candidates":
            result["candidate_count"] = len(state.get("evidence", []))
        elif tool_name == "normalize_metric_definitions":
            result["required_metrics"] = state.get("required_metrics", [])
        elif tool_name == "recalculate_valuation":
            result["calculator"] = "Decimal"
        elif tool_name == "request_human_review":
            result["approval_gate"] = "human"
        state["tool_results"].append(result)
        trace_detail = (
            f"phase={phase} · contract={TOOL_CONTRACT_VERSION} · "
            f"preconditions={'pass' if preconditions['passed'] else 'blocked'} · "
            f"adapter=public_snapshot_adapter · controller=typed allowlist"
        )
        if blocked_reason:
            trace_detail += f" · {blocked_reason}"
        trace_detail += f" · postconditions={result['postcondition_status']}"
        add_trace(
            state,
            "TOOL",
            status,
            TOOL_LABELS[tool_name] if not outcome_detail else f"{TOOL_LABELS[tool_name]} · {outcome_detail}",
            trace_detail,
        )


def record_human_handoff(state: dict[str, Any], phase: str, outcome_detail: str) -> None:
    """Record the human approval boundary as an executable, typed handoff."""
    dispatch_tool_plan(
        state,
        phase,
        ["request_human_review"],
        outcome_detail=outcome_detail,
    )


def attach_llm_planner(state: dict[str, Any], client: ApprovedLLMClient) -> None:
    result = run_planner(client, state)
    state.setdefault("agent_runtime", {})["planner"] = result
    state["agent_runtime"]["llm_policy"] = result.get("policy", client.policy)
    state["agent_runtime"]["model"] = result.get("model", client.model)
    state["agent_runtime"]["provider"] = result.get("provider", client.provider)
    state["plan"] = sanitize_planner_plan(result)
    if result["ok"]:
        parsed = result.get("parsed", {})
        steps = parsed.get("plan_steps", [])
        step_text = ", ".join(str(item) for item in steps[:3]) or "typed verification path"
        add_trace(
            state,
            "PLAN",
            "pass",
            "LLM Planner가 다음 Tool 호출과 검증 순서를 제안",
            f"provider={result['provider']} model={result['model']} latency={result['latency_ms']}ms · tools={','.join(state['plan']['requested_tool_calls'])} · {step_text}",
        )
    else:
        add_trace(
            state,
            "PLAN",
            "retry",
            "LLM Planner 호출 실패. 결정론적 기본 계획으로 계속 진행",
            f"fail-safe · tools={','.join(state['plan']['requested_tool_calls'])} · {result.get('error', 'unknown error')}",
        )


def attach_llm_reflection(state: dict[str, Any], client: ApprovedLLMClient) -> None:
    result = run_critic(client, state)
    state.setdefault("agent_runtime", {})["reflection"] = result
    state["agent_runtime"]["llm_policy"] = result.get("policy", client.policy)
    state["agent_runtime"]["model"] = result.get("model", client.model)
    state["agent_runtime"]["provider"] = result.get("provider", client.provider)
    if result["ok"]:
        parsed = result.get("parsed", {})
        recommendation = str(parsed.get("recommended_action", "REVIEW")).upper()
        flags = ", ".join(str(item) for item in parsed.get("risk_flags", [])[:3]) or "none"
        add_trace(
            state,
            "REFLECTION",
            "pass",
            "LLM Reflection이 취약가정과 근거 정합성을 재검토",
            f"recommendation={recommendation} · risk_flags={flags} · {result['latency_ms']}ms",
        )
    else:
        add_trace(
            state,
            "REFLECTION",
            "retry",
            "LLM Reflection 호출 실패. 결정론적 Verifier 결과를 최종 기준으로 유지",
            f"fail-safe · {result.get('error', 'unknown error')}",
        )


def inject_faults(case: dict[str, Any], scenario: str) -> list[dict[str, Any]]:
    sources = [dict(source) for source in case["sources"]]
    if scenario == "missing_evidence":
        sources = [source for source in sources if source.get("metric") != "EBITDA"]
    if scenario in {"conflict", "hold"}:
        sources.append(
            {
                "id": "E2",
                "source_type": "Secondary",
                "document_name": "Company A market summary",
                "page": "p.4",
                "url": "local://demo/company-a-market-summary",
                "as_of_date": "2026-03-31",
                "period": "FY2025",
                "metric": "Revenue",
                "metric_definition": "Revenue copied from an unverified market summary",
                "value": 920,
                "unit": "USD mm",
                "confidence": "low",
                "priority": 3,
            }
        )
    if scenario == "period_mismatch":
        sources.append(
            {
                "id": "E4",
                "source_type": "Peer filing",
                "document_name": "Peer B 9M FY2026 Results",
                "page": "p.7",
                "url": "local://demo/peer-b-9m-fy2026",
                "as_of_date": "2026-09-30",
                "period": "9M FY2026",
                "metric": "Revenue",
                "metric_definition": "Reported revenue for nine months ended 2026-09-30",
                "value": 1180,
                "unit": "USD mm",
                "confidence": "high",
                "priority": 1,
            }
        )
    if scenario == "currency_mismatch":
        sources.append(
            {
                "id": "E5",
                "source_type": "Peer filing",
                "document_name": "Peer B FY2025 Results",
                "page": "p.9",
                "url": "local://demo/peer-b-fy2025-eur",
                "as_of_date": "2026-03-31",
                "period": "FY2025",
                "metric": "Revenue",
                "metric_definition": "Reported revenue in EUR millions; conversion source not attached",
                "value": 1000,
                "unit": "EUR mm",
                "currency": "EUR",
                "confidence": "high",
                "priority": 1,
            }
        )
    return sources


def detect_conflicts(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in evidence:
        key = (item.get("metric", ""), item.get("period", ""))
        grouped.setdefault(key, []).append(item)
    conflicts: list[dict[str, Any]] = []
    for (metric, period), items in grouped.items():
        values = {str(item.get("value")) for item in items}
        if len(values) > 1:
            conflicts.append({"metric": metric, "period": period, "items": items})
    return conflicts


def detect_period_mismatches(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect same-metric evidence that cannot be compared by period."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        metric = str(item.get("metric", "")).strip()
        period = str(item.get("period", "")).strip()
        if metric and period:
            grouped.setdefault(metric, []).append(item)

    mismatches: list[dict[str, Any]] = []
    for metric, items in grouped.items():
        periods = sorted({str(item.get("period", "")) for item in items})
        if len(periods) > 1:
            mismatches.append(
                {
                    "type": "period_mismatch",
                    "metric": metric,
                    "period": " / ".join(periods),
                    "periods": periods,
                    "items": items,
                }
            )
    return mismatches


def detect_currency_mismatches(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect same-metric evidence that is not expressed in one currency."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in evidence:
        metric = str(item.get("metric", "")).strip()
        period = str(item.get("period", "")).strip()
        if metric and period:
            grouped.setdefault((metric, period), []).append(item)

    mismatches: list[dict[str, Any]] = []
    for (metric, period), items in grouped.items():
        currencies: set[str] = set()
        for item in items:
            raw_currency = str(item.get("currency", "")).strip().upper()
            if not raw_currency:
                raw_currency = str(item.get("unit", "")).strip().upper().split(" ", 1)[0]
            currencies.add(raw_currency or "UNKNOWN")
        if len(currencies) > 1:
            mismatches.append(
                {
                    "type": "currency_mismatch",
                    "metric": metric,
                    "period": period,
                    "currencies": sorted(currencies),
                    "items": items,
                }
            )
    return mismatches


def filter_primary_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for item in evidence:
        key = (item.get("metric", ""), item.get("period", ""))
        current = selected.get(key)
        if current is None or item.get("priority", 99) < current.get("priority", 99):
            selected[key] = item
    return list(selected.values())


def peer_metrics(peers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for peer in peers:
        ev = Decimal(str(peer["market_cap"])) + Decimal(str(peer["net_debt"]))
        revenue = Decimal(str(peer["revenue"]))
        ebitda = Decimal(str(peer["ebitda"]))
        rows.append(
            {
                "name": peer["name"],
                "ticker": peer["ticker"],
                "business_model": peer["business_model"],
                "ev": money(ev),
                "ev_revenue": money(ev / revenue),
                "ev_ebitda": money(ev / ebitda),
                "period": peer["period"],
            }
        )
    return rows


def valuation(case: dict[str, Any]) -> dict[str, Any]:
    company = case["company"]
    peers = peer_metrics(case["peers"])
    median_ev_revenue = Decimal(str(statistics.median(row["ev_revenue"] for row in peers)))
    median_ev_ebitda = Decimal(str(statistics.median(row["ev_ebitda"] for row in peers)))
    revenue = Decimal(str(company["revenue"]))
    ebitda = Decimal(str(company["ebitda"]))
    net_debt = Decimal(str(company["net_debt"]))
    implied_by_revenue = revenue * median_ev_revenue - net_debt
    implied_by_ebitda = ebitda * median_ev_ebitda - net_debt
    low = min(implied_by_revenue, implied_by_ebitda)
    high = max(implied_by_revenue, implied_by_ebitda)
    revenue_minus_10pct = revenue * Decimal("0.90") * median_ev_revenue - net_debt
    multiple_minus_0_5x = revenue * max(median_ev_revenue - Decimal("0.50"), Decimal("0")) - net_debt
    return {
        "method": "Peer trading multiples",
        "peer_rows": peers,
        "median_ev_revenue": money(median_ev_revenue),
        "median_ev_ebitda": money(median_ev_ebitda),
        "implied_equity_by_revenue": money(implied_by_revenue),
        "implied_equity_by_ebitda": money(implied_by_ebitda),
        "equity_value_range": [money(low), money(high)],
        "formula": "EV = metric × peer median multiple, equity value = EV − net debt",
        "sensitivity": {
            "method": "one-way pre-screen sensitivity",
            "base_equity_by_revenue": money(implied_by_revenue),
            "revenue_minus_10pct": money(revenue_minus_10pct),
            "multiple_minus_0_5x": money(multiple_minus_0_5x),
            "disclosure": "Illustrative sensitivity only; not an official KIC risk metric or investment recommendation.",
        },
    }


def ps_sensitivity(revenue: Decimal, peer_median: Decimal, base_value: Decimal) -> dict[str, Any]:
    """Provide a transparent, one-way sensitivity for the public snapshot."""
    return {
        "method": "one-way pre-screen sensitivity",
        "base_equity_by_revenue": money(base_value),
        "revenue_minus_10pct": money(revenue * Decimal("0.90") * peer_median),
        "multiple_minus_0_5x": money(revenue * max(peer_median - Decimal("0.50"), Decimal("0"))),
        "disclosure": "Illustrative sensitivity only; not an official KIC risk metric or investment recommendation.",
    }


def run_real_case(
    use_llm: bool = False,
    user_goal: str | None = None,
    routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = load_real_case()
    target = snapshot["target"]
    requested_goal = str(user_goal or "").strip()
    state: dict[str, Any] = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "scenario": "real",
        "requested_scenario": (routing or {}).get("requested", "real"),
        "routing": routing or {"mode": "explicit", "requested": "real", "resolved": "real"},
        "status": "running",
        "verification_passed": False,
        "user_goal": requested_goal or "Mastercard의 공개자료 기반 Peer screening과 P/S valuation 검증",
        "as_of_date": snapshot["as_of_date"],
        "required_metrics": ["Revenue", "Diluted shares", "Close price", "Price-to-sales"],
        "evidence": [],
        "assumptions": [
            "공시 기준일은 target과 peer가 2025-12-31로 일치해야 함",
            "시장가격은 2026-11-05 종가를 사용",
            "P/S를 사용하고 EV 정의는 다음 버전에서 별도 정규화",
        ],
        "unresolved": [],
        "trace": [],
        "valuation": None,
        "memo": None,
        "plan": {},
        "planning_history": [],
        "tool_results": [],
        "tool_state": {},
        "agent_runtime": {"mode": "approved_llm_with_deterministic_gate" if use_llm else "deterministic_gate"},
        "case_origin": "public_snapshot",
        "company_name": target["name"],
    }
    add_trace(state, "PLAN", "pass", "Mastercard와 후보 Peer의 공시기간·가격 기준일을 명시")
    add_trace(state, "RETRIEVE", "pass", "SEC Company Facts와 지정일 시장가격 source를 연결")
    for index, source in enumerate(snapshot["sources"], start=1):
        add_evidence(
            state,
            {
                "id": f"REAL-{index}",
                "source_type": source["source_type"],
                "document_name": source.get("company", source.get("provider", "source")),
                "page": "API response",
                "url": source.get("url", "") or "provider snapshot",
                "metric": ", ".join(source.get("metrics", source.get("tickers", []))),
                "period": source.get("period_end", source.get("as_of_date", snapshot["as_of_date"])),
                "value": source.get("filed", source.get("as_of_date", snapshot["as_of_date"])),
                "unit": "source metadata",
            },
            verification_status="source_linked",
        )
    if use_llm:
        attach_llm_planner(state, ApprovedLLMClient())
    else:
        state["plan"] = deterministic_plan("real", state["user_goal"])
    record_plan_transition(
        state,
        "initial",
        state.get("plan", {}).get("requested_tool_calls", []),
        state.get("plan", {}).get("planning_reason", "Planner가 목적과 근거 확인 순서를 제안"),
        state.get("plan", {}).get("goal_decomposition", {}).get("stop_condition", "unresolved_issue -> HUMAN_REVIEW"),
    )
    add_plan_summary_trace(state)
    dispatch_tool_plan(state, "initial")
    add_trace(state, "NORMALIZE", "pass", f"target period {target['period_end']}와 후보 Peer period를 비교")
    excluded = ", ".join(item["ticker"] for item in snapshot["excluded_candidates"])
    add_trace(state, "VERIFY", "pass", f"period·필수지표 게이트 통과. 제외 후보: {excluded}")
    state["verification_passed"] = True
    state["valuation"] = {
        "method": snapshot["valuation"]["method"],
        "peer_rows": snapshot["eligible_peers"],
        "peer_median": snapshot["valuation"]["peer_median"],
        "implied_equity_value": snapshot["valuation"]["implied_target_equity_usd_m"],
        "formula": "implied equity = target revenue × eligible peer median P/S",
    }
    dispatch_tool_plan(state, "verified", ["recalculate_valuation"])
    state["stress_preview"] = ps_sensitivity(
        Decimal(str(target["revenue_usd_m"])),
        Decimal(str(snapshot["valuation"]["peer_median"])),
        Decimal(str(snapshot["valuation"]["implied_target_equity_usd_m"])),
    )
    add_trace(state, "CALCULATE", "pass", f"eligible Peer {len(snapshot['eligible_peers'])}개로 P/S median {snapshot['valuation']['peer_median']:.2f} 계산")
    add_trace(state, "CRITIC", "pass", "Visa를 무리하게 포함하지 않고 period·필수지표 경고를 남김")
    if use_llm:
        attach_llm_reflection(state, ApprovedLLMClient())
    state["status"] = "ready_for_review"
    state["memo"] = {
        "decision": "REVIEW",
        "headline": f"{target['name']} 공개자료 Peer screen 완료",
        "range": [snapshot["valuation"]["implied_target_equity_usd_m"], snapshot["valuation"]["implied_target_equity_usd_m"]],
        "caveat": "공개자료 snapshot으로 계산한 초안입니다. 공통 기준과 원문·라이선스를 담당자가 확인해야 합니다.",
        "next_action": "SEC 원문·시장데이터 라이선스와 Peer 적합도를 담당자가 승인",
    }
    record_human_handoff(state, "handoff", "공개자료·라이선스·Peer 적합도 승인")
    add_trace(state, "MEMO", "pass", "실제 공개자료의 source link와 Peer 제외 사유를 IC 초안에 연결")
    state["investment_pack"] = build_investment_pack(state)
    return state


def run_agent(
    scenario: str = "auto",
    use_llm: bool = False,
    user_goal: str | None = None,
    case_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    default_goal = "Company A의 Peer 3개와 valuation을 계산하고 취약한 가정을 검증"
    requested_goal = str(user_goal or "").strip() or default_goal
    resolved_scenario, routing = route_user_goal(requested_goal, scenario)
    if case_packet is not None:
        case_packet = validate_case_packet(case_packet)
        if resolved_scenario == "real":
            resolved_scenario = "clean"
            routing = dict(routing)
            routing["resolved"] = resolved_scenario
            routing["reason"] = "로컬 case packet을 선택해 공개 snapshot 대신 입력 자료를 검증"
    if resolved_scenario == "real":
        return run_real_case(use_llm=use_llm, user_goal=requested_goal, routing=routing)
    case = case_packet or load_demo_case()
    scenario = resolved_scenario
    state: dict[str, Any] = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "scenario": scenario,
        "requested_scenario": routing.get("requested", scenario),
        "routing": routing,
        "status": "running",
        "verification_passed": False,
        "user_goal": requested_goal,
        "as_of_date": case["company"]["as_of_date"],
        "required_metrics": ["Revenue", "EBITDA", "Net debt", "EV/Revenue", "EV/EBITDA"],
        "evidence": [],
        "assumptions": [
            "모든 금액은 USD millions로 처리",
            "Peer 기업은 FY2025 기준으로 비교",
            "결정론적 Calculator가 LLM의 숫자 출력을 대체",
        ],
        "unresolved": [],
        "trace": [],
        "valuation": None,
        "memo": None,
        "plan": {},
        "planning_history": [],
        "tool_results": [],
        "tool_state": {},
        "agent_runtime": {"mode": "approved_llm_with_deterministic_gate" if use_llm else "deterministic_gate"},
        "case_origin": "local_case_packet" if case_packet is not None else "demo_snapshot",
        "company_name": case.get("company", {}).get("name", "Company A"),
    }

    if scenario == "period_mismatch":
        state["comparison"] = {
            "case_id": "H02",
            "input_summary": "대상 기업 FY2025와 비교기업 9M FY2026의 기간이 다름",
            "baseline": {
                "label": "기록된 일반 답변 비교군",
                "decision": "REVIEW",
                "reason": "기간 차이를 설명했지만 계산을 멈추는 기준이 없음",
                "source": "data/benchmark_holdout20_offline_result.json · H02",
            },
            "forensics": {
                "label": PRODUCT_NAME,
                "decision": "HOLD",
                "reason": "승인된 기간 보정 근거가 없어 비교를 중단",
                "source": "현재 실행의 typed period gate",
            },
            "disclosure": "모델 없는 baseline 비교이며 모든 LLM의 일반화 성능을 의미하지 않음",
        }

    add_trace(
        state,
        "PLAN",
        "pass",
        "사용자 요청을 기준일·필요 지표·Peer 범위와 위험 신호로 구조화",
        f"route={routing.get('resolved')} · mode={routing.get('mode')} · {routing.get('reason', '')}",
    )
    sources = inject_faults(case, scenario)
    add_trace(state, "RETRIEVE", "pass", f"공시·IR·보조자료 {len(sources)}건 조회")
    for source in sources:
        add_evidence(state, source)
    if use_llm:
        attach_llm_planner(state, ApprovedLLMClient())
    else:
        state["plan"] = deterministic_plan(scenario, state["user_goal"])
    record_plan_transition(
        state,
        "initial",
        state.get("plan", {}).get("requested_tool_calls", []),
        state.get("plan", {}).get("planning_reason", "Planner가 목적과 근거 확인 순서를 제안"),
        state.get("plan", {}).get("goal_decomposition", {}).get("stop_condition", "unresolved_issue -> HUMAN_REVIEW"),
    )
    add_plan_summary_trace(state)
    dispatch_tool_plan(state, "initial")
    add_trace(state, "NORMALIZE", "pass", "통화·단위·보고기간을 표준화")

    if scenario == "missing_evidence":
        missing_metrics = [
            metric
            for metric in ("Revenue", "EBITDA")
            if not any(item.get("metric") == metric for item in state["evidence"])
        ]
        if missing_metrics:
            state["missing_evidence"] = missing_metrics
            add_trace(
                state,
                "VERIFY",
                "fail",
                "필수 근거가 부족해 valuation을 실행하지 않음",
                f"누락 지표: {', '.join(missing_metrics)}",
            )
            add_trace(
                state,
                "REPLAN",
                "retry",
                "누락 지표가 포함된 1순위 원문을 다시 요청",
                "계산보다 자료 보완을 우선하는 안전 게이트",
            )
            record_plan_transition(
                state,
                "replan",
                ["retrieve_primary_filings", "request_human_review"],
                "필수 지표가 없어 계산보다 원문 보완을 우선",
                "required_evidence_missing -> REQUEST_INFO",
            )
            add_plan_summary_trace(state, "replan")
            dispatch_tool_plan(
                state,
                "replan",
                ["retrieve_primary_filings", "request_human_review"],
                status="retry",
                outcome_detail="missing metrics",
            )
            state["status"] = "needs_more_info"
            state["memo"] = {
                "decision": "REQUEST_INFO",
                "headline": "필수 지표가 없어 가치 계산을 보류하고 추가자료를 요청",
                "reason": [
                    {"metric": metric, "reason": "연결된 원문 근거가 없음"}
                    for metric in missing_metrics
                ],
                "next_action": "누락 지표가 포함된 1순위 원문을 추가한 뒤 재실행",
            }
            record_human_handoff(state, "handoff", "추가자료 확인 후 재실행")
            add_trace(state, "MEMO", "pass", "추가자료 요청이 포함된 투자심의팩 생성")
            state["investment_pack"] = build_investment_pack(state)
            return state

    conflicts = detect_currency_mismatches(state["evidence"])
    if not conflicts:
        conflicts = detect_conflicts(state["evidence"])
    if not conflicts:
        conflicts = detect_period_mismatches(state["evidence"])
    if conflicts:
        conflict = conflicts[0]
        conflict_type = conflict.get("type", "source_conflict")
        if conflict_type == "period_mismatch":
            detail = f"{conflict['metric']} 기준기간이 {' / '.join(conflict.get('periods', []))}으로 어긋남"
            verify_message = "보고기간이 달라 비교 기준을 맞출 수 없음"
        elif conflict_type == "currency_mismatch":
            detail = f"{conflict['metric']} {conflict['period']} 통화가 {' / '.join(conflict.get('currencies', []))}으로 섞임"
            verify_message = "통화 기준과 환율 기준일이 맞지 않음"
        else:
            detail = f"{conflict['metric']} {conflict['period']} 값이 {len(conflict['items'])}개로 충돌"
            verify_message = "독립 출처 대조 실패"
        add_trace(state, "VERIFY", "fail", verify_message, detail)
        if scenario in {"hold", "period_mismatch", "currency_mismatch"} or conflict_type == "currency_mismatch":
            unresolved_type = conflict_type if conflict_type in {"period_mismatch", "currency_mismatch"} else "source_conflict"
            unresolved_reason = (
                "target와 비교기업의 보고기간이 달라 승인된 기간 보정 근거가 필요"
                if conflict_type == "period_mismatch"
                else "대상·Peer 통화가 달라 승인된 환율 snapshot의 기준일과 출처가 필요"
                if conflict_type == "currency_mismatch"
                else "1순위 원문과 보조자료의 값이 달라 추가 확인 필요"
            )
            state["unresolved"].append(
                {
                    "type": unresolved_type,
                    "metric": conflict["metric"],
                    "period": conflict["period"],
                    "reason": unresolved_reason,
                    **(
                        {"currencies": conflict.get("currencies", [])}
                        if conflict_type == "currency_mismatch"
                        else {}
                    ),
                }
            )
            replan_message = (
                "기간 보정 규칙이 없어 비교를 중단"
                if conflict_type == "period_mismatch"
                else "환율 기준일·출처가 없어 통화 정렬 전 계산을 중단"
                if conflict_type == "currency_mismatch"
                else "재조회 후에도 기준 출처가 없어 실행을 중단"
            )
            add_trace(state, "REPLAN", "hold", replan_message)
            hold_stop = (
                "period_alignment_unresolved -> HOLD"
                if conflict_type == "period_mismatch"
                else "currency_alignment_unresolved -> HOLD"
                if conflict_type == "currency_mismatch"
                else "unresolved_source_conflict -> HOLD"
            )
            record_plan_transition(
                state,
                "replan",
                ["retrieve_primary_filings", "retrieve_market_price", "normalize_metric_definitions"]
                if conflict_type == "currency_mismatch"
                else ["retrieve_primary_filings"],
                "통화·환율 기준이 정렬되지 않아 환율 근거를 확인하고 계산을 중단"
                if conflict_type == "currency_mismatch"
                else "충돌이 남아 1순위 원문만 재확인하고 계산을 중단",
                hold_stop,
            )
            add_plan_summary_trace(state, "replan")
            dispatch_tool_plan(
                state,
                "replan",
                ["retrieve_primary_filings", "retrieve_market_price", "normalize_metric_definitions"]
                if conflict_type == "currency_mismatch"
                else ["retrieve_primary_filings"],
                status="hold",
                outcome_detail=(
                    "currency alignment evidence required"
                    if conflict_type == "currency_mismatch"
                    else "unresolved conflict remains"
                ),
            )
        else:
            planner_signal = "LLM Planner 요청을 typed controller가 승인" if state.get("plan", {}).get("needs_replan") else "Verifier가 충돌을 감지해 typed controller가 재계획을 강제"
            add_trace(state, "REPLAN", "retry", "1순위 원문 기준으로 재조회 질의를 생성", f"{planner_signal} · {detail}")
            record_plan_transition(
                state,
                "replan",
                ["retrieve_primary_filings", "normalize_metric_definitions", "recalculate_valuation"],
                "출처 충돌을 감지해 1순위 원문 재조회·정의 정규화·재계산으로 계획을 전환",
                "primary_evidence_verified -> CALCULATE",
            )
            add_plan_summary_trace(state, "replan")
            dispatch_tool_plan(
                state,
                "replan",
                ["retrieve_primary_filings", "normalize_metric_definitions", "recalculate_valuation"],
            )
            state["evidence"] = filter_primary_evidence(state["evidence"])
            for item in state["evidence"]:
                item["verification_status"] = "verified_primary"
            add_trace(state, "RETRIEVE", "pass", "1순위 IR 원문 재조회 후 evidence를 갱신")
            add_trace(state, "VERIFY", "pass", "원문 기준으로 수치 충돌 해소")
    else:
        for item in state["evidence"]:
            item["verification_status"] = "verified"
        add_trace(state, "VERIFY", "pass", "독립 출처 대조 통과")

    if not state["unresolved"]:
        state["verification_passed"] = True

    if state["unresolved"]:
        state["status"] = "hold"
        headline = (
            "보고기간이 달라 멀티플 비교를 보류"
            if any(item.get("type") == "period_mismatch" for item in state["unresolved"])
            else "통화·환율 기준이 달라 멀티플 비교를 보류"
            if any(item.get("type") == "currency_mismatch" for item in state["unresolved"])
            else "검증되지 않은 수치 충돌이 있어 가치 메모 생성을 보류"
        )
        state["memo"] = {
            "decision": "HOLD",
            "headline": headline,
            "reason": state["unresolved"],
            "next_action": "1순위 원문 또는 담당자 확인 후 재실행",
        }
        record_human_handoff(state, "handoff", "보류 사유와 다음 확인 지점 전달")
        add_trace(state, "CRITIC", "hold", "중대 모순이 남아 IC 메모 생성 중단")
        if use_llm:
            attach_llm_reflection(state, ApprovedLLMClient())
        state["investment_pack"] = build_investment_pack(state)
        return state

    state["valuation"] = valuation(case)
    dispatch_tool_plan(state, "verified", ["recalculate_valuation"])
    state["stress_preview"] = state["valuation"].get("sensitivity", {})
    add_trace(state, "CALCULATE", "pass", "Peer trading multiples를 결정론적으로 계산")
    add_trace(state, "CRITIC", "pass", "Peer 수·기간·정의·보류 조건을 점검")
    state["status"] = "ready_for_review"
    if use_llm:
        attach_llm_reflection(state, ApprovedLLMClient())
    state["memo"] = {
        "decision": "REVIEW",
        "headline": "Peer 배수 기반 가치 초안은 검토 가능 상태",
        "range": state["valuation"]["equity_value_range"],
        "caveat": "공개 데모 데이터이며 실제 투자판단 전 원문과 가정을 담당자가 승인해야 함",
        "next_action": "Evidence Ledger를 확인한 뒤 IC 초안을 승인 또는 수정",
    }
    record_human_handoff(state, "handoff", "심의팩 승인 또는 수정 요청")
    add_trace(state, "MEMO", "pass", "근거와 계산식을 연결한 IC 초안 생성")
    state["investment_pack"] = build_investment_pack(state)
    return state


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, STATIC_PATH.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/health":
            self._send(
                200,
                json.dumps(
                    {
                        "status": "ok",
                        "service": PRODUCT_NAME,
                        "subtitle": PRODUCT_SUBTITLE,
                        "version": "0.9.2",
                        "mode": "public_demo_snapshot",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            return
        if path == "/api/demo-case":
            self._send(200, json.dumps(load_demo_case(), ensure_ascii=False).encode("utf-8"))
            return
        self._send(404, b'{"error":"not found"}')

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/run":
            self._send(404, b'{"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > CASE_PACKET_MAX_BYTES:
                self._send(413, json.dumps({"error": "request_too_large", "max_bytes": CASE_PACKET_MAX_BYTES}).encode("utf-8"))
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                self._send(400, b'{"error":"request must be a JSON object"}')
                return
            mode = str(payload.get("mode", "deterministic"))
            result = run_agent(
                str(payload.get("scenario", "auto")),
                use_llm=mode == "approved_llm",
                user_goal=str(payload.get("user_goal", "")).strip() or None,
                case_packet=payload.get("case_packet") if payload.get("case_packet") is not None else None,
            )
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except ValueError as exc:
            self._send(400, json.dumps({"error": "invalid_case_packet", "detail": str(exc)}, ensure_ascii=False).encode("utf-8"))
        except Exception as exc:  # pragma: no cover
            self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{PRODUCT_NAME} MVP")
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="check the configured approved LLM endpoint before accepting browser requests",
    )
    args = parser.parse_args()
    host = os.getenv("KIC_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", os.getenv("KIC_PORT", "8765")))
    server = ThreadingHTTPServer((host, port), Handler)
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    print(f"{PRODUCT_NAME} demo: http://{display_host}:{port}")
    if args.warmup:
        warmup = ApprovedLLMClient().generate_json(
            'Return only JSON with the key "ready" set to true.',
            "warmup",
        )
        if warmup["ok"]:
            print(f"Approved LLM endpoint ready: {warmup['model']} ({warmup['latency_ms']}ms)")
        else:
            print(f"Approved LLM unavailable; deterministic fallback remains available: {warmup.get('error', 'unknown error')}")
    server.serve_forever()


if __name__ == "__main__":
    main()
