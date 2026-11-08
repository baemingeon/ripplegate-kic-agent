from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any


AS_OF_DATE = "2026-11-05"
SEC_CONTACT = os.getenv("KIC_SEC_CONTACT", "").strip()
SEC_HEADERS = {
    "User-Agent": f"ICPreflight/0.9.2 ({SEC_CONTACT})"
    if SEC_CONTACT
    else "ICPreflight/0.9.2 (contact-not-configured)",
}
COMPANIES = {
    "MA": {"name": "Mastercard", "cik": "0001141391", "role": "target"},
    "V": {"name": "Visa", "cik": "0001403161", "role": "candidate_peer"},
    "AXP": {"name": "American Express", "cik": "0000004962", "role": "candidate_peer"},
    "PYPL": {"name": "PayPal", "cik": "0001633917", "role": "candidate_peer"},
}


def get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers=headers or {"User-Agent": "ICPreflight/0.9.2 (public-demo-snapshot)"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def latest_annual_fact(facts: dict[str, Any], tags: list[str]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for tag in tags:
        fact = facts.get(tag)
        if not fact:
            continue
        for unit, values in fact.get("units", {}).items():
            for item in values:
                if item.get("form") not in {"10-K", "10-K/A"}:
                    continue
                if item.get("fp") != "FY" or item.get("filed", "") > AS_OF_DATE:
                    continue
                candidates.append({**item, "tag": tag, "unit": unit})
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item.get("end", ""), item.get("filed", "")))
    return candidates[-1]


def yahoo_close(ticker: str) -> dict[str, Any]:
    start = int(datetime.fromisoformat(AS_OF_DATE).replace(tzinfo=timezone.utc).timestamp())
    end = int((datetime.fromisoformat(AS_OF_DATE) + timedelta(days=1)).replace(tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start}&period2={end}&interval=1d&events=history"
    payload = get_json(url)
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    closes = result["indicators"]["quote"][0].get("close", [])
    if not timestamps or not closes or closes[-1] is None:
        raise RuntimeError(f"no close price for {ticker} on {AS_OF_DATE}")
    return {
        "ticker": ticker,
        "value": closes[-1],
        "unit": "USD/share",
        "as_of_date": AS_OF_DATE,
        "source_url": url,
        "source_type": "market_data",
    }


def company_record(ticker: str, metadata: dict[str, str]) -> dict[str, Any]:
    sec_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{metadata['cik']}.json"
    payload = get_json(sec_url, SEC_HEADERS)
    us_gaap = payload.get("facts", {}).get("us-gaap", {})
    revenue = latest_annual_fact(
        us_gaap,
        ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    )
    shares = latest_annual_fact(us_gaap, ["WeightedAverageNumberOfDilutedSharesOutstanding"])
    price = yahoo_close(ticker)
    return {
        "ticker": ticker,
        "name": metadata["name"],
        "role": metadata["role"],
        "sec_companyfacts_url": sec_url,
        "revenue": revenue,
        "diluted_shares": shares,
        "price": price,
    }


def evidence_for(record: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    revenue = record["revenue"]
    if revenue:
        evidence.append(
            {
                "id": f"{record['ticker']}-REV",
                "source_type": "SEC Company Facts",
                "source_url": record["sec_companyfacts_url"],
                "document_name": f"{record['name']} SEC companyfacts",
                "filed": revenue.get("filed"),
                "period_end": revenue.get("end"),
                "metric": "Revenue",
                "metric_definition": revenue.get("tag"),
                "value": revenue.get("val"),
                "unit": revenue.get("unit"),
                "verification_status": "retrieved",
            }
        )
    shares = record["diluted_shares"]
    if shares:
        evidence.append(
            {
                "id": f"{record['ticker']}-SHARES",
                "source_type": "SEC Company Facts",
                "source_url": record["sec_companyfacts_url"],
                "document_name": f"{record['name']} SEC companyfacts",
                "filed": shares.get("filed"),
                "period_end": shares.get("end"),
                "metric": "Diluted shares",
                "metric_definition": shares.get("tag"),
                "value": shares.get("val"),
                "unit": shares.get("unit"),
                "verification_status": "retrieved",
            }
        )
    evidence.append(
        {
            "id": f"{record['ticker']}-PRICE",
            "source_type": record["price"]["source_type"],
            "source_url": record["price"]["source_url"],
            "document_name": f"{record['name']} historical close",
            "filed": AS_OF_DATE,
            "period_end": AS_OF_DATE,
            "metric": "Close price",
            "metric_definition": "Unadjusted daily close",
            "value": record["price"]["value"],
            "unit": record["price"]["unit"],
            "verification_status": "retrieved",
        }
    )
    return evidence


def main() -> None:
    if not SEC_CONTACT:
        raise RuntimeError(
            "Set KIC_SEC_CONTACT to a real team contact before making SEC requests "
            "so the User-Agent identifies the client."
        )
    records = [company_record(ticker, metadata) for ticker, metadata in COMPANIES.items()]
    target = next(item for item in records if item["role"] == "target")
    target_period = target["revenue"]["end"] if target["revenue"] else None
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for record in records:
        if record["role"] != "candidate_peer":
            continue
        period = record["revenue"]["end"] if record["revenue"] else None
        if not record["revenue"] or not record["diluted_shares"]:
            exclusions.append({"ticker": record["ticker"], "reason": "required metric unavailable in SEC facts"})
            continue
        if period != target_period:
            exclusions.append({"ticker": record["ticker"], "reason": f"period mismatch: target {target_period}, candidate {period}"})
            continue
        market_cap_m = record["price"]["value"] * record["diluted_shares"]["val"] / 1_000_000
        revenue_m = record["revenue"]["val"] / 1_000_000
        candidates.append(
            {
                "ticker": record["ticker"],
                "name": record["name"],
                "period_end": period,
                "market_cap_usd_m": round(market_cap_m, 2),
                "revenue_usd_m": round(revenue_m, 2),
                "price_to_sales": round(market_cap_m / revenue_m, 2),
            }
        )
    target_market_cap_m = target["price"]["value"] * target["diluted_shares"]["val"] / 1_000_000 if target["diluted_shares"] else None
    target_revenue_m = target["revenue"]["val"] / 1_000_000 if target["revenue"] else None
    peer_median = median(item["price_to_sales"] for item in candidates) if candidates else None
    result = {
        "disclosure": "Public-source research snapshot. Market data source is Yahoo Finance chart API and requires license review before production use.",
        "as_of_date": AS_OF_DATE,
        "target": {
            "ticker": target["ticker"],
            "name": target["name"],
            "period_end": target_period,
            "market_cap_usd_m": round(target_market_cap_m, 2) if target_market_cap_m else None,
            "revenue_usd_m": round(target_revenue_m, 2) if target_revenue_m else None,
        },
        "eligible_peers": candidates,
        "excluded_candidates": exclusions,
        "valuation": {
            "method": "Price-to-sales peer median",
            "peer_median": peer_median,
            "implied_target_equity_usd_m": round(target_revenue_m * peer_median, 2) if target_revenue_m and peer_median else None,
        },
        "evidence": [item for record in records for item in evidence_for(record)],
        "notes": [
            "Peer selection is a validation result, not an investment recommendation.",
            "Visa may be excluded because its latest annual period does not align with the target period or required share fact is unavailable.",
            "All final results require analyst review and source-license confirmation.",
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
