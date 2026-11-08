from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


REPRO_GOAL = "대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘"


def fetch(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, bytes]:
    body = None
    headers = {"User-Agent": "ICPreflight-submission-smoke/0.9.2"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        return int(response.status), response.read()


def check_demo(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    try:
        health_status, health_body = fetch(f"{base}/health")
        root_status, root_body = fetch(base)
        api_status, api_body = fetch(
            f"{base}/api/run",
            method="POST",
            payload={"scenario": "period_mismatch", "mode": "deterministic", "user_goal": REPRO_GOAL},
        )
        health = json.loads(health_body.decode("utf-8"))
        result = json.loads(api_body.decode("utf-8"))
        trace_nodes = [item.get("node") for item in result.get("trace", [])]
        passed = (
            health_status == 200
            and health.get("service") == "IC Preflight"
            and health.get("version") == "0.9.2"
            and root_status == 200
            and "IC Preflight".encode("utf-8") in root_body
            and api_status == 200
            and result.get("status") == "hold"
            and result.get("user_goal") == REPRO_GOAL
            and {"VERIFY", "REPLAN", "CRITIC"}.issubset(set(trace_nodes))
            and result.get("investment_pack", {}).get("decision") == "보류"
        )
        return {
            "configured": True,
            "passed": passed,
            "health_status": health_status,
            "root_status": root_status,
            "api_status": api_status,
            "decision": result.get("investment_pack", {}).get("decision"),
            "trace_nodes": trace_nodes,
        }
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"configured": True, "passed": False, "error": str(exc)[:240]}


def check_link(url: str, required: bool) -> dict[str, Any]:
    if not url:
        return {"configured": False, "required": required, "passed": not required, "detail": "not configured"}
    try:
        status, _ = fetch(url)
        return {"configured": True, "required": required, "passed": 200 <= status < 400, "status": status}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"configured": True, "required": required, "passed": False, "error": str(exc)[:240]}


def env_first(primary: str, legacy: str) -> str:
    """Read the current product prefix first, while keeping old local scripts usable."""
    return os.getenv(primary, "").strip() or os.getenv(legacy, "").strip()


def run_public_submission_smoke() -> dict[str, Any]:
    demo_url = env_first("IC_PREFLIGHT_DEMO_URL", "IC_PROOF_DEMO_URL")
    github_url = env_first("IC_PREFLIGHT_GITHUB_URL", "IC_PROOF_GITHUB_URL")
    video_url = env_first("IC_PREFLIGHT_VIDEO_URL", "IC_PROOF_VIDEO_URL")
    demo = check_demo(demo_url) if demo_url else {
        "configured": False,
        "passed": False,
        "detail": "IC_PREFLIGHT_DEMO_URL is not configured",
    }
    github = check_link(github_url, required=True)
    video = check_link(video_url, required=False)
    required_configured = bool(demo_url and github_url)
    passed = required_configured and demo.get("passed") is True and github.get("passed") is True
    return {
        "status": "READY" if passed else "READY_AFTER_LINKS" if not required_configured else "BLOCKED",
        "passed": passed,
        "demo": demo,
        "github": github,
        "video_optional": video,
        "next_action": [] if passed else [
            "IC_PREFLIGHT_DEMO_URL과 IC_PREFLIGHT_GITHUB_URL을 설정한 뒤 재실행",
            "선택 시연영상은 IC_PREFLIGHT_VIDEO_URL로 추가 검증",
            "기존 IC_PROOF_* 환경변수도 호환 alias로 사용할 수 있음",
        ],
    }


def main() -> int:
    result = run_public_submission_smoke()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
