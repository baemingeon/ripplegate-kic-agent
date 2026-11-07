from __future__ import annotations

"""Check that the submitted public Demo serves the claimed static experience.

This is an availability/content smoke check, not a model-quality or user-
efficiency benchmark. It deliberately does not submit user data or call a
runtime model API.
"""

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_URL = "https://ripplegate-kic-agent.branchingdonkey2.chatgpt.site"
DEFAULT_REPORT = Path(__file__).resolve().parent / "data" / "public_demo_smoke_2026-11-08.json"


def audit(url: str, timeout: int = 30) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "RippleGate-public-demo-smoke/1.0"})
    result: dict[str, object] = {
        "schema_version": "ripplegate-public-demo-smoke.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "status": "BLOCKED",
        "checks": {},
        "disclosure": "공개 Demo 가용성·정적 UI 문구 smoke check이며 정확도·환각률·업무효율 benchmark가 아님",
    }
    checks: dict[str, object] = result["checks"]  # type: ignore[assignment]
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_000).decode("utf-8", errors="replace")
            status_code = int(response.status)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        checks["http_200"] = {"passed": False, "detail": f"{type(exc).__name__}: {exc}"}
        return result

    title = re.search(r"<title>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
    checks["http_200"] = {"passed": status_code == 200, "detail": status_code}
    checks["ripplegate_title"] = {"passed": bool(title and "RippleGate" in title.group(1)), "detail": title.group(1).strip() if title else ""}
    checks["compare_path_present"] = {"passed": "/api/compare" in body, "detail": "static compare path wired"}
    checks["retrieval_control_disclosure"] = {"passed": "검색·요약 대조 경로" in body, "detail": "fair comparison label present"}
    checks["retired_control_label_absent"] = {"passed": "요약형 통제군" not in body, "detail": "retired label absent"}
    checks["no_direct_openai_runtime_url"] = {"passed": "api.openai.com" not in body, "detail": "browser bundle has no direct model endpoint"}
    result["status"] = "PASS" if all(bool(item.get("passed")) for item in checks.values() if isinstance(item, dict)) else "BLOCKED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="RippleGate public Demo smoke audit")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = audit(args.url, max(1, min(args.timeout, 120)))
    if args.write_report:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
