from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MVP = ROOT / "mvp"
DATA = MVP / "data"
PLAN = ROOT / "기획서"
BUILD = ROOT / ".codex-build"

PPTX = PLAN / "KIC_AI_에이전트_공모전_기획서_작업본_v0.9.2.pptx"
PDF = PLAN / "KIC_AI_에이전트_공모전_기획서_작업본_v0.9.2.pdf"
RELEASE_ZIP = PLAN / "KIC_ICPreflight_MVP_v0.9.2_20261107.zip"
VIDEO = PLAN / "IC_Preflight_본선_시연영상_초안.webm"
RECEIPT = ROOT / ".codex-finalizer-v09.3" / "validation.json"
PPTX_INSPECT = BUILD / "candidate_v20.pptx.inspect.ndjson"
OFFLINE_RESULT = DATA / "benchmark_holdout20_offline_result.json"
OFFLINE_REPEAT = DATA / "benchmark_holdout20_offline_repeat01_result.json"
UI_LOG = DATA / "ui_run_results_2026-11-07.json"
OUTPUT = DATA / "submission_validation_2026-11-07.json"


PRELIM_REQUIRED_SECTIONS = {
    # Each tuple is an acceptable keyword set. This handles titles and body
    # copy split across multiple text objects or adjacent slides.
    "summary": (("Summary",), ("서비스명",)),
    "problem_definition": (("문제 정의",),),
    "service_proposal": (("서비스 제안",),),
    "agent_configuration": (("Agent 역할", "Workflow"), ("AI 기술·Tool/API",)),
    "data_utilization_plan": (("데이터 활용 계획",),),
    "mvp_development_plan": (("MVP 개발 계획",),),
    "expected_effects": (("기대효과",),),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
    *,
    blocking: bool = False,
) -> None:
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "blocking": bool(blocking and not passed),
            "detail": detail,
        }
    )


def count_pptx_slides(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return len(
            [
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
        )


def count_pdf_pages(path: Path) -> int | None:
    try:
        from pypdf import PdfReader  # type: ignore

        return len(PdfReader(str(path)).pages)
    except Exception:
        pdfinfo = shutil.which("pdfinfo")
        if not pdfinfo:
            return None
        try:
            completed = subprocess.run(
                [pdfinfo, str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        for line in (completed.stdout or "").splitlines():
            if line.startswith("Pages:"):
                try:
                    return int(line.split(":", 1)[1].strip())
                except ValueError:
                    return None
        return None


def audit_prelim_required_sections(path: Path) -> dict[str, Any]:
    """Audit the seven official prelim sections from the inspect artifact.

    This is intentionally a lightweight content-presence gate, not a quality
    score. It protects the <=10-page submission from losing a required section
    during later visual or copy edits.
    """
    if not path.exists():
        return {
            "passed": False,
            "sections": {},
            "detail": "PPTX inspect artifact is missing",
        }

    slide_text: dict[int, list[str]] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                item = json.loads(line)
                slide_index = item.get("slideIndex")
                if not isinstance(slide_index, int):
                    continue
                text = item.get("title") if item.get("kind") == "slide" else item.get("text")
                if isinstance(text, str) and text.strip():
                    slide_text.setdefault(slide_index, []).append(text.strip())
                preview = item.get("preview")
                if isinstance(preview, str) and preview.strip():
                    slide_text.setdefault(slide_index, []).append(preview.strip())
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "passed": False,
            "sections": {},
            "detail": f"inspect parse failed: {exc}",
        }

    section_results: dict[str, Any] = {}
    for name, keyword_sets in PRELIM_REQUIRED_SECTIONS.items():
        matches: list[int] = []
        for slide_index, texts in slide_text.items():
            haystack = " ".join(texts)
            if any(all(keyword in haystack for keyword in keywords) for keywords in keyword_sets):
                matches.append(slide_index + 1)
        section_results[name] = {
            "passed": bool(matches),
            "slides": sorted(set(matches)),
            "keyword_sets": [list(keywords) for keywords in keyword_sets],
        }
    missing = [name for name, result in section_results.items() if not result["passed"]]
    return {
        "passed": not missing,
        "sections": section_results,
        "detail": "all seven official prelim sections detected"
        if not missing
        else f"missing sections: {missing}",
    }


def run_deterministic_rehearsal() -> dict[str, Any]:
    sys.path.insert(0, str(MVP))
    from server import run_agent  # type: ignore

    rehearsal: dict[str, Any] = {}
    for scenario in ("clean", "conflict", "hold", "period_mismatch", "currency_mismatch", "missing_evidence", "real"):
        result = run_agent(scenario, use_llm=False)
        trace = result.get("trace", [])
        nodes = [item.get("node") for item in trace]
        if scenario == "clean":
            expected_status = "ready_for_review"
            required_nodes = {"VERIFY", "CALCULATE", "MEMO", "TOOL"}
        elif scenario == "conflict":
            expected_status = "ready_for_review"
            required_nodes = {"VERIFY", "REPLAN", "CALCULATE", "MEMO", "TOOL"}
        elif scenario == "hold":
            expected_status = "hold"
            required_nodes = {"VERIFY", "REPLAN", "CRITIC", "TOOL"}
        elif scenario == "period_mismatch":
            expected_status = "hold"
            required_nodes = {"VERIFY", "REPLAN", "CRITIC", "TOOL"}
        elif scenario == "currency_mismatch":
            expected_status = "hold"
            required_nodes = {"VERIFY", "REPLAN", "CRITIC", "TOOL"}
        elif scenario == "missing_evidence":
            expected_status = "needs_more_info"
            required_nodes = {"VERIFY", "REPLAN", "MEMO", "TOOL"}
        else:
            expected_status = "ready_for_review"
            required_nodes = {"RETRIEVE", "VERIFY", "CALCULATE", "MEMO", "TOOL"}
        human_gate_recorded = bool(
            result.get("investment_pack", {})
            .get("audit_contract", {})
            .get("tool_state", {})
            .get("human_gate_recorded")
        )
        rehearsal[scenario] = {
            "passed": result.get("status") == expected_status
            and required_nodes.issubset(set(nodes))
            and human_gate_recorded,
            "status": result.get("status"),
            "nodes": nodes,
            "required_nodes": sorted(required_nodes),
            "human_gate_recorded": human_gate_recorded,
        }
    return rehearsal


def run_llm_failure_fallback() -> dict[str, Any]:
    sys.path.insert(0, str(MVP))
    from server import run_agent  # type: ignore

    failure_env_names = (
        "KIC_LLM_POLICY",
        "KIC_LLM_PROVIDER",
        "KIC_LLM_URL",
        "KIC_LLM_MODEL",
        "KIC_LLM_API_KEY",
        "KIC_LLM_ALLOWED_MODELS",
        "KIC_LLM_TIMEOUT",
    )
    saved = {name: os.environ.get(name) for name in failure_env_names}
    try:
        os.environ["KIC_LLM_POLICY"] = "approved"
        os.environ["KIC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["KIC_LLM_URL"] = "http://127.0.0.1:1"
        os.environ["KIC_LLM_MODEL"] = "approved-fallback-validation"
        os.environ["KIC_LLM_API_KEY"] = "validation-only-secret"
        os.environ["KIC_LLM_ALLOWED_MODELS"] = "approved-fallback-validation"
        os.environ["KIC_LLM_TIMEOUT"] = "1"
        result = run_agent("conflict", use_llm=True)
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    retry_nodes = [item.get("node") for item in result.get("trace", []) if item.get("status") == "retry"]
    return {
        "passed": result.get("status") == "ready_for_review"
        and result.get("agent_runtime", {}).get("planner", {}).get("ok") is False
        and result.get("agent_runtime", {}).get("reflection", {}).get("ok") is False
        and {"PLAN", "REFLECTION"}.issubset(set(retry_nodes)),
        "status": result.get("status"),
        "planner_ok": result.get("agent_runtime", {}).get("planner", {}).get("ok"),
        "reflection_ok": result.get("agent_runtime", {}).get("reflection", {}).get("ok"),
        "retry_nodes": retry_nodes,
    }


def run_http_smoke() -> dict[str, Any]:
    sys.path.insert(0, str(MVP))
    from test_mvp import run_http_smoke as smoke  # type: ignore

    return smoke()


def run_approved_gateway_smoke() -> dict[str, Any]:
    sys.path.insert(0, str(MVP))
    from test_mvp import run_approved_gateway_smoke as smoke  # type: ignore

    return smoke()


def run_model_allowlist_smoke() -> dict[str, Any]:
    sys.path.insert(0, str(MVP))
    from test_mvp import run_model_allowlist_smoke as smoke  # type: ignore

    return smoke()


def run_public_submission_smoke() -> dict[str, Any]:
    sys.path.insert(0, str(MVP))
    from validate_public_submission import run_public_submission_smoke as smoke  # type: ignore

    return smoke()


def main() -> int:
    checks: list[dict[str, Any]] = []
    required_files = [
        PPTX,
        PDF,
        RELEASE_ZIP,
        RECEIPT,
        OFFLINE_RESULT,
        OFFLINE_REPEAT,
        UI_LOG,
        MVP / "server.py",
        MVP / "static" / "index.html",
        MVP / "assets" / "ui-period-mismatch.png",
        MVP / "assets" / "ui-currency-mismatch.png",
        MVP / "assets" / "ui-local-packet.png",
        MVP / "measure_effect.py",
        MVP / "validate_effect_measurement.py",
        MVP / "generate_pilot_artifacts.py",
        MVP / "data" / "effect_measurement_template.json",
        MVP / "data" / "goal_route_holdout_v1.json",
        MVP / "data" / "case_packet_template.json",
        MVP / "data" / "pilot_measurement_sheet_v0.2.json",
        MVP / "data" / "pilot_packet_manifest_v0.1.json",
        MVP / "data" / "pilot_agent_runtime_2026-11-07.json",
        MVP / "Dockerfile",
        MVP / "render.yaml",
        MVP / "DEPLOYMENT.md",
        MVP / "test_mvp.py",
        MVP / "DEMO_RUNBOOK.md",
        MVP / "JUDGE_REPRO.md",
        MVP / "validate_public_submission.py",
        MVP / "THIRD_PARTY_NOTICES_v0.9.2.md",
        MVP / "finalize_submission.ps1",
        MVP / "RELEASE_MANIFEST_v0.9.2.md",
        MVP / "data" / "source_policy_2026-11-07.json",
        MVP / "data" / "model_policy_2026-11-07.json",
        MVP / "data" / "benchmark_holdout20_offline_result.json",
        MVP / "data" / "benchmark_holdout20_offline_repeat01_result.json",
        MVP / "data" / "benchmark_observations_v1.json",
        PLAN / "제출_체크리스트_v0.7.1.md",
        PLAN / "외부자원_사용대장_v0.1.md",
        PLAN / "본선_상위권_실행플랜_v0.1.md",
        PLAN / "본선_발표_스토리보드_v0.1.md",
        PLAN / "본선_효과측정_프로토콜_v0.1.md",
        PLAN / "본선_레드팀_QA_v0.2.md",
        PLAN / "예선_상호평가_운영플랜_v0.1.md",
        PLAN / "100점_달성_갭분석_v0.1.md",
        PLAN / "KIC_업무검증_인터뷰_스크립트_v0.1.md",
        PLAN / "최신본_사용안내_v0.9.2.md",
        PLAN / "본선_GitHub_업로드_가이드_v0.1.md",
        PLAN / "100점_달성_갭분석_v0.2.md",
        PLAN / "경쟁작대비_레드팀_검증_v0.1.md",
        PLAN / "심사대응_매트릭스_v0.9.md",
        PLAN / "서비스명_포지셔닝_결정_v0.2.md",
        PLAN / "제품개편_의사결정_v0.2.md",
        PLAN / "KIC_1등_달성_운영판_v0.1.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required_files if not path.exists()]
    add_check(
        checks,
        "required_files",
        not missing,
        "all required files present" if not missing else f"missing: {missing}",
        blocking=True,
    )

    artifact_paths = {
        "pptx": PPTX,
        "pdf": PDF,
        "fallback_video": VIDEO,
    }
    artifact_hashes = {
        name: {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
        for name, path in artifact_paths.items()
        if path.exists()
    }
    add_check(
        checks,
        "artifact_hashes",
        all(name in artifact_hashes for name in ("pptx", "pdf", "fallback_video")),
        "PPTX/PDF/fallback video hashes recorded; MVP ZIP is checked independently"
        if all(name in artifact_hashes for name in ("pptx", "pdf", "fallback_video"))
        else "one or more current external submission artifacts are missing",
        blocking=True,
    )

    try:
        sys.path.insert(0, str(MVP))
        from server import route_user_goal  # type: ignore

        route_holdout = json.loads((MVP / "data" / "goal_route_holdout_v1.json").read_text(encoding="utf-8"))
        route_observations = [
            {
                "case_id": case.get("case_id"),
                "expected": case.get("expected_scenario"),
                "observed": route_user_goal(str(case.get("user_goal", "")))[0],
            }
            for case in route_holdout.get("cases", [])
        ]
        route_holdout_passed = bool(route_observations) and all(
            item["expected"] == item["observed"] for item in route_observations
        )
        route_holdout_detail = f"{len(route_observations)} natural-language route cases match"
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        route_holdout_passed = False
        route_holdout_detail = f"route holdout failed: {exc}"
    add_check(
        checks,
        "goal_route_holdout",
        route_holdout_passed,
        route_holdout_detail,
        blocking=True,
    )

    if PPTX.exists():
        slide_count = count_pptx_slides(PPTX)
        add_check(checks, "pptx_slide_count", slide_count == 10, f"{slide_count} slides", blocking=True)
    else:
        slide_count = None

    pdf_pages = count_pdf_pages(PDF) if PDF.exists() else None
    add_check(
        checks,
        "pdf_page_count",
        pdf_pages == 10,
        f"{pdf_pages} pages" if pdf_pages is not None else "pypdf unavailable or unreadable",
        blocking=True,
    )

    prelim_sections = audit_prelim_required_sections(PPTX_INSPECT)
    add_check(
        checks,
        "prelim_required_sections",
        prelim_sections["passed"],
        prelim_sections["detail"],
        blocking=True,
    )

    visible_deck_text = PPTX_INSPECT.read_text(encoding="utf-8") if PPTX_INSPECT.exists() else ""
    add_check(
        checks,
        "brand_consistency",
        "IC Preflight" in visible_deck_text and "IC Proof" not in visible_deck_text and "투심렌즈" not in visible_deck_text and "심의나침반" not in visible_deck_text and "IC-Gate" not in visible_deck_text,
        "visible deck uses IC Preflight and contains no legacy brand label",
        blocking=True,
    )
    forbidden_public_terms = (
        "심의나침반",
        "IC-Gate",
        "IC Proof",
        "Qwen",
        "qwen",
        "Ollama",
        "ollama",
        "KIC Valuation Forensics Agent",
        "benchmark_ollama",
    )
    forbidden_hits = [term for term in forbidden_public_terms if term in visible_deck_text]
    add_check(
        checks,
        "public_deck_model_boundary",
        not forbidden_hits,
        "visible deck contains no legacy brand or specific local-model reference"
        if not forbidden_hits
        else f"forbidden visible deck terms: {forbidden_hits}",
        blocking=True,
    )

    if RELEASE_ZIP.exists():
        with zipfile.ZipFile(RELEASE_ZIP) as archive:
            entries = archive.namelist()
        unwanted = [name for name in entries if "__pycache__" in name or name.endswith(".pyc")]
        add_check(
            checks,
            "mvp_release_zip",
            "RELEASE_MANIFEST_v0.9.2.md" in entries
            and "data/benchmark_holdout20_offline_result.json" in entries
            and "data/benchmark_observations_v1.json" in entries
            and "data/model_policy_2026-11-07.json" in entries
            and not any("ollama" in name.lower() or "qwen" in name.lower() for name in entries)
            and not unwanted,
            f"{len(entries)} entries; no cache artifacts; manifest present",
            blocking=True,
        )

    receipt: dict[str, Any] = {}
    if RECEIPT.exists():
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        actual_sha = sha256(PPTX) if PPTX.exists() else ""
        receipt_sha = receipt.get("finalSha256", "")
        add_check(
            checks,
            "pptx_receipt_sha256",
            bool(actual_sha) and actual_sha == receipt_sha,
            f"actual={actual_sha} receipt={receipt_sha}",
            blocking=True,
        )
        add_check(
            checks,
            "pptx_structural_validation",
            receipt.get("packageIntegrity", {}).get("finding_count") == 0
            and receipt.get("presentationLayout", {}).get("finding_count") == 0,
            "package integrity and layout findings are 0",
            blocking=True,
        )

    if OFFLINE_RESULT.exists() and OFFLINE_REPEAT.exists():
        offline = json.loads(OFFLINE_RESULT.read_text(encoding="utf-8"))
        offline_repeat = json.loads(OFFLINE_REPEAT.read_text(encoding="utf-8"))

        def offline_decisions(payload: dict[str, Any], model: str) -> list[tuple[str, str]]:
            predictions = payload.get("models", {}).get(model, {}).get("predictions", [])
            return [(str(item.get("case_id")), str(item.get("decision"))) for item in predictions]

        add_check(
            checks,
            "benchmark_reproducibility",
            all(
                offline_decisions(offline, model) == offline_decisions(offline_repeat, model)
                for model in ("direct_llm_offline_proxy", "rag_offline_proxy", "forensics_deterministic")
            )
            and offline.get("case_count") == 20
            and offline_repeat.get("case_count") == 20,
            "two observable-policy benchmark runs match for all 20 decisions",
            blocking=True,
        )

    if UI_LOG.exists():
        ui = json.loads(UI_LOG.read_text(encoding="utf-8"))
        real = ui.get("real", {})
        hold = ui.get("hold", {})
        missing_evidence = ui.get("missingEvidence", {})
        local_packet = ui.get("localPacket", {})
        real_api = real.get("api", {})
        hold_api = hold.get("api", {})
        missing_api = missing_evidence.get("api", {})
        local_packet_api = local_packet.get("api", {})
        deterministic_pack_present = (
            real_api.get("investment_pack", {}).get("title") == "투자심의팩"
            and hold_api.get("investment_pack", {}).get("title") == "투자심의팩"
        )
        pack_export_enabled = (
            real.get("packDownloadEnabled") is True
            and hold.get("packDownloadEnabled") is True
            and real.get("packDownloadSmoke") is True
            and hold.get("packDownloadSmoke") is True
        )
        optional_llm_trace_present = (
            real.get("reflectionVisible") is True
            and hold.get("reflectionVisible") is True
            and real_api.get("plan", {}).get("source") == "llm_proposal"
            and len(real_api.get("tool_results", [])) >= 1
        )
        additional_material_gate_present = (
            missing_evidence.get("status", "").startswith("추가자료")
            and missing_api.get("status") == "needs_more_info"
            and missing_api.get("investment_pack", {}).get("decision") == "추가자료"
            and missing_api.get("valuation") is None
        )
        local_packet_gate_present = (
            local_packet.get("status", "").startswith("검토 가능")
            and local_packet_api.get("case_origin") == "local_case_packet"
            and local_packet_api.get("company_name") == "Company A"
            and local_packet_api.get("investment_pack", {}).get("data_origin") == "local_case_packet"
        )
        add_check(
            checks,
            "ui_execution_log",
            real.get("status", "").startswith("검토 가능")
            and hold.get("status", "").startswith("보류")
            and (optional_llm_trace_present or deterministic_pack_present)
            and pack_export_enabled
            and additional_material_gate_present,
            "real/hold/additional-material paths include the investment pack, export action, and deterministic fallback",
            blocking=True,
        )
        add_check(
            checks,
            "local_packet_execution",
            local_packet_gate_present,
            "local JSON packet path returns a company-specific investment pack",
            blocking=True,
        )

    rehearsal = run_deterministic_rehearsal()
    add_check(
        checks,
        "deterministic_demo_rehearsal",
        all(item["passed"] for item in rehearsal.values()),
        "clean/conflict/hold/period_mismatch/currency_mismatch/missing_evidence/real paths pass expected status and trace gates",
        blocking=True,
    )

    fallback = run_llm_failure_fallback()
    add_check(
        checks,
        "llm_failure_fallback",
        fallback["passed"],
        "LLM failure keeps deterministic review path and records retry nodes",
        blocking=True,
    )

    http_smoke = run_http_smoke()
    add_check(
        checks,
        "http_boundary_smoke",
        http_smoke.get("passed") is True,
        "ephemeral local server returns UI 200 and period-mismatch REVIEW/HOLD comparison",
        blocking=True,
    )

    approved_gateway_smoke = run_approved_gateway_smoke()
    add_check(
        checks,
        "approved_gateway_contract",
        approved_gateway_smoke.get("passed") is True,
        "provider-neutral approved gateway keeps typed allowlist and deterministic final decision",
        blocking=True,
    )

    model_allowlist_smoke = run_model_allowlist_smoke()
    add_check(
        checks,
        "model_allowlist_boundary",
        model_allowlist_smoke.get("passed") is True,
        "unapproved model is rejected before any network call",
        blocking=True,
    )

    public_submission_smoke = run_public_submission_smoke()
    public_status = public_submission_smoke.get("status")
    add_check(
        checks,
        "public_submission_links",
        public_submission_smoke.get("passed") is True,
        "demo URL and GitHub link smoke check; configure links before final submission",
        # Missing external links are a user-input gate; configured but failing
        # links are a real release failure and must not be hidden as a warning.
        blocking=public_status == "BLOCKED",
    )

    placeholder = False
    if PPTX_INSPECT.exists():
        placeholder = "(추후 입력)" in PPTX_INSPECT.read_text(encoding="utf-8")
    add_check(
        checks,
        "team_information",
        not placeholder,
        "team name, lead, and members are filled" if not placeholder else "cover still contains team-information placeholder",
        blocking=False,
    )

    video_ok = VIDEO.exists() and VIDEO.stat().st_size > 100_000
    add_check(
        checks,
        "local_video_fallback",
        video_ok,
        "current IC Preflight fallback video is present" if video_ok else "optional local fallback video is missing",
        blocking=False,
    )

    blocking_failures = [item["name"] for item in checks if item["blocking"]]
    user_actions = []
    if placeholder:
        user_actions.append("표지의 팀명·팀장·팀원·연락처 입력 후 PPTX/PDF 재생성")
    if public_status == "READY_AFTER_LINKS":
        user_actions.append("Demo URL·GitHub 링크 설정 후 python .\\mvp\\validate_public_submission.py 실행")
    if not video_ok:
        user_actions.append("선택 제출용 IC Preflight 시연영상 fallback 생성 또는 확인")
    needs_user_input = placeholder or public_status == "READY_AFTER_LINKS"
    status = "READY_AFTER_USER_INPUT" if not blocking_failures and needs_user_input else (
        "READY" if not blocking_failures else "BLOCKED"
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "version": "v0.9.2",
        "artifact_hashes": artifact_hashes,
        "checks": checks,
        "prelim_required_sections": prelim_sections,
        "rehearsal": rehearsal,
        "llm_failure_fallback": fallback,
        "http_smoke": http_smoke,
        "approved_gateway_smoke": approved_gateway_smoke,
        "model_allowlist_smoke": model_allowlist_smoke,
        "public_submission_smoke": public_submission_smoke,
        "user_actions": user_actions,
        "limitations": [
            "실제 KIC 내부 시간절감·재작업 수치는 측정하지 않았음",
            "offline baseline과 observable policy 통제군은 공개 케이스셋의 재현성 증거이며 live LLM 일반화 성능이 아님",
            "observable policy는 관측 신호와 사전에 설계한 규칙으로 구성된 결정론적 통제군임",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if status != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
