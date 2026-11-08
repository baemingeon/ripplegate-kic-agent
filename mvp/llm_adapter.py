from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


class ApprovedLLMClient:
    """Provider-neutral adapter for an approved optional LLM boundary.

    The endpoint must be an approved private or OpenAI-compatible gateway.
    Provider selection never changes the deterministic safety gate.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        # The production-safe default is provider-neutral and model-free.
        # An approved private gateway is opt-in through policy.
        self.provider = os.getenv("KIC_LLM_PROVIDER", "private_gateway").strip().lower()
        self.base_url = base_url or os.getenv("KIC_LLM_URL", "")
        self.model = model if model is not None else os.getenv("KIC_LLM_MODEL", "")
        self.allowed_models = tuple(
            item.strip()
            for item in os.getenv("KIC_LLM_ALLOWED_MODELS", "").split(",")
            if item.strip()
        )
        self.policy = os.getenv("KIC_LLM_POLICY", "disabled").strip().lower()
        self.timeout = timeout or int(os.getenv("KIC_LLM_TIMEOUT", "45"))

    def generate_json(self, prompt: str, purpose: str) -> dict[str, Any]:
        if self.policy not in {"approved", "allow", "enabled"}:
            return self._failure(purpose, "llm_disabled_by_policy", "", time.perf_counter())
        if not self.model:
            return self._failure(purpose, "model_not_configured", "", time.perf_counter())
        if self.model not in self.allowed_models:
            return self._failure(purpose, "model_not_allowlisted", "", time.perf_counter())
        if self.provider not in {"openai", "openai_compatible", "enterprise", "private_gateway"}:
            return self._failure(purpose, f"unsupported_provider:{self.provider}", "", time.perf_counter())
        return self._generate_openai_compatible(prompt, purpose)

    def _failure(self, purpose: str, error: str, raw: str, started: float) -> dict[str, Any]:
        return {
            "ok": False,
            "purpose": purpose,
            "provider": self.provider,
            "model": self.model,
            "policy": self.policy,
            "error": error[:500],
            "raw": raw[:1500],
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    def _generate_openai_compatible(self, prompt: str, purpose: str) -> dict[str, Any]:
        api_key = os.getenv("KIC_LLM_API_KEY", "").strip()
        started = time.perf_counter()
        if not self.base_url.strip():
            return self._failure(purpose, "endpoint_not_configured", "", started)
        if not api_key:
            return self._failure(purpose, "api_key_not_configured", "", started)
        base = self.base_url.rstrip("/")
        endpoint = base if base.endswith("/v1") else base + "/v1"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return JSON only. Do not invent data or sources."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        request = urllib.request.Request(
            endpoint + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.load(response)
            choices = body.get("choices", [])
            raw = ""
            if choices and isinstance(choices[0], dict):
                message = choices[0].get("message", {})
                if isinstance(message, dict):
                    raw = str(message.get("content", ""))
            parsed = _extract_json_object(raw)
            if parsed is None:
                return self._failure(purpose, "invalid_json", raw, started)
            return {
                "ok": True,
                "purpose": purpose,
                "provider": self.provider,
                "model": self.model,
                "policy": self.policy,
                "raw": raw[:1500],
                "parsed": parsed,
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return self._failure(purpose, f"{type(exc).__name__}: {exc}", "", started)


def planner_prompt(
    user_goal: str,
    as_of_date: str,
    required_metrics: list[str],
    evidence: list[dict[str, Any]],
) -> str:
    evidence_summary = [
        {
            "id": item.get("id"),
            "source_type": item.get("source_type"),
            "metric": item.get("metric"),
            "period": item.get("period", item.get("period_end")),
        }
        for item in evidence
    ]
    return f"""You are the Planner agent in a financial research workflow.
Return JSON only with keys: plan_steps (array of short strings), tool_calls (array using only the exact allowlisted names below), risk_flags (array of short strings), needs_replan (boolean).
You propose the next actions; you do not approve an investment and you do not decide whether a quantitative result is safe. Do not invent data or sources.

Allowlisted tool_calls: retrieve_primary_filings, retrieve_market_price, screen_peer_candidates, normalize_metric_definitions, recalculate_valuation, request_human_review.

User goal: {user_goal}
As-of date: {as_of_date}
Required metrics: {json.dumps(required_metrics, ensure_ascii=False)}
Evidence metadata: {json.dumps(evidence_summary, ensure_ascii=False)}
"""


def critic_prompt(state: dict[str, Any]) -> str:
    evidence_summary = [
        {
            "id": item.get("id"),
            "metric": item.get("metric"),
            "period": item.get("period", item.get("period_end")),
            "value": item.get("value"),
            "unit": item.get("unit"),
            "verification_status": item.get("verification_status"),
        }
        for item in state.get("evidence", [])
    ]
    return f"""You are the Reflection/Critic agent in a financial research workflow.
Return JSON only with keys: risk_flags (array of short strings), challenge (short string), recommended_action (exactly REVIEW or HOLD).
Challenge assumptions and source alignment, but do not override deterministic verification results.

Goal: {state.get("user_goal")}
As-of date: {state.get("as_of_date")}
Unresolved typed issues: {json.dumps(state.get("unresolved", []), ensure_ascii=False)}
Calculation state: {json.dumps(state.get("valuation"), ensure_ascii=False)}
Evidence: {json.dumps(evidence_summary, ensure_ascii=False)}
"""


def run_planner(client: ApprovedLLMClient, state: dict[str, Any]) -> dict[str, Any]:
    return client.generate_json(
        planner_prompt(
            state["user_goal"],
            state["as_of_date"],
            state["required_metrics"],
            state["evidence"],
        ),
        "planner",
    )


def run_critic(client: ApprovedLLMClient, state: dict[str, Any]) -> dict[str, Any]:
    return client.generate_json(critic_prompt(state), "reflection")
