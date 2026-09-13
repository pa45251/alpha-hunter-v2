from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

OUT = Path("output")
CONTRACT = "ALPHA_HUNTER_DEEP_REVIEW_PACKET_V4"
TRADE_STATES = {"BUY", "EARLY BUY", "WAIT"}


def _evidence_refs(row: dict) -> list[dict]:
    result = []
    seen = set()
    groups = (
        ("EXPOSURE", row.get("exposure_evidence") or []),
        ("COMPANY_CURRENT", row.get("evidence") or []),
        ("DRIVER_CURRENT", row.get("international_evidence") or []),
    )
    for scope, items in groups:
        for item in items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("source_url") or "")
            claim = str(item.get("claim") or "")
            if not url or not claim:
                continue
            key = (scope, url, claim)
            if key in seen:
                continue
            seen.add(key)
            evidence_id = "E_" + hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()[:12]
            result.append({
                "evidence_id": evidence_id,
                "scope": scope,
                "claim": claim,
                "source_title": item.get("source_title"),
                "source_url": url,
                "published_at": item.get("published_at"),
                "available_at": item.get("available_at"),
                "metric": item.get("metric"),
                "driver_id": item.get("driver_id"),
            })
    return result


def _admit(row: dict) -> tuple[bool, str]:
    state = str(row.get("decision_state") or row.get("action") or "")
    if state not in TRADE_STATES:
        return False, "NOT_THESIS_QUALIFIED_ACTION"
    if row.get("entry_risk_eligible") is not True:
        return False, "ENTRY_RISK_NOT_ELIGIBLE"
    if str(row.get("missing_gate") or "") not in {"ENTRY", ""}:
        return False, "THESIS_EVIDENCE_NOT_COMPLETE"
    if not str(row.get("company_transmission") or "").strip():
        return False, "COMPANY_TRANSMISSION_MISSING"
    refs = _evidence_refs(row)
    company_refs = [x for x in refs if x["scope"] in {"EXPOSURE", "COMPANY_CURRENT"}]
    if not company_refs:
        return False, "SOURCE_BACKED_COMPANY_MECHANISM_MISSING"
    if str(row.get("driver_scope") or "GLOBAL") == "GLOBAL":
        if not any(x["scope"] == "DRIVER_CURRENT" for x in refs):
            return False, "CURRENT_DRIVER_EVIDENCE_MISSING"
    if not str(row.get("what_would_make_us_wrong") or "").strip():
        return False, "FALSIFICATION_CONDITION_MISSING"
    return True, "ADMITTED"


def build_packet(out: Path = OUT) -> dict[str, Any]:
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    advisory_path = out / "opportunity_advisory.json"
    if not advisory_path.exists() or advisory_path.stat().st_size == 0:
        return {
            "contract": CONTRACT,
            "status": "INPUT_UNAVAILABLE",
            "run_id": manifest.get("run_id"),
            "targets": [],
            "excluded": [],
            "reason": "opportunity_advisory.json missing or empty",
        }
    advisory = json.loads(advisory_path.read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id") or "")
    if str(advisory.get("source_run_id") or "") != run_id:
        raise RuntimeError("DEEP_REVIEW_MIXED_SNAPSHOT")

    targets = []
    excluded = []
    for row in advisory.get("all_candidates") or []:
        if not isinstance(row, dict):
            continue
        admitted, reason = _admit(row)
        thesis = str(row.get("thesis_id") or f"{row.get('ticker')}|{row.get('driver_id') or row.get('driver')}")
        if not admitted:
            excluded.append({"thesis_id": thesis, "ticker": row.get("ticker"), "reason": reason})
            continue
        refs = _evidence_refs(row)
        targets.append({
            "thesis_id": thesis,
            "ticker": row.get("ticker"),
            "name": row.get("name"),
            "canonical_action": row.get("decision_state") or row.get("action"),
            "driver_id": row.get("driver_id"),
            "driver": row.get("driver"),
            "driver_scope": row.get("driver_scope"),
            "driver_state": row.get("driver_state"),
            "company_transmission": row.get("company_transmission"),
            "counter_evidence": row.get("main_counter_evidence"),
            "falsification": row.get("what_would_make_us_wrong"),
            "entry": row.get("entry"),
            "entry_low": row.get("entry_low"),
            "entry_high": row.get("entry_high"),
            "invalidation": row.get("invalidation"),
            "stop": row.get("stop"),
            "risk_pct": row.get("risk_pct"),
            "reward_risk": row.get("reward_risk"),
            "entry_risk_eligible": row.get("entry_risk_eligible"),
            "technical": row.get("technical"),
            "regime": row.get("regime"),
            "next_validation": row.get("add_trigger"),
            "review_question": "Try to falsify this thesis using only the supplied evidence. Does the canonical action remain justified?",
            "evidence": refs,
        })
    return {
        "contract": CONTRACT,
        "status": "PASS",
        "run_id": run_id,
        "public_lineage_id": advisory.get("public_lineage_id"),
        "auto_trade_allowed": False,
        "targets": targets,
        "excluded": excluded,
        "target_count": len(targets),
    }


if __name__ == "__main__":
    payload = build_packet()
    (OUT / "deep_review_packet_v4.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"deep review admission: status={payload['status']} targets={len(payload['targets'])}")
