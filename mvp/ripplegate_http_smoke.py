from __future__ import annotations

"""HTTP-level smoke test for a running RippleGate demo server."""

import argparse
import json
import urllib.error
import urllib.request
from typing import Any


def request(base_url: str, path: str, method: str = "GET", body: Any = None, content_type: str | None = None) -> tuple[int, dict[str, str], bytes]:
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method)
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def body_json(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("response body must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="RippleGate HTTP smoke test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    base = args.base_url
    output: dict[str, Any] = {}

    status, headers, raw = request(base, "/health")
    health = body_json(raw)
    assert status == 200 and health.get("service") == "RippleGate"
    output["health"] = status

    status, headers, raw = request(base, "/")
    assert status == 200 and "Content-Security-Policy" in headers and headers.get("X-Content-Type-Options") == "nosniff"
    output["security_headers"] = status

    status, _, raw = request(base, "/api/data-policy")
    policy = body_json(raw)
    assert status == 200 and policy.get("passed") is True
    output["data_policy"] = {"status": status, "warnings": len(policy.get("warnings", []))}

    common = {
        "dataset": "public_snapshot",
        "event_id": "event_red_sea",
        "horizon_months": 3,
        "user_goal": "impact review",
    }
    status, _, raw = request(base, "/api/analyze", "POST", {**common, "phase": "plan"}, "application/json")
    plan = body_json(raw)
    assert status == 200 and plan.get("phase") == "plan"
    output["plan"] = status

    status, _, raw = request(base, "/api/analyze", "POST", {**common, "phase": "run", "human_confirmed": True, "assumptions": {}}, "application/json")
    run = body_json(raw)
    assert status == 200 and run.get("status_counts") == {"VERIFIED": 1, "SCENARIO": 1, "HOLD": 1}
    output["run"] = {"status": status, "status_counts": run["status_counts"]}

    status, _, raw = request(base, "/api/compare", "POST", {**common, "assumptions": {}}, "application/json")
    comparison = body_json(raw)
    assert status == 200 and comparison.get("schema_version") == "ripplegate-comparison.v1"
    assert comparison.get("baseline", {}).get("path_count") == 0
    output["compare"] = {"status": status, "baseline_paths": comparison["baseline"]["path_count"], "ripple_paths": comparison["ripplegate"]["path_count"]}

    status, _, raw = request(base, "/api/analyze", "POST", {**common, "phase": "run"}, "application/json")
    assert status == 400 and body_json(raw).get("error") == "invalid_request"
    output["human_gate_guard"] = status

    status, _, raw = request(base, "/api/analyze", "POST", {**common, "phase": "plan"}, "text/plain")
    assert status == 415 and body_json(raw).get("error") == "content_type_must_be_application_json"
    output["content_type_guard"] = status

    status, _, raw = request(base, "/api/analyze", "POST", b"{" + (b"x" * 128_001) + b"}", "application/json")
    assert status == 413 and body_json(raw).get("error") == "request_too_large"
    output["body_limit_guard"] = status

    print(json.dumps({"reproduction": "PASS", "base_url": base, "checks": output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
