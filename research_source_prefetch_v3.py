from __future__ import annotations

import argparse
import csv
import io
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

CONTRACT = "ALPHA_HUNTER_V3_RESEARCH_SOURCE_PREFETCH"
PROVIDER = "BING_NEWS_RSS"
ENDPOINT = "https://www.bing.com/news/search"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 AlphaHunterResearch/3.1"
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: str | None, limit: int = 900) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _compact_terms(value: str | None, limit: int = 180) -> str:
    text = _clean_text(value, limit=limit)
    text = re.sub(r"[^A-Za-z0-9%+./\- ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _published_at(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _unwrap_bing_url(value: str | None) -> str | None:
    url = html.unescape(str(value or "")).strip()
    if not url:
        return None
    for _ in range(2):
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return None
        host = (parsed.hostname or "").lower()
        if "bing.com" not in host:
            return url
        query = parse_qs(parsed.query)
        replacement = None
        for key in ("url", "u", "r"):
            vals = query.get(key) or []
            for candidate in vals:
                decoded = unquote(candidate)
                if decoded.startswith(("http://", "https://")):
                    replacement = decoded
                    break
            if replacement:
                break
        if not replacement:
            return None
        url = replacement
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} else None


def _search(query: str, timeout: float = 15.0, limit: int = 6) -> tuple[list[dict], str | None]:
    try:
        response = requests.get(
            ENDPOINT,
            params={"q": query, "format": "RSS", "count": max(10, limit * 2)},
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/xml, text/xml;q=0.9,*/*;q=0.8",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"

    results: list[dict] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        link = _unwrap_bing_url(item.findtext("link"))
        if not link or link in seen:
            continue
        seen.add(link)
        results.append(
            {
                "source_title": _clean_text(item.findtext("title"), limit=300),
                "source_url": link,
                "published_at": _published_at(item.findtext("pubDate")),
                "snippet": _clean_text(item.findtext("description"), limit=900),
            }
        )
        if len(results) >= limit:
            break
    return results, None


def _query_for(target: dict, lane: str) -> str:
    if target.get('ticker'):
        company = str(target.get('name') or '') + ' ' + str(target['ticker']).split('.')[0]
        terms = '營收' if lane == 'SUPPORT' else '衰退'
        return f'{company} {terms} {datetime.now(timezone.utc).year}'
    label = _compact_terms(target.get("driver_label") or target.get("driver_id"), 120)
    scope = _compact_terms(target.get("driver_scope"), 120)
    if lane == "SUPPORT":
        requirement = _compact_terms(target.get("activation_evidence_required"), 160)
    else:
        requirement = _compact_terms(target.get("counter_evidence_required"), 160)
    parts = [label, " ".join(requirement.split()[:7]), str(datetime.now(timezone.utc).year)]
    query = " ".join(x for x in parts if x).strip()
    return query[:420]


def official_company_revenue(targets: list[dict], timeout: float = 15.0) -> dict[str, list[dict]]:
    """Current official snapshots are evidence candidates, never historical backfills.

    retrieved_at/available_at bind availability to this run. Export date does not
    pretend the individual company's original announcement was known at midnight.
    """
    result = {}
    wanted = {str(t.get('ticker', '')).split('.')[0]: str(t.get('ticker')) for t in targets}
    for suffix, url in [('.TW', 'https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv'),
                        ('.TWO', 'https://mopsfin.twse.com.tw/opendata/t187ap05_O.csv')]:
        if not any(str(t.get('ticker', '')).endswith(suffix) for t in targets):
            continue
        try:
            response = requests.get(url, timeout=timeout, headers={'User-Agent': USER_AGENT})
            response.raise_for_status()
            rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
            if not rows or "公司代號" not in rows[0]:
                raise ValueError("OFFICIAL_REVENUE_SCHEMA_MISMATCH")
            observed = _utcnow()
            for row in rows:
                code = str(row.get('公司代號', '')).strip()
                if code not in wanted or not wanted[code].endswith(suffix):
                    continue
                result[wanted[code]] = [{
                    'source_title': f"Official monthly revenue: {row.get('公司名稱')} {row.get('資料年月')}",
                    'source_url': url, 'published_at': observed, 'available_at': observed,
                    'date_basis': 'CURRENT_DATASET_OBSERVED_AT; original issuer publication time unknown',
                    'export_date_roc': row.get('出表日期'),
                    'snippet': json.dumps(row, ensure_ascii=False),
                    'search_lane': 'OFFICIAL_COMPANY_REVENUE',
                }]
        except (requests.RequestException, ValueError, TypeError) as exc:
            print(f'Official revenue unavailable: {suffix} {type(exc).__name__}')
    return result


def build_prefetch(handoff: dict, *, timeout: float = 15.0, per_query: int = 5) -> dict:
    run_id = str(handoff.get("run_id") or handoff.get("research_run_id") or "")
    targets = [x for x in (handoff.get("research_targets") or []) if isinstance(x, dict)]
    if not run_id:
        raise RuntimeError("prefetch handoff missing run_id")
    if not targets:
        raise RuntimeError("prefetch handoff contains no research_targets")

    query_attempt_count = 0
    successful_query_count = 0
    errors: list[str] = []
    out_targets: list[dict] = []

    for target in targets:
        driver_id = str(target.get("driver_id") or "")
        target_candidates: list[dict] = []
        seen: set[str] = set()
        queries: list[dict] = []
        for lane in ("SUPPORT", "COUNTER"):
            query = _query_for(target, lane)
            query_attempt_count += 1
            rows, error = _search(query, timeout=timeout, limit=per_query)
            if error is None:
                successful_query_count += 1
            else:
                errors.append(f"{driver_id}:{lane}:{error}")
            queries.append(
                {
                    "lane": lane,
                    "query": query,
                    "status": "PASS" if error is None else "ERROR",
                    "result_count": len(rows),
                }
            )
            for row in rows:
                url = str(row.get("source_url") or "")
                if not url or url in seen:
                    continue
                seen.add(url)
                enriched = dict(row)
                enriched["search_lane"] = lane
                enriched["query"] = query
                target_candidates.append(enriched)

        out_targets.append(
            {
                "driver_id": driver_id,
                "ticker": target.get("ticker"),
                "queries": queries,
                "candidate_sources": target_candidates,
                "candidate_source_count": len(target_candidates),
            }
        )

    candidate_source_count = sum(int(x["candidate_source_count"]) for x in out_targets)
    sourced_target_count = sum(1 for x in out_targets if int(x["candidate_source_count"]) > 0)
    status = (
        "PASS"
        if query_attempt_count == len(targets) * 2
        and successful_query_count > 0
        and candidate_source_count > 0
        and sourced_target_count > 0
        else "FAIL_CLOSED"
    )
    company_sources = []
    if handoff.get('company_research_targets'):
        extra = build_prefetch({'run_id': run_id, 'research_targets': handoff['company_research_targets']}, timeout=timeout, per_query=per_query)
        company_sources = extra['targets']
        official = official_company_revenue(handoff['company_research_targets'], timeout)
        for target in company_sources:
            target['candidate_sources'] = official.get(target.get('ticker'), []) + target['candidate_sources']
            target['candidate_source_count'] = len(target['candidate_sources'])
    return {
        'company_targets': company_sources,
        "contract": CONTRACT,
        "status": status,
        "research_run_id": run_id,
        "provider": PROVIDER,
        "generated_at_utc": _utcnow(),
        "target_count": len(targets),
        "query_attempt_count": query_attempt_count,
        "successful_query_count": successful_query_count,
        "candidate_source_count": candidate_source_count,
        "sourced_target_count": sourced_target_count,
        "errors": errors[:20],
        "targets": out_targets,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--per-query", type=int, default=5)
    args = parser.parse_args()

    handoff = json.loads(Path(args.handoff).read_text(encoding="utf-8"))
    payload = build_prefetch(
        handoff,
        timeout=args.timeout,
        per_query=max(1, min(args.per_query, 8)),
    )
    Path(args.out).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "research source prefetch: "
        f"status={payload['status']} targets={payload['target_count']} "
        f"queries={payload['query_attempt_count']} successful_queries={payload['successful_query_count']} "
        f"candidate_sources={payload['candidate_source_count']} sourced_targets={payload['sourced_target_count']} "
        f"company_sources={sum(x['candidate_source_count'] for x in payload.get('company_targets', []))}"
    )
    if payload["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
