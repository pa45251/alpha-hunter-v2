from __future__ import annotations

# Final live-validation trigger marker; no policy or threshold effect.
import hashlib
from pathlib import Path
from typing import Any


def thesis_id(ticker: str, driver_id: str, event_id: str | None = None) -> str:
    raw = f"{ticker}|{driver_id}|{event_id or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _question(row: dict) -> str:
    gate = str(row.get("missing_gate") or "")
    name = str(row.get("name") or row.get("ticker") or "company")
    driver = str(row.get("driver_label") or row.get("driver_id") or "driver")
    if gate == "DRIVER_UNKNOWN":
        return f"Which source-backed economic exposure or specific company event can materially affect {name}, independent of its stock price?"
    if gate == "CAUSAL_UNVERIFIED":
        return f"Is {driver} currently changing in the real economy on non-price evidence, and what is the strongest counter-evidence?"
    if gate == "COMPANY_TRANSMISSION_UNVERIFIED":
        return f"Is the current {driver} change actually transmitting to {name}'s orders, shipments, pricing, mix or revenue?"
    return "No decision-changing research question."


def _classify(row: dict) -> tuple[str, str, str]:
    gate = str(row.get("missing_gate") or "")
    reaction = str(row.get("reaction_state") or "")
    price_ready = bool(row.get("entry_research_ready"))
    if gate == "ECONOMIC_DRIVER_REJECTED" or reaction == "BROKEN":
        return "DROP_THIS_RUN", "Economic thesis rejected or setup broken", "NEW_SESSION_OR_NEW_NONPRICE_EVENT"
    if gate == "ENTRY":
        return "NO_RESEARCH", "Thesis already reached entry gate", "ENTRY_OR_REGIME_CHANGE"
    if gate in {"GLOBAL_PRICE_WEAK", "GLOBAL_PRICE_UNCONFIRMED"}:
        return "OBSERVE", "Global price is a trading-risk blocker, not an economic research question", "GLOBAL_PRICE_STATE_CHANGE"
    if row.get("price_data_status") == "MISSING_OR_INSUFFICIENT":
        return "OBSERVE", "Sealed price data missing or insufficient; setup not evaluated", "PRICE_DATA_REPAIRED"
    if not price_ready or reaction == "EXTENDED":
        return "OBSERVE", "Evidence gap exists but current setup cannot change action", "ENTRY_SETUP_OR_NEW_NONPRICE_EVENT"
    if gate in {"DRIVER_UNKNOWN", "CAUSAL_UNVERIFIED", "COMPANY_TRANSMISSION_UNVERIFIED"}:
        return "FACT_CHECK", "A bounded factual question can change the current action", "SOURCE_OR_SETUP_CHANGE"
    return "OBSERVE", "No actionable evidence gap", "MATERIAL_STATE_CHANGE"


def apply_admission(handoff: dict[str, Any], *, out: Path = Path("output")) -> dict[str, Any]:
    """Convert broad unresolved nominations into a bounded fact-check queue.

    No score and no Top-N quota is introduced. Price can make a fact question worth
    answering now, but can never establish the answer or create causality.
    """
    from research_handoff import company_research_targets

    all_rows = company_research_targets(out, research_only=False)
    admitted: list[dict] = []
    deferred: list[dict] = []
    admitted_driver_ids: set[str] = set()

    for source in all_rows:
        row = dict(source)
        row["thesis_id"] = thesis_id(str(row.get("ticker")), str(row.get("driver_id")), row.get("event_id"))
        state, reason, wake = _classify(row)
        row["admission_state"] = state
        row["admission_reason"] = reason
        row["wake_condition"] = wake
        row["research_question"] = _question(row)
        row["action_impact"] = {
            "DRIVER_UNKNOWN": "Resolve exposure/local-event identity before risk is allowed",
            "CAUSAL_UNVERIFIED": "Current driver evidence may advance or veto the thesis",
            "COMPANY_TRANSMISSION_UNVERIFIED": "Company evidence may advance or veto the thesis",
        }.get(str(row.get("missing_gate")), "No immediate action impact")
        if state == "FACT_CHECK":
            admitted.append(row)
            if row.get("missing_gate") == "CAUSAL_UNVERIFIED" and row.get("driver_id"):
                admitted_driver_ids.add(str(row["driver_id"]))
        else:
            deferred.append({
                "ticker": row.get("ticker"),
                "thesis_id": row["thesis_id"],
                "driver_id": row.get("driver_id"),
                "missing_gate": row.get("missing_gate"),
                "admission_predicates": admission_predicates(row),
                "entry_research_reason": row.get("entry_research_reason"),
                "admission_state": state,
                "admission_reason": reason,
                "wake_condition": wake,
            })

    shared = []
    seen = set()
    for driver in handoff.get("research_targets") or []:
        driver_id = str(driver.get("driver_id") or "")
        if driver_id in admitted_driver_ids and driver_id not in seen:
            shared.append(driver)
            seen.add(driver_id)

    result = dict(handoff)
    result["contract"] = "ALPHA_HUNTER_RESEARCH_ADMISSION_V4"
    result["research_targets"] = shared
    result["company_research_targets"] = admitted
    result["deferred_candidates"] = deferred
    result["admission_completeness"] = audit_completeness(all_rows)
    result["admission_summary"] = {
        "audit_candidates": len(all_rows),
        "fact_check_targets": len(admitted),
        "shared_driver_questions": len(shared),
        "deferred_candidates": len(deferred),
    }
    return result


def admission_predicates(row):
    return {k: row.get(k) for k in ('missing_gate', 'reaction_state', 'entry_research_ready', 'price_data_status')}


def audit_completeness(rows):
    """Replay every predicate tuple; no rank, ticker or quota influences admission."""
    import json
    classes, ledger = {}, []
    seen = set()
    for row in rows:
        tid = thesis_id(str(row.get('ticker')), str(row.get('driver_id')), row.get('event_id'))
        if tid in seen:
            raise ValueError('DUPLICATE_ADMISSION_THESIS')
        seen.add(tid)
        predicates = admission_predicates(row)
        key = json.dumps(predicates, sort_keys=True)
        outcome = _classify(row)
        if key in classes and classes[key] != outcome:
            raise ValueError('NONDETERMINISTIC_ADMISSION')
        classes[key] = outcome
        ledger.append(dict(thesis_id=tid, ticker=row.get('ticker'), driver_id=row.get('driver_id'),
                           predicates=predicates, admission_state=outcome[0], reason=outcome[1],
                           entry_reason=row.get('entry_research_reason')))
    return dict(evaluated=len(rows), predicate_classes=len(classes), deterministic=True, ledger=ledger)
