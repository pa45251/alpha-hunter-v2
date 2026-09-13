from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from company_source_documents import acquire
from research_source_prefetch_v3 import _search

VERSION = "TARGETED_RETRIEVAL_V1"
MAX_COMPANY_DOCS = 12
MAX_DRIVER_DOCS = 8

DRIVER_HINTS = {
    "AI_SERVER_SHIPMENTS": "AI server units rack shipments ODM backlog hyperscaler orders server demand",
    "NAND_STORAGE_CYCLE": "NAND contract price SSD controller module demand inventory shipments",
    "COPPER_COMMODITY_TRADE_INVENTORY": "LME COMEX copper inventories physical premium imports exports smelter supply tightness",
    "CONTAINER_FREIGHT": "container spot contract freight rates liner utilization blank sailings volumes",
    "DRY_BULK_FREIGHT": "Baltic Dry Index Capesize Panamax rates iron ore coal volumes vessel supply",
}

SLOT_TERMS = {
    "CAN": "產品 應用 客戶 終端市場 product application customer end market business mix",
    "REACH": "法說 訂單 出貨 ASP backlog utilization 產能 稼動 產品組合 shipment order pricing mix guidance",
    "COUNTER": "法說 需求 庫存 毛利 風險 slowdown inventory margin cancellation weakness risk",
}


def _compact(value, limit=180):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _company_slots(target):
    gap = str(target.get("missing_gate") or "")
    exposure_known = bool(target.get("exposure_source_urls") or target.get("exposure_resolution_status"))
    if exposure_known and gap in {"CAUSAL_UNVERIFIED", "COMPANY_TRANSMISSION_UNVERIFIED"}:
        return ("REACH", "COUNTER")
    return ("CAN", "REACH", "COUNTER")


def _company_query(target, slot):
    company = (str(target.get("name") or "") + " " + str(target.get("ticker") or "").split(".")[0]).strip()
    driver_id = str(target.get("driver_id") or "")
    driver = "" if driver_id == "UNMAPPED_OPPORTUNITY" else _compact(
        " ".join(x for x in [target.get("driver_label"), target.get("global_theme"), target.get("driver_scope")] if x), 150
    )
    return _compact(" ".join(x for x in [company, driver, SLOT_TERMS[slot]] if x), 420)


def _driver_query(target, lane):
    driver_id = str(target.get("driver_id") or "")
    label = _compact(target.get("driver_label") or driver_id, 120)
    scope = _compact(DRIVER_HINTS.get(driver_id) or target.get("driver_scope"), 200)
    if lane == "SUPPORT":
        tail = "demand shipments orders pricing utilization inventory current"
    else:
        tail = "contradictory weakness oversupply inventory slowdown cancellation current"
    return _compact(f"{label} {scope} {tail} {datetime.now(timezone.utc).year}", 420)


def _terms(target, slot):
    pieces = [
        target.get("name"),
        str(target.get("ticker") or "").split(".")[0],
        target.get("driver_label"),
        target.get("global_theme"),
        target.get("driver_scope"),
        DRIVER_HINTS.get(str(target.get("driver_id") or "")),
        SLOT_TERMS.get(slot),
    ]
    words = []
    for piece in pieces:
        for token in re.split(r"[\s,;/|()]+", str(piece or "")):
            token = token.strip().lower()
            if len(token) >= 2 and token not in words:
                words.append(token)
    return words[:40]


def _focused_text(text, terms, max_chars=12000):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= max_chars:
        return text
    lower = text.lower()
    hits = []
    for term in terms:
        start = 0
        while len(hits) < 10:
            idx = lower.find(term, start)
            if idx < 0:
                break
            hits.append(idx)
            start = idx + max(1, len(term))
        if len(hits) >= 10:
            break
    if not hits:
        return text[:max_chars]
    windows = []
    for idx in sorted(set(hits))[:8]:
        windows.append(text[max(0, idx - 700): min(len(text), idx + 1300)])
    focused = " ... ".join(windows)
    return focused[:max_chars]


def _score(source, requested_slots, terms):
    slot = str(source.get("evidence_slot") or "")
    lane = str(source.get("search_lane") or "")
    title = str(source.get("source_title") or "").lower()
    text = str(source.get("document_text") or "").lower()
    score = 0
    if source.get("fetch_status") == "FETCHED":
        score += 10
    if lane in {"STRUCTURAL_EXPOSURE", "CURRENT_TRANSMISSION"}:
        score += 8
    if lane == "STRUCTURAL_IDENTITY":
        score += 2
    if lane == "OFFICIAL_COMPANY_REVENUE":
        score -= 2
    if slot in requested_slots:
        score += 5
    for kw in ("法說", "investor", "presentation", "earnings", "financial", "產品", "product"):
        if kw in title:
            score += 2
    score += min(6, sum(1 for term in terms[:20] if term in title or term in text))
    return score


def _dedupe(sources):
    out, seen = [], set()
    for source in sources:
        url = str(source.get("resolved_url") or source.get("source_url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(source)
    return out


def _prepare_source(source, target, slot, timeout):
    row = dict(source)
    row.setdefault("evidence_slot", slot)
    if row.get("fetch_status") != "FETCHED":
        row = acquire(row, timeout)
    if row.get("fetch_status") == "FETCHED" and row.get("document_text"):
        terms = _terms(target, row.get("evidence_slot") or slot)
        focused = _focused_text(row["document_text"], terms)
        row["document_text"] = focused
        row["document_sha256"] = hashlib.sha256(focused.encode()).hexdigest()
        row["retrieval_focus_version"] = VERSION
    row.pop("_links", None)
    return row


def _enhance_company(target, packet, timeout, per_query):
    slots = _company_slots(target)
    sources = list(packet.get("candidate_sources") or [])
    seen = {str(s.get("resolved_url") or s.get("source_url") or "") for s in sources}
    queries = list(packet.get("queries") or [])
    for slot in slots:
        query = _company_query(target, slot)
        rows, error = _search(query, timeout=timeout, limit=per_query)
        queries.append({"lane": slot, "evidence_slot": slot, "query": query,
                        "status": "PASS" if error is None else "ERROR", "result_count": len(rows)})
        for row in rows:
            url = str(row.get("source_url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            row = dict(row, search_lane=slot, evidence_slot=slot, query=query)
            sources.append(_prepare_source(row, target, slot, timeout))

    normalized = []
    for source in sources:
        lane = str(source.get("search_lane") or "")
        slot = str(source.get("evidence_slot") or "")
        if not slot:
            slot = "CAN" if lane == "STRUCTURAL_EXPOSURE" else "REACH" if lane == "CURRENT_TRANSMISSION" else "CONTEXT"
        normalized.append(_prepare_source(source, target, slot, timeout))
    normalized = _dedupe(normalized)
    terms = _terms(target, "REACH")

    # Preserve at least the strongest evidence for each requested slot, then fill by relevance.
    chosen, chosen_urls = [], set()
    for slot in slots:
        candidates = [s for s in normalized if s.get("evidence_slot") == slot and s.get("fetch_status") == "FETCHED"]
        for source in sorted(candidates, key=lambda s: _score(s, slots, terms), reverse=True)[:2]:
            url = str(source.get("resolved_url") or source.get("source_url"))
            if url not in chosen_urls:
                chosen.append(source); chosen_urls.add(url)
    for source in sorted(normalized, key=lambda s: _score(s, slots, terms), reverse=True):
        if len(chosen) >= MAX_COMPANY_DOCS:
            break
        url = str(source.get("resolved_url") or source.get("source_url"))
        if url not in chosen_urls:
            chosen.append(source); chosen_urls.add(url)

    packet["candidate_sources"] = chosen
    packet["candidate_source_count"] = len(chosen)
    packet["document_count"] = sum(s.get("fetch_status") == "FETCHED" for s in chosen)
    packet["retrieval_slots"] = list(slots)
    packet["queries"] = queries
    packet["targeted_retrieval_version"] = VERSION
    return packet


def _enhance_driver(target, packet, timeout, per_query):
    sources = list(packet.get("candidate_sources") or [])
    seen = {str(s.get("resolved_url") or s.get("source_url") or "") for s in sources}
    queries = list(packet.get("queries") or [])
    for lane in ("SUPPORT", "COUNTER"):
        query = _driver_query(target, lane)
        rows, error = _search(query, timeout=timeout, limit=per_query)
        queries.append({"lane": lane, "evidence_slot": "NOW" if lane == "SUPPORT" else "COUNTER",
                        "query": query, "status": "PASS" if error is None else "ERROR", "result_count": len(rows)})
        for row in rows:
            url = str(row.get("source_url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            slot = "NOW" if lane == "SUPPORT" else "COUNTER"
            row = dict(row, search_lane=lane, evidence_slot=slot, query=query)
            sources.append(_prepare_source(row, target, slot, timeout))
    normalized = [_prepare_source(s, target, s.get("evidence_slot") or "NOW", timeout) for s in sources]
    normalized = [s for s in _dedupe(normalized) if s.get("fetch_status") == "FETCHED"]
    terms = _terms(target, "NOW")
    normalized.sort(key=lambda s: _score(s, {"NOW", "COUNTER"}, terms), reverse=True)
    packet["candidate_sources"] = normalized[:MAX_DRIVER_DOCS]
    packet["candidate_source_count"] = len(packet["candidate_sources"])
    packet["queries"] = queries
    packet["targeted_retrieval_version"] = VERSION
    return packet


def enhance_prefetch(handoff, prefetch, *, timeout=12, per_query=3):
    driver_meta = {str(t.get("driver_id")): t for t in handoff.get("research_targets", [])}
    company_meta = {(str(t.get("ticker")), str(t.get("driver_id")), str(t.get("event_id") or "")): t
                    for t in handoff.get("company_research_targets", [])}

    for packet in prefetch.get("targets", []):
        meta = driver_meta.get(str(packet.get("driver_id")))
        if meta:
            _enhance_driver(meta, packet, timeout, per_query)

    for packet in prefetch.get("company_targets", []):
        key = (str(packet.get("ticker")), str(packet.get("driver_id")), str(packet.get("event_id") or ""))
        meta = company_meta.get(key) or company_meta.get((key[0], key[1], ""))
        if meta:
            _enhance_company(meta, packet, timeout, per_query)

    prefetch["targeted_retrieval_version"] = VERSION
    prefetch["candidate_source_count"] = sum(int(x.get("candidate_source_count", 0)) for x in prefetch.get("targets", []))
    prefetch["sourced_target_count"] = sum(1 for x in prefetch.get("targets", []) if x.get("candidate_source_count", 0))
    company_docs = sum(int(x.get("document_count", 0)) for x in prefetch.get("company_targets", []))
    print(f"targeted retrieval: drivers={prefetch['sourced_target_count']}/{len(prefetch.get('targets', []))} company_docs={company_docs}", flush=True)
    return prefetch
