from __future__ import annotations

"""Validation boundary for RippleGate's frozen public snapshot.

The adapter deliberately validates a local, date-stamped packet instead of
silently fetching arbitrary web pages during a demo. A future institutional
adapter can replace the loader while preserving the same source contract.
"""

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
PUBLIC_GRAPH_PATH = ROOT / "data" / "ripplegate_public_graph_v1.json"
ALLOWED_SOURCE_HOSTS = {
    "unctad.org",
    "www.unctad.org",
    "eia.gov",
    "www.eia.gov",
    "comtradeplus.un.org",
    "comtradeapi.un.org",
    "worldbank.org",
    "www.worldbank.org",
    "thedocs.worldbank.org",
}


def _host_allowed(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and port in {None, 443}
        and host in ALLOWED_SOURCE_HOSTS
    )


def validate_public_snapshot(graph: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    sources = graph.get("sources") if isinstance(graph.get("sources"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    source_by_id = {str(source.get("id")): source for source in sources if isinstance(source, dict) and source.get("id")}
    if graph.get("schema_version") != "impact-graph.v1":
        errors.append("schema_version must be impact-graph.v1")
    if graph.get("dataset") != "public_snapshot":
        errors.append("dataset must be public_snapshot")
    if not graph.get("as_of_date"):
        errors.append("as_of_date is required")
    for source_id, source in source_by_id.items():
        url = source.get("url")
        if not _host_allowed(str(url)):
            errors.append(f"source {source_id} has a non-allowlisted HTTPS URL")
        for field in ("title", "issuer", "period", "retrieved_at", "source_type", "verification_status"):
            if not str(source.get(field) or "").strip():
                errors.append(f"source {source_id} is missing provenance field: {field}")
        if source.get("source_type") != "official_public":
            errors.append(f"source {source_id} is not labelled official_public")
        if source.get("verification_status") not in {"linked", "reference_only", "not_loaded", "conflict"}:
            errors.append(f"source {source_id} has an unsupported verification_status")
        if source.get("verification_status") == "not_loaded":
            warnings.append(f"source {source_id} is not_loaded metadata-only and cannot support a numeric calculation")
        if source.get("verification_status") == "reference_only":
            warnings.append(f"source {source_id} is reference_only; raw response values are not included and cannot support a numeric calculation")
    for edge in edges:
        edge_id = str(edge.get("id"))
        evidence_ids = [str(item) for item in edge.get("evidence_ids", [])]
        missing = [item for item in evidence_ids if item not in source_by_id]
        if missing:
            errors.append(f"edge {edge_id} references missing sources: {','.join(missing)}")
        not_loaded = [item for item in evidence_ids if source_by_id.get(item, {}).get("verification_status") == "not_loaded"]
        if not_loaded and str(edge.get("status")) != "HOLD":
            errors.append(f"edge {edge_id} uses not_loaded sources without HOLD")
        if str(edge.get("status")) != "HOLD" and not evidence_ids:
            errors.append(f"edge {edge_id} has no evidence_ids")
    return {
        "schema_version": "ripplegate-public-adapter-report.v1",
        "passed": not errors,
        "dataset": graph.get("dataset"),
        "as_of_date": graph.get("as_of_date"),
        "source_count": len(source_by_id),
        "edge_count": len(edges),
        "allowlisted_hosts": sorted(ALLOWED_SOURCE_HOSTS),
        "errors": errors,
        "warnings": warnings,
        "disclosure": "URL allowlist·evidence 연결·not_loaded 차단만 검증하며, 출처 내용의 진실성이나 기관 운영 승인을 대신하지 않음",
    }


def load_public_snapshot(path: Path = PUBLIC_GRAPH_PATH) -> dict[str, Any]:
    graph = json.loads(path.read_text(encoding="utf-8"))
    report = validate_public_snapshot(graph)
    if not report["passed"]:
        raise ValueError("public snapshot validation failed: " + "; ".join(report["errors"]))
    return graph


def public_adapter_report(path: Path = PUBLIC_GRAPH_PATH) -> dict[str, Any]:
    graph = json.loads(path.read_text(encoding="utf-8"))
    return validate_public_snapshot(graph)
