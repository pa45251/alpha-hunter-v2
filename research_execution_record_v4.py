from __future__ import annotations

import json
from pathlib import Path

CONTRACT = "ALPHA_HUNTER_RESEARCH_EXECUTION_V4"


def record(handoff_path: Path, research_path: Path, out_path: Path) -> dict:
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    research = json.loads(research_path.read_text(encoding="utf-8"))
    opportunities = {
        (str(x.get("ticker")), str(x.get("driver_id")))
        for x in research.get("company_opportunities") or [] if isinstance(x, dict)
    }
    coverage = {
        (str(x.get("ticker")), str(x.get("driver_id"))): x
        for x in research.get("company_research_coverage") or [] if isinstance(x, dict)
    }
    items = []
    for row in handoff.get("company_research_targets") or []:
        ticker = str(row.get("ticker") or "")
        driver = str(row.get("driver_id") or "")
        thesis = str(row.get("thesis_id") or f"{ticker}|{driver}")
        key = (ticker, driver)
        outcome = (coverage.get(key) or {}).get("status") or ("RESOLVED" if key in opportunities else "UNRESOLVED")
        reason = (coverage.get(key) or {}).get("reason")
        items.append({
            "thesis_id": thesis,
            "ticker": ticker,
            "driver_id": driver,
            "outcome": outcome,
            "reason": reason,
            "signature": row.get("repeat_signature"),
            "origin_research_run_id": research.get("research_run_id"),
        })
    payload = {
        "contract": CONTRACT,
        "run_id": research.get("research_run_id"),
        "research_status": research.get("status"),
        "items": items,
        "repeat_guard": handoff.get("repeat_guard") or {},
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    record(Path("/tmp/research_handoff.json"), Path("output/research_result_v3.json"), Path("output/research_execution_v4.json"))
