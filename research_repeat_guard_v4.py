from __future__ import annotations

import json
from pathlib import Path


def _urls(prefetch: dict, ticker: str, driver_id: str) -> list[str]:
    result = []
    for row in prefetch.get("company_targets") or []:
        if str(row.get("ticker") or "") == ticker and str(row.get("driver_id") or "") == driver_id:
            result += [str(x.get("source_url")) for x in row.get("candidate_sources") or [] if x.get("source_url")]
    if driver_id != "UNMAPPED_OPPORTUNITY":
        for row in prefetch.get("targets") or []:
            if str(row.get("driver_id") or "") == driver_id:
                result += [str(x.get("source_url")) for x in row.get("candidate_sources") or [] if x.get("source_url")]
    return sorted(set(result))


def filter_repeats(handoff: dict, prefetch: dict, previous: dict | None) -> tuple[dict, list[dict]]:
    previous = previous or {}
    old = {str(x.get("thesis_id")): x for x in previous.get("items") or [] if isinstance(x, dict)}
    kept = []
    skipped = []
    needed_drivers = set()
    for row in handoff.get("company_research_targets") or []:
        thesis = str(row.get("thesis_id") or f"{row.get('ticker')}|{row.get('driver_id')}")
        signature = {
            "question": row.get("research_question"),
            "urls": _urls(prefetch, str(row.get("ticker") or ""), str(row.get("driver_id") or "")),
            "wake": [row.get("reaction_state"), row.get("international_price_state"), row.get("entry_research_ready")],
        }
        prior = old.get(thesis) or {}
        if prior.get("outcome") == "UNRESOLVED" and prior.get("signature") == signature:
            skipped.append({"thesis_id": thesis, "ticker": row.get("ticker"), "driver_id": row.get("driver_id"), "reason": "NO_NEW_EVIDENCE_OR_SETUP_CHANGE"})
            continue
        row = dict(row)
        row["repeat_signature"] = signature
        kept.append(row)
        if row.get("missing_gate") == "CAUSAL_UNVERIFIED":
            needed_drivers.add(str(row.get("driver_id") or ""))

    filtered = dict(handoff)
    filtered["company_research_targets"] = kept
    filtered["research_targets"] = [
        row for row in handoff.get("research_targets") or []
        if str(row.get("driver_id") or "") in needed_drivers
    ]
    filtered["repeat_guard"] = {"skipped": skipped, "skipped_count": len(skipped)}
    return filtered, skipped


def load_previous(path: str = "output/research_execution_v4.json") -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
