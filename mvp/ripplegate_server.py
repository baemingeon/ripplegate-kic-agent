from __future__ import annotations

"""RippleGate demo server.

This is intentionally separate from the legacy FactGate demo.  RippleGate
demonstrates the contest concept in one reproducible flow:

    event -> impact path -> agent assumptions -> human confirmation
    -> deterministic calculation -> FactGate -> review pack

The default browser path uses a frozen public snapshot; a synthetic packet is
also available for deterministic error demonstrations. Neither path is a live
investment recommendation or a claim about current markets.
"""

import argparse
import hashlib
import json
import math
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

try:
    from .ripplegate_public_adapter import load_public_snapshot, public_adapter_report
    from .ripplegate_llm import optional_llm_planner
    from .ripplegate_baseline import summary_only_baseline
except ImportError:  # direct `python ripplegate_server.py` execution
    from ripplegate_public_adapter import load_public_snapshot, public_adapter_report
    from ripplegate_llm import optional_llm_planner
    from ripplegate_baseline import summary_only_baseline


ROOT = Path(__file__).resolve().parent
GRAPH_PATH = ROOT / "data" / "ripplegate_demo_graph_v1.json"
PUBLIC_GRAPH_PATH = ROOT / "data" / "ripplegate_public_graph_v1.json"
STATIC_PATH = ROOT / "ripplegate_static" / "index.html"
ASSET_ROOT = ROOT / "assets"
PRODUCT = "RippleGate"
VERSION = "0.1.0-demo"
MAX_BODY_BYTES = 128_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_graph(dataset: str = "synthetic") -> dict[str, Any]:
    normalized = str(dataset or "synthetic").strip().lower()
    if normalized in {"public", "public_snapshot", "official"}:
        return load_public_snapshot(PUBLIC_GRAPH_PATH)
    elif normalized in {"synthetic", "synthetic_demo", "demo"}:
        path = GRAPH_PATH
    else:
        raise ValueError("unsupported dataset")
    return json.loads(path.read_text(encoding="utf-8"))


def graph_hash(graph: dict[str, Any]) -> str:
    payload = json.dumps(graph, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def clamp_number(value: Any, low: float, high: float, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
    if number < low or number > high:
        raise ValueError(f"{label} must be between {low} and {high}")
    return number


def node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node["id"]): node for node in graph.get("nodes", [])}


def source_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(source["id"]): source for source in graph.get("sources", [])}


def data_quality_summary(graph: dict[str, Any]) -> dict[str, Any]:
    """Expose the data boundary as a first-class result, not an invisible policy."""
    dataset = str(graph.get("dataset", "synthetic"))
    sources = graph.get("sources", []) if isinstance(graph.get("sources"), list) else []
    if dataset == "public_snapshot":
        report = public_adapter_report(PUBLIC_GRAPH_PATH)
        return {
            "status": "REVIEW_REQUIRED" if report.get("warnings") else "PASS",
            "status_label": "공개 snapshot · 검토 필요" if report.get("warnings") else "공개 snapshot · provenance 확인",
            "source_count": report.get("source_count", len(sources)),
            "warnings": list(report.get("warnings", [])),
            "calculation_boundary": "not_loaded·미연결 자료는 단일 숫자 계산에서 제외",
            "institutional_boundary": "공개자료는 기관 승인 운영자료로 자동 승격하지 않음",
        }
    return {
        "status": "CONTROLLED_DEMO",
        "status_label": "합성 packet · 통제된 시연 전용",
        "source_count": len(sources),
        "warnings": ["합성·오류 packet은 실제 시장자료나 기관 운영자료가 아님"],
        "calculation_boundary": "사람 확인 후 결정론적 시연 계산만 허용",
        "institutional_boundary": "실제 운용 전 승인 source adapter·라이선스·보안검토 필요",
    }


def default_assumptions(edge_id: str) -> dict[str, Any]:
    """Agent-proposed defaults, deliberately explicit and editable."""
    defaults: dict[str, dict[str, Any]] = {
        "edge_shipping_europe": {
            "duration_months": 3,
            "shock_pct": 18.0,
            "shock_range": [12.0, 24.0],
            "pass_through": 0.60,
            "pass_through_range": [0.45, 0.70],
            "exposure": 0.55,
            "exposure_range": [0.45, 0.65],
            "basis": "연료·운송비 충격이 조달비용으로 전이된다는 가정",
            "basis_source": "SYN-001",
        },
        "edge_energy_asia": {
            "duration_months": 3,
            "shock_pct": 8.0,
            "shock_range": [5.0, 12.0],
            "pass_through": 0.45,
            "pass_through_range": [0.30, 0.55],
            "exposure": 0.70,
            "exposure_range": [0.60, 0.80],
            "basis": "에너지 비용 상승 중 일부가 수출기업 원가로 전이된다는 가정",
            "basis_source": "SYN-002",
        },
        "edge_supply_chain_hold": {
            "duration_months": None,
            "shock_pct": None,
            "shock_range": None,
            "pass_through": None,
            "pass_through_range": None,
            "exposure": None,
            "exposure_range": None,
            "basis": "시장가격과 무역자료의 기준기간 충돌로 가정 생성 중단",
            "basis_source": "SYN-003",
        },
        "edge_transit_europe": {
            "observed_only": True,
            "duration_months": None,
            "shock_pct": None,
            "shock_range": None,
            "pass_through": None,
            "pass_through_range": None,
            "exposure": None,
            "exposure_range": None,
            "basis": "UNCTAD 공개 사례의 항해기간 관찰값",
            "basis_source": "PUB-UNCTAD-001",
        },
        "edge_energy_asia_public": {
            "duration_months": 3,
            "shock_pct": 9.0,
            "shock_range": [5.0, 15.0],
            "pass_through": 0.40,
            "pass_through_range": [0.25, 0.60],
            "exposure": 0.65,
            "exposure_range": [0.50, 0.80],
            "basis": "EIA 유가 관찰 맥락과 항로 우회 evidence를 사용한 시나리오",
            "basis_source": "PUB-EIA-001",
        },
        "edge_trade_exposure_hold": {
            "duration_months": None,
            "shock_pct": None,
            "shock_range": None,
            "pass_through": None,
            "pass_through_range": None,
            "exposure": None,
            "exposure_range": None,
            "basis": "UN Comtrade 국가·HS 코드 query 미로드로 노출도 산출 중단",
            "basis_source": "PUB-COMTRADE-001",
        },
    }
    if edge_id not in defaults:
        raise ValueError(f"unsupported edge: {edge_id}")
    return dict(defaults[edge_id])


def recommend_plan(graph: dict[str, Any], horizon_months: int, user_goal: str = "") -> dict[str, Any]:
    edges = graph.get("edges", [])
    llm_planner = optional_llm_planner(user_goal, graph, horizon_months)
    tool_specs = [
        {"name": "event_lookup", "label": "이슈·기준일 조회", "state": "ready"},
        {"name": "exposure_lookup", "label": "국가·산업 노출 경로 조회", "state": "ready"},
        {"name": "portfolio_context_lookup", "label": "포트폴리오 노출·한도 context 확인", "state": "gated"},
        {"name": "market_snapshot", "label": "시장·무역 snapshot 연결", "state": "ready"},
        {"name": "path_calculate", "label": "경로별 영향 범위 계산", "state": "gated"},
        {"name": "evidence_check", "label": "출처·기간·가정 검증", "state": "gated"},
        {"name": "request_human_review", "label": "사람 검토 요청", "state": "gated"},
        {"name": "review_pack", "label": "사람 검토용 팩 생성", "state": "gated"},
    ]
    goal_text = str(user_goal or "").lower()
    wants_exposure = any(token in goal_text for token in ("노출", "자산", "산업", "포트폴리오", "portfolio", "exposure"))
    wants_portfolio = any(token in goal_text for token in ("포트폴리오", "편입", "비중", "집중도", "한도", "portfolio", "allocation", "concentration", "weight"))
    wants_exposure = wants_exposure or wants_portfolio
    wants_market = any(token in goal_text for token in ("시장", "유가", "가격", "무역", "운송비", "market", "trade", "energy"))
    wants_calculation = any(token in goal_text for token in ("숫자", "수치", "영향", "계산", "범위", "시나리오", "impact", "calculate"))
    has_public_observation = any(bool(edge.get("public_observation")) for edge in edges)
    selected_tools = ["event_lookup"]
    if wants_exposure:
        selected_tools.append("exposure_lookup")
    if wants_portfolio:
        selected_tools.append("portfolio_context_lookup")
    if wants_market or (wants_calculation and has_public_observation):
        selected_tools.append("market_snapshot")
    if wants_calculation:
        selected_tools.append("path_calculate")
    selected_tools.extend(["evidence_check", "request_human_review", "review_pack"])
    selected_tools = list(dict.fromkeys(selected_tools))
    for tool in tool_specs:
        tool["selected"] = str(tool["name"]) in selected_tools
    planner_mode = "deterministic_demo_policy"
    planner_reason = "사용자 목표의 이슈·노출·시장·계산 요구를 읽어 필요한 Tool만 선택하고 근거 검증·사람 게이트를 마지막에 배치"
    if llm_planner.get("accepted"):
        proposal = llm_planner.get("proposal") or {}
        proposed_order = [str(tool) for tool in proposal.get("tool_calls", []) if str(tool) in selected_tools]
        selected_tools = proposed_order + [tool for tool in selected_tools if tool not in proposed_order]
        rank = {name: index for index, name in enumerate(selected_tools)}
        tool_specs.sort(key=lambda tool: rank[str(tool["name"])])
        planner_mode = "approved_gateway_typed_proposal"
        planner_reason = "승인 gateway의 Tool 후보를 allowlist로 정규화한 뒤 영향 경로·가정·근거 검증 순서를 구성"
    return {
        "planner": {
            "name": "RippleGate Planner",
            "mode": planner_mode,
            "reason": planner_reason,
        },
        "llm_planner": llm_planner,
        "selected_tools": selected_tools,
        "user_goal": str(user_goal or "").strip()[:800],
        "tool_selection": {
            "goal_signals": {
                "exposure": wants_exposure,
                "portfolio": wants_portfolio,
                "market": wants_market,
                "calculation": wants_calculation,
            },
            "reason": "요청에 포함된 목적 신호에 따라 최소 실행 경로를 구성하고, 근거 검증·사람 게이트·검토팩은 항상 유지",
        },
        "goal": "글로벌 이슈가 자산·산업에 미치는 영향 범위를 산출하고 투자검토팩으로 전달",
        "tools": tool_specs,
        "steps": [
            "선택한 글로벌 이슈와 분석기간을 구조화",
            f"선택 Tool 실행: {' → '.join(selected_tools)}",
            "영향 경로별 충격·전가율·노출도 기본값을 제안",
            "사람이 기본값을 확인하거나 예외값만 수정",
            "확인된 값만 결정론적 계산기로 전달",
            "근거·기간 충돌을 FactGate에서 검증하고 보류 사유를 기록",
        ],
        "horizon_months": horizon_months,
        "assumptions": {str(edge["id"]): default_assumptions(str(edge["id"])) for edge in edges},
        "human_gate": {
            "required": True,
            "label": "가정 확인 후 계산",
            "note": "Agent가 투자 결정을 내리지 않습니다. 사람 확인 전에는 계산·팩 생성을 실행하지 않습니다.",
        },
        "investment_context": {
            "required": wants_portfolio,
            "schema": "ripplegate-portfolio-context.v1",
            "note": "포트폴리오·편입 목적이면 승인된 노출·한도 context가 없을 때 투자 영향 숫자를 확정하지 않습니다.",
        },
    }


def parse_assumptions(raw: Any, edges: list[dict[str, Any]], horizon_months: int) -> dict[str, dict[str, Any]]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("assumptions must be an object")
    result: dict[str, dict[str, Any]] = {}
    allowed = {"duration_months", "shock_pct", "pass_through", "exposure"}
    for edge in edges:
        edge_id = str(edge["id"])
        base = default_assumptions(edge_id)
        override = raw.get(edge_id, {})
        if override is None:
            override = {}
        if not isinstance(override, dict):
            raise ValueError(f"assumptions.{edge_id} must be an object")
        unknown = set(override) - allowed
        if unknown:
            raise ValueError(f"unsupported assumption fields for {edge_id}: {sorted(unknown)}")
        if edge_id in {"edge_supply_chain_hold", "edge_trade_exposure_hold"} or base.get("observed_only"):
            result[edge_id] = base
            continue
        duration = int(clamp_number(override.get("duration_months", horizon_months), 1, 12, f"{edge_id}.duration_months"))
        shock = clamp_number(override.get("shock_pct", base["shock_pct"]), 0, 100, f"{edge_id}.shock_pct")
        pass_through = clamp_number(override.get("pass_through", base["pass_through"]), 0, 1, f"{edge_id}.pass_through")
        exposure = clamp_number(override.get("exposure", base["exposure"]), 0, 1, f"{edge_id}.exposure")
        current = dict(base)
        current.update({
            "duration_months": duration,
            "shock_pct": shock,
            "pass_through": pass_through,
            "exposure": exposure,
            "edited": bool(override),
        })
        result[edge_id] = current
    return result


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def calculate_path(edge: dict[str, Any], assumptions: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    edge_id = str(edge["id"])
    evidence_ids = [str(item) for item in edge.get("evidence_ids", [])]
    linked_sources = [sources[item] for item in evidence_ids if item in sources]
    unresolved = list(edge.get("unresolved", []))
    if edge.get("status") == "HOLD" or unresolved:
        return {
            "id": edge_id,
            "label": edge.get("impact_summary", edge_id),
            "from": edge.get("from"),
            "to": edge.get("to"),
            "channel": edge.get("channel", ""),
            "lag": edge.get("lag", ""),
            "status": "HOLD",
            "status_label": "HOLD",
            "impact": None,
            "formula": "계산 중단 — 기간 정합성 미확인",
            "evidence_ids": evidence_ids,
            "evidence_quality": "conflict",
            "unresolved": unresolved or ["edge_marked_hold"],
            "next_action": edge.get("next_action", "동일 기준일 자료를 추가한 뒤 재실행"),
            "assumptions": assumptions,
        }
    missing = [item for item in evidence_ids if item not in sources]
    if missing:
        return {
            "id": edge_id,
            "label": edge.get("impact_summary", edge_id),
            "from": edge.get("from"),
            "to": edge.get("to"),
            "channel": edge.get("channel", ""),
            "lag": edge.get("lag", ""),
            "status": "HOLD",
            "status_label": "HOLD",
            "impact": None,
            "formula": "계산 중단 — 연결된 근거 없음",
            "evidence_ids": evidence_ids,
            "evidence_quality": "missing",
            "unresolved": ["evidence_missing"],
            "next_action": "원문 출처를 연결한 뒤 재실행",
            "assumptions": assumptions,
        }
    if edge.get("observed_only"):
        observed = edge.get("observed") if isinstance(edge.get("observed"), dict) else {}
        before = observed.get("before")
        after = observed.get("after")
        delta = observed.get("delta")
        if not all(isinstance(value, (int, float)) for value in (before, after, delta)):
            return {
                "id": edge_id,
                "label": edge.get("impact_summary", edge_id),
                "from": edge.get("from"),
                "to": edge.get("to"),
                "channel": edge.get("channel", ""),
                "lag": edge.get("lag", ""),
                "status": "HOLD",
                "status_label": "HOLD",
                "impact": None,
                "formula": "계산 중단 — 관찰값 필드 누락",
                "evidence_ids": evidence_ids,
                "evidence_quality": "invalid_observation",
                "unresolved": ["observed_value_missing"],
                "next_action": "원문에서 관찰값 필드를 다시 추출",
                "assumptions": assumptions,
            }
        unit = str(observed.get("unit", "관찰 단위"))
        return {
            "id": edge_id,
            "label": edge.get("impact_summary", edge_id),
            "from": edge.get("from"),
            "to": edge.get("to"),
            "channel": edge.get("channel", ""),
            "lag": edge.get("lag", ""),
            "status": "VERIFIED",
            "status_label": "VERIFIED",
            "impact": {"kind": "observed", "low": round(float(delta), 2), "base": round(float(delta), 2), "high": round(float(delta), 2), "unit": unit, "direction": "negative", "observed": {"before": before, "after": after}},
            "formula": f"{before}{unit} → {after}{unit} = +{delta}{unit}",
            "evidence_ids": evidence_ids,
            "evidence_quality": "linked_observation",
            "unresolved": [],
            "next_action": edge.get("next_action", "대상 투자·산업의 실제 노출을 추가 확인"),
            "assumptions": assumptions,
        }
    shock = float(assumptions["shock_pct"])
    pass_through = float(assumptions["pass_through"])
    exposure = float(assumptions["exposure"])
    base = shock * pass_through * exposure
    low = float(assumptions["shock_range"][0]) * float(assumptions["pass_through_range"][0]) * float(assumptions["exposure_range"][0])
    high = float(assumptions["shock_range"][1]) * float(assumptions["pass_through_range"][1]) * float(assumptions["exposure_range"][1])
    inferred = str(edge.get("status", "")).upper() == "INFERRED"
    status = "SCENARIO" if inferred or bool(assumptions.get("edited")) else "VERIFIED"
    return {
        "id": edge_id,
        "label": edge.get("impact_summary", edge_id),
        "from": edge.get("from"),
        "to": edge.get("to"),
        "channel": edge.get("channel", ""),
        "lag": edge.get("lag", ""),
        "status": status,
        "status_label": status,
        "impact": {
            "kind": "scenario",
            "low": round(low, 2),
            "base": round(base, 2),
            "high": round(high, 2),
            "unit": "영향지수 pp",
            "direction": "negative",
        },
        "formula": "충격(%) × 전가율 × 노출도 = 비용 압력 영향지수(pp)",
        "evidence_ids": evidence_ids,
        "evidence_quality": "linked",
        "unresolved": [],
        "next_action": edge.get("next_action", "원문과 가정을 확인한 뒤 담당자가 투자검토에 반영"),
        "assumptions": assumptions,
    }


def critic_check(paths: list[dict[str, Any]], plan: dict[str, Any], portfolio_gate: dict[str, Any]) -> dict[str, Any]:
    """Run an independent, deterministic post-calculation invariant check.

    The critic cannot change assumptions or approve an investment. It only
    checks that the calculator and FactGate kept their contract: HOLD paths
    have no number, numeric ranges are ordered and finite, and every released
    path has evidence. A future LLM critic may add observations, but this
    fail-closed rule check remains the final guard.
    """
    findings: list[dict[str, Any]] = []
    allowed_tools = {str(tool.get("name")) for tool in plan.get("tools", []) if isinstance(tool, dict)}
    unknown_tools = [str(tool) for tool in plan.get("selected_tools", []) if str(tool) not in allowed_tools]
    if unknown_tools:
        findings.append({"code": "unknown_tool", "detail": ",".join(unknown_tools)})

    for path in paths:
        path_id = str(path.get("id", "unknown"))
        status = str(path.get("status", ""))
        impact = path.get("impact")
        evidence_ids = path.get("evidence_ids")
        if status not in {"VERIFIED", "SCENARIO", "HOLD"}:
            findings.append({"code": "unknown_path_status", "path_id": path_id, "detail": status})
        if status == "HOLD" and impact is not None:
            findings.append({"code": "hold_has_number", "path_id": path_id, "detail": "HOLD path must have null impact"})
        if status in {"VERIFIED", "SCENARIO"} and not isinstance(impact, dict):
            findings.append({"code": "released_path_missing_impact", "path_id": path_id, "detail": "released path has no impact object"})
        if status != "HOLD" and not isinstance(evidence_ids, list):
            findings.append({"code": "released_path_missing_evidence", "path_id": path_id, "detail": "released path has no evidence_ids"})
        if isinstance(impact, dict):
            values = [impact.get(key) for key in ("low", "base", "high")]
            if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in values):
                findings.append({"code": "non_finite_impact", "path_id": path_id, "detail": "impact range must be finite"})
            elif not (float(values[0]) <= float(values[1]) <= float(values[2])):
                findings.append({"code": "impact_range_inverted", "path_id": path_id, "detail": "low <= base <= high is required"})
        if status != "HOLD" and path.get("evidence_quality") in {"missing", "conflict", "invalid_observation"}:
            findings.append({"code": "released_path_bad_evidence", "path_id": path_id, "detail": str(path.get("evidence_quality"))})

    passed = not findings
    return {
        "status": "PASS" if passed else "HOLD",
        "actor": "Deterministic independent check",
        "findings": findings,
        "checked": [
            "HOLD 경로는 숫자를 갖지 않음",
            "영향 범위는 유한하고 low ≤ base ≤ high를 만족함",
            "확정 경로는 근거 ID를 가짐",
            "선택 Tool은 allowlist 안에 있음",
        ],
        "next_action": "검토팩을 사람에게 전달" if passed else "Critic finding을 해소한 뒤 FactGate부터 재실행",
        "portfolio_gate_status": str(portfolio_gate.get("status", "NOT_REQUESTED")),
    }


def ledger_entry(source: dict[str, Any], edge: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": source["id"],
        "title": source.get("title", source["id"]),
        "issuer": source.get("issuer", ""),
        "period": source.get("period", ""),
        "published_at": source.get("published_at", ""),
        "retrieved_at": source.get("retrieved_at", ""),
        "source_type": source.get("source_type", ""),
        "verification_status": source.get("verification_status", "unknown"),
        "linked_path": edge.get("id") if edge else None,
        "url": source.get("url"),
        "note": source.get("note", ""),
    }


def build_trace(graph: dict[str, Any], plan: dict[str, Any], paths: list[dict[str, Any]], phase: str, critic: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    now = utc_now()
    status_counts = {key: sum(1 for path in paths if path["status"] == key) for key in ("VERIFIED", "SCENARIO", "HOLD")}
    selected_tools = plan.get("selected_tools", [])
    trace: list[dict[str, Any]] = [
        {"stage": "PLANNER", "state": "PASS", "actor": "Agent", "message": "목적을 이슈·경로·가정·근거 검증 작업으로 분해", "at": now},
        {"stage": "TOOL", "state": "PASS", "actor": "Controller", "message": f"{' → '.join(str(tool) for tool in selected_tools)} 선택·실행", "at": now},
    ]
    if phase == "plan":
        trace.extend([
            {"stage": "ASSUMPTION", "state": "WAIT", "actor": "Agent", "message": "추천 가정을 사람 확인 대기 상태로 전달", "at": now},
            {"stage": "HUMAN_GATE", "state": "WAIT", "actor": "Human", "message": "확인 전에는 계산·검토팩 생성 금지", "at": now},
        ])
        return trace
    trace.append({"stage": "HUMAN_GATE", "state": "PASS", "actor": "Human", "message": "추천 가정 확인 완료; 예외 수정값 포함", "at": now})
    if status_counts["HOLD"]:
        trace.append({"stage": "FACTGATE", "state": "HOLD", "actor": "Deterministic", "message": f"{status_counts['HOLD']}개 경로의 기간·근거 충돌을 먼저 차단", "at": now})
        trace.append({"stage": "REPLAN", "state": "PASS", "actor": "Agent", "message": "충돌 경로는 원문 재조회 단계로 되돌리고 전체 승인 대신 부분 검토팩 생성", "at": now})
    else:
        trace.append({"stage": "FACTGATE", "state": "PASS", "actor": "Deterministic", "message": "출처·기간·수식·가정 상태를 먼저 확인", "at": now})
    ready_count = status_counts["VERIFIED"] + status_counts["SCENARIO"]
    if ready_count:
        trace.append({"stage": "CALCULATOR", "state": "PASS", "actor": "Deterministic", "message": f"FactGate 통과 {ready_count}개 경로만 영향 범위로 계산; HOLD 경로는 계산 제외", "at": now})
    else:
        trace.append({"stage": "CALCULATOR", "state": "HOLD", "actor": "Deterministic", "message": "FactGate 통과 경로가 없어 계산하지 않음", "at": now})
    critic = critic or {"status": "PASS", "findings": []}
    critic_message = "수치 범위·HOLD 경로·근거 ID·Tool allowlist 불변식 확인"
    if critic.get("findings"):
        critic_message = f"{len(critic['findings'])}개 불변식 위반을 확인해 추가 계산을 중단"
    trace.append({"stage": "CRITIC", "state": critic.get("status", "HOLD"), "actor": "Deterministic independent check", "message": critic_message, "at": now})
    trace.append({"stage": "REVIEW_PACK", "state": "PASS", "actor": "Agent", "message": "사람이 검토할 숫자·범위·보류 사유·다음 행동을 묶음", "at": now})
    return trace


def build_portfolio_gate(plan: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    required = bool(plan.get("tool_selection", {}).get("goal_signals", {}).get("portfolio"))
    if not required:
        return {
            "required": False,
            "status": "NOT_REQUESTED",
            "status_label": "포트폴리오 context 미요청",
            "next_action": "필요할 때 승인된 포트폴리오 context를 연결",
        }
    context = payload.get("portfolio_context")
    if context is None:
        return {
            "required": True,
            "status": "REQUEST_INFO",
            "status_label": "추가자료 필요",
            "missing": ["portfolio_context"],
            "next_action": "승인된 포트폴리오의 국가·산업·통화 노출과 한도를 연결한 뒤 재실행",
            "disclosure": "실제 포트폴리오 자료가 없어 편입 영향·집중도·P&L을 계산하지 않았습니다.",
        }
    if not isinstance(context, dict):
        return {
            "required": True,
            "status": "REQUEST_INFO",
            "status_label": "context 형식 확인 필요",
            "missing": ["portfolio_context.v1 object"],
            "next_action": "ripplegate-portfolio-context.v1 형식의 승인된 context를 제공",
            "disclosure": "포트폴리오 context가 객체가 아니므로 투자 영향 계산을 중단했습니다.",
        }
    required_fields = ("schema_version", "as_of_date", "target_node_id", "proposed_weight_pct", "current_exposure_pct", "limit_pct")
    missing = [field for field in required_fields if field not in context]
    if missing:
        return {
            "required": True,
            "status": "REQUEST_INFO",
            "status_label": "context 필드 누락",
            "missing": missing,
            "next_action": "누락된 context 필드를 추가한 뒤 재실행",
            "disclosure": "필수 포트폴리오 노출·한도 필드가 없어 투자 영향 계산을 중단했습니다.",
        }
    try:
        proposed = float(context["proposed_weight_pct"])
        current = float(context["current_exposure_pct"])
        limit = float(context["limit_pct"])
    except (TypeError, ValueError):
        return {
            "required": True,
            "status": "REQUEST_INFO",
            "status_label": "context 수치 확인 필요",
            "missing": ["numeric portfolio exposure/limit"],
            "next_action": "편입 비중·현재 노출·한도를 숫자로 제공한 뒤 재실행",
            "disclosure": "포트폴리오 context의 비중 또는 한도가 숫자가 아니므로 계산하지 않았습니다.",
        }
    if any(value < 0 or value > 100 for value in (proposed, current, limit)):
        return {
            "required": True,
            "status": "REQUEST_INFO",
            "status_label": "context 범위 오류",
            "missing": ["percentage_between_0_and_100"],
            "next_action": "편입 비중·현재 노출·한도를 0~100% 범위로 수정",
            "disclosure": "포트폴리오 context 수치 범위가 유효하지 않아 계산하지 않았습니다.",
        }
    after = current + proposed
    breached = after > limit
    return {
        "required": True,
        "status": "HOLD" if breached else "VERIFIED",
        "status_label": "한도 초과·사람 검토" if breached else "context 확인됨",
        "schema_version": str(context.get("schema_version")),
        "as_of_date": str(context.get("as_of_date")),
        "target_node_id": str(context.get("target_node_id")),
        "target_label": str(context.get("target_label", context.get("target_node_id"))),
        "proposed_weight_pct": round(proposed, 4),
        "current_exposure_pct": round(current, 4),
        "after_exposure_pct": round(after, 4),
        "limit_pct": round(limit, 4),
        "next_action": "편입 비중 또는 한도를 사람이 검토한 뒤 재실행" if breached else "경로별 시나리오와 함께 사람이 편입 영향을 검토",
        "disclosure": "합성 또는 승인된 context의 노출·한도 사전 점검이며 실제 수익률·P&L 예측이 아닙니다.",
    }


def attach_portfolio_impacts(paths: list[dict[str, Any]], portfolio_gate: dict[str, Any]) -> None:
    """Attach a clearly labelled sensitivity index when an approved context is present."""
    if not portfolio_gate.get("required") or portfolio_gate.get("status") not in {"VERIFIED", "HOLD"}:
        return
    target_node_id = str(portfolio_gate.get("target_node_id", ""))
    proposed_weight = float(portfolio_gate.get("proposed_weight_pct", 0.0))
    for path in paths:
        impact = path.get("impact") or {}
        if str(path.get("to", "")) != target_node_id or impact.get("kind") != "scenario":
            continue
        value = round(float(impact.get("base", 0.0)) * proposed_weight / 100.0, 4)
        path["portfolio_impact"] = {
            "kind": "portfolio_sensitivity_index",
            "base": value,
            "unit": "포트폴리오 민감도 지수 pp",
            "formula": "경로 영향지수 × 제안 비중",
            "disclosure": "수익률·P&L이 아닌 관심 비중 적용 민감도 지수",
        }


def build_replan(plan: dict[str, Any], paths: list[dict[str, Any]], status_counts: dict[str, int], portfolio_gate: dict[str, Any] | None = None, critic: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    initial_tools = [str(tool) for tool in plan.get("selected_tools", [])]
    initial_history = {
        "iteration": 1,
        "state": "EXECUTED",
        "trigger": "user_goal",
        "selected_tools": initial_tools,
        "executed": True,
    }
    portfolio_gate = portfolio_gate or {"status": "NOT_REQUESTED"}
    critic = critic or {"status": "PASS", "findings": []}
    portfolio_issue = portfolio_gate.get("status") in {"REQUEST_INFO", "HOLD"}
    critic_issue = critic.get("status") == "HOLD"
    if not status_counts["HOLD"] and not portfolio_issue and not critic_issue:
        return ({
            "triggered": False,
            "state": "NOT_REQUIRED",
            "reason": None,
            "from_tools": initial_tools,
            "next_tools": [],
            "next_step": "담당자 검토 후 다음 의사결정 단계로 이동",
        }, [initial_history])

    unresolved = sorted({
        str(reason)
        for path in paths
        if path["status"] == "HOLD"
        for reason in path.get("unresolved", [])
    })
    if critic_issue:
        reason_parts = ["critic_invariant_failed"] + [str(item.get("code")) for item in critic.get("findings", [])]
        next_tools = ["evidence_check", "request_human_review", "review_pack"]
        next_step = str(critic.get("next_action", "Critic finding을 해소한 뒤 재실행"))
    elif portfolio_issue:
        portfolio_reason = "portfolio_context_missing" if portfolio_gate.get("status") == "REQUEST_INFO" else "portfolio_limit_breach"
        reason_parts = [portfolio_reason] + unresolved
        next_tools = ["portfolio_context_lookup", "evidence_check", "request_human_review", "review_pack"]
        next_step = str(portfolio_gate.get("next_action", "포트폴리오 context를 보완한 뒤 재실행"))
    else:
        reason_parts = unresolved
        needs_exposure = any(token in " / ".join(unresolved) for token in ("trade", "mapping", "exposure", "country_hs"))
        retry_tool = "exposure_lookup" if needs_exposure else "market_snapshot"
        next_tools = ["event_lookup", retry_tool, "evidence_check", "request_human_review", "review_pack"]
        next_step = next((path["next_action"] for path in paths if path["status"] == "HOLD"), "미해결 근거를 추가한 뒤 재실행")
    reason = " / ".join(reason_parts) or "unresolved_evidence"
    next_history = {
        "iteration": 2,
        "state": "AWAITING_SOURCE",
        "trigger": reason,
        "selected_tools": next_tools,
        "executed": False,
        "note": "추가 승인 자료가 입력되기 전에는 재조회 경로를 실행했다고 표시하지 않음",
    }
    return ({
        "triggered": True,
        "state": "AWAITING_SOURCE",
        "reason": reason,
        "from_tools": initial_tools,
        "next_tools": next_tools,
        "next_step": next_step,
    }, [initial_history, next_history])


def run_ripplegate(payload: dict[str, Any]) -> dict[str, Any]:
    dataset = str(payload.get("dataset", "synthetic") or "synthetic")
    graph = load_graph(dataset)
    if str(payload.get("event_id", graph.get("origin", {}).get("id"))) != graph.get("origin", {}).get("id"):
        raise ValueError("unsupported event_id")
    phase = str(payload.get("phase", "plan")).lower()
    if phase not in {"plan", "run"}:
        raise ValueError("phase must be plan or run")
    horizon = int(clamp_number(payload.get("horizon_months", 3), 1, 12, "horizon_months"))
    user_goal = str(payload.get("user_goal", "글로벌 이슈의 투자 영향 경로와 근거를 확인"))[:800]
    plan = recommend_plan(graph, horizon, user_goal)
    quality = data_quality_summary(graph)
    if phase == "plan":
        return {
            "schema_version": "ripplegate-run.v1",
            "product": PRODUCT,
            "version": VERSION,
            "phase": "plan",
            "run_id": f"RG-PLAN-{uuid.uuid4().hex[:8].upper()}",
            "graph_hash": graph_hash(graph),
            "scenario": {"id": graph["scenario_id"], "title": graph["title"], "as_of_date": graph["as_of_date"], "analysis_horizon": f"{horizon}개월"},
            "dataset": graph.get("dataset", dataset),
            "data_quality": quality,
            "plan": plan,
            "trace": build_trace(graph, plan, [], "plan"),
            "disclosure": graph.get("disclosure"),
        }
    if payload.get("human_confirmed") is not True:
        raise ValueError("human_confirmed must be true before calculation")
    assumptions = parse_assumptions(payload.get("assumptions"), graph["edges"], horizon)
    sources = source_map(graph)
    nodes = node_map(graph)
    paths = []
    for edge in graph["edges"]:
        path = calculate_path(edge, assumptions[str(edge["id"])], sources)
        path["from_label"] = nodes.get(str(edge.get("from")), {}).get("label", edge.get("from"))
        path["to_label"] = nodes.get(str(edge.get("to")), {}).get("label", edge.get("to"))
        paths.append(path)
    counts = {key: sum(1 for path in paths if path["status"] == key) for key in ("VERIFIED", "SCENARIO", "HOLD")}
    portfolio_gate = build_portfolio_gate(plan, payload)
    attach_portfolio_impacts(paths, portfolio_gate)
    ledger = []
    seen: set[str] = set()
    for edge in graph["edges"]:
        for source_id in edge.get("evidence_ids", []):
            source = sources.get(str(source_id))
            if source and source["id"] not in seen:
                ledger.append(ledger_entry(source, edge))
                seen.add(source["id"])
    for source in graph.get("sources", []):
        if source.get("id") not in seen:
            ledger.append(ledger_entry(source))
            seen.add(source["id"])
    trace = build_trace(graph, plan, paths, "run")
    decision = "REQUEST_INFO" if portfolio_gate["status"] == "REQUEST_INFO" else ("PARTIAL_REVIEW_HOLD" if counts["HOLD"] or portfolio_gate["status"] == "HOLD" else "HUMAN_REVIEW")
    run_id = f"RG-RUN-{uuid.uuid4().hex[:8].upper()}"
    critic = critic_check(paths, plan, portfolio_gate)
    trace = build_trace(graph, plan, paths, "run", critic)
    replan, planning_history = build_replan(plan, paths, counts, portfolio_gate, critic)
    if critic["status"] == "HOLD":
        decision = "CRITIC_HOLD"
    return {
        "schema_version": "ripplegate-run.v1",
        "product": PRODUCT,
        "version": VERSION,
        "phase": "run",
        "run_id": run_id,
        "graph_hash": graph_hash(graph),
        "scenario": {
            "id": graph["scenario_id"],
            "title": graph["title"],
            "as_of_date": graph["as_of_date"],
            "analysis_horizon": f"{horizon}개월",
            "origin": graph["origin"],
            "dataset": graph.get("dataset", dataset),
        },
        "data_quality": quality,
        "decision": decision,
        "status_counts": counts,
        "portfolio_gate": portfolio_gate,
        "critic": critic,
        "plan": plan,
        "assumptions": assumptions,
        "paths": paths,
        "evidence_ledger": ledger,
        "trace": trace,
        "replan": replan,
        "planning_history": planning_history,
        "review_pack": {
            "title": f"RippleGate 투자검토팩 · {graph['title']}",
            "decision": decision,
            "headline": ("거시 영향 경로는 분리했지만 포트폴리오 context가 없어 편입 영향은 계산하지 않았습니다." if portfolio_gate["status"] == "REQUEST_INFO" else ("포트폴리오 context와 경로별 민감도를 확인했지만 한도 초과는 자동 승인하지 않습니다." if portfolio_gate["status"] == "HOLD" else ("검증된 경로·시나리오와 포트폴리오 민감도를 분리해 검토팩으로 만들었습니다." if portfolio_gate["status"] == "VERIFIED" else "검증된 경로와 시나리오 범위를 분리하고, 충돌 경로는 자동 보류했습니다."))),
            "human_action": (portfolio_gate["next_action"] if portfolio_gate["status"] in {"REQUEST_INFO", "HOLD"} else "VERIFIED·SCENARIO 수치와 포트폴리오 민감도를 검토하고 HOLD 경로의 추가자료를 요청"),
            "not_included": ["자동 매매", "자동 투자승인", "리스크 한도 변경", "미확인 경로의 단일 숫자 확정"],
            "critic": critic,
        },
        "disclosure": graph.get("disclosure"),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "RippleGate/0.1"
    sys_version = ""

    def send_bytes(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), browsing-topics=()")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(body)

    def json(self, status: int, value: dict[str, Any]) -> None:
        self.send_bytes(status, json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/":
            self.send_bytes(200, STATIC_PATH.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/health":
            self.json(200, {"status": "ok", "service": PRODUCT, "version": VERSION, "mode": "public_and_synthetic_snapshot"})
            return
        if path == "/api/graph":
            dataset = parse_qs(parsed.query).get("dataset", ["synthetic"])[0]
            self.json(200, load_graph(dataset))
            return
        if path == "/api/data-policy":
            self.json(200, public_adapter_report())
            return
        if path == "/assets/ripplegate-world-map-v1.png":
            self.send_bytes(200, (ASSET_ROOT / "ripplegate-world-map-v1.png").read_bytes(), "image/png")
            return
        if path == "/favicon.ico":
            self.send_bytes(204, b"", "image/x-icon")
            return
        self.json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in {"/api/analyze", "/api/compare"}:
            self.json(404, {"error": "not_found"})
            return
        try:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self.json(415, {"error": "content_type_must_be_application_json"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY_BYTES:
                self.json(413, {"error": "request_too_large"})
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("request must be an object")
            if path == "/api/compare":
                dataset = str(payload.get("dataset", "public_snapshot") or "public_snapshot")
                graph = load_graph(dataset)
                event_id = str(payload.get("event_id", graph.get("origin", {}).get("id")))
                if event_id != graph.get("origin", {}).get("id"):
                    raise ValueError("unsupported event_id")
                user_goal = str(payload.get("user_goal", "글로벌 이슈의 영향 경로와 근거를 확인"))[:800]
                ripplegate_result = run_ripplegate({
                    "phase": "run",
                    "dataset": dataset,
                    "event_id": event_id,
                    "horizon_months": payload.get("horizon_months", 3),
                    "human_confirmed": True,
                    "user_goal": user_goal,
                    "assumptions": payload.get("assumptions", {}),
                })
                self.json(200, {
                    "schema_version": "ripplegate-comparison.v1",
                    "same_input": {"dataset": dataset, "event_id": event_id, "horizon_months": payload.get("horizon_months", 3), "user_goal": user_goal},
                    "baseline": summary_only_baseline(graph, user_goal),
                    "ripplegate": {
                        "run_id": ripplegate_result["run_id"],
                        "decision": ripplegate_result["decision"],
                        "status_counts": ripplegate_result["status_counts"],
                        "path_count": len(ripplegate_result["paths"]),
                        "evidence_count": len(ripplegate_result["evidence_ledger"]),
                        "trace": [item["stage"] + ":" + item["state"] for item in ripplegate_result["trace"]],
                        "replan": ripplegate_result["replan"],
                    },
                    "disclosure": "검색·요약 대조 경로와 RippleGate의 구조 차이 비교이며, live LLM 정확도·환각률 benchmark가 아니다.",
                })
                return
            self.json(200, run_ripplegate(payload))
        except ValueError as exc:
            self.json(400, {"error": "invalid_request", "detail": str(exc)[:300]})
        except Exception as exc:  # pragma: no cover
            self.log_message("internal error: %s", exc)
            self.json(500, {"error": "internal_server_error"})


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{PRODUCT} demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    print(f"{PRODUCT} demo: http://{display_host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
