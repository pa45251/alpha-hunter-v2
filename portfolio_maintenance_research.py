"""Private, ephemeral research lane for existing-position maintenance.

Opportunity research answers "what should we buy next?".  This module answers a
separate question: "are the economic drivers behind positions we already own
still active?"  Holdings and the derived maintenance target set must never be
committed.  The workflow writes handoff/result files under /tmp only.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from existing_position import RISK_GROUP_DRIVERS
from portfolio_risk import load_portfolio_state
from research_contract_v3 import ResearchContractError, validate_research_result

OUT = Path("output")
DEFAULT_HANDOFF = Path("/tmp/portfolio_maintenance_handoff.json")
DEFAULT_RAW = Path("/tmp/portfolio_maintenance_result.raw.txt")
DEFAULT_VALIDATED = Path("/tmp/portfolio_maintenance_result.json")
MAX_TARGETS = 12


def _ticker_key(v: Any) -> str:
    return str(v or "").strip().upper().removesuffix(".TWO").removesuffix(".TW")


def _list(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, (list, tuple, set)):
        return [str(x) for x in v if str(x).strip()]
    return []


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text: str) -> dict:
    text = text.strip().lstrip("\ufeff")
    if not text:
        raise ResearchContractError("empty maintenance research output")
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ResearchContractError("no valid top-level maintenance research JSON object")



def full_exposure_board(graph: pd.DataFrame, board: pd.DataFrame) -> pd.DataFrame:
    """Preserve canonical edges outside the opportunity funnel; never invent prices."""
    g = graph.copy()
    g = g[pd.to_numeric(g["enabled"], errors="coerce").eq(1)].copy()
    g["ticker"] = g["taiwan_code"].map(_ticker_key)
    g["dynamic_driver_state"] = "UNRESOLVED"
    g["reaction_state"] = "UNKNOWN"
    # The graph is a mapping, not current source-backed validation.
    g["provenance_status"] = "NEEDS_SOURCE_BACKFILL"
    b = board.copy()
    g["ticker_key"] = g["ticker"].map(_ticker_key)
    b["ticker_key"] = b["ticker"].map(_ticker_key)
    pairs = set(zip(b["ticker_key"], b["driver_id"]))
    missing = g[[p not in pairs for p in zip(g["ticker_key"], g["driver_id"])]]
    return pd.concat([b, missing], ignore_index=True)


def _current_inputs() -> tuple[str, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    from canonical_gate import validate_canonical_snapshot
    gate = validate_canonical_snapshot(OUT)
    if gate.get("gate_status") != "PASS":
        raise RuntimeError("maintenance lane canonical gate failed")
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id", ""))
    if not run_id:
        raise RuntimeError("maintenance lane missing canonical run_id")
    structural = pd.read_csv(OUT / "structural_matches.csv", dtype={"taiwan_code": str})
    taxonomy = pd.read_csv(OUT / "causal_driver_taxonomy.csv")
    if structural.empty or "run_id" not in structural.columns or not structural["run_id"].astype(str).eq(run_id).all():
        raise RuntimeError("maintenance lane MIXED_SNAPSHOT_DATA: structural_matches")
    graph = pd.read_csv(OUT / "structural_exposure_graph.csv", dtype={"taiwan_code": str})
    structural = full_exposure_board(graph, structural)
    return run_id, structural, taxonomy, load_portfolio_state()


def _system_drivers_for_position(pos: dict[str, Any], structural: pd.DataFrame) -> tuple[list[str], str]:
    ticker = _ticker_key(pos.get("ticker"))
    if ticker and not structural.empty and "ticker" in structural.columns:
        keys = structural["ticker"].fillna("").astype(str).map(_ticker_key)
        exact = structural.loc[keys.eq(ticker)]
        drivers = [str(x).upper() for x in exact.get("driver_id", pd.Series(dtype=str)).dropna().tolist() if str(x).strip()]
        if drivers:
            return list(dict.fromkeys(drivers)), "SYSTEM_TICKER_EXPOSURE"
    inferred: list[str] = []
    for group in _list(pos.get("risk_groups")):
        inferred.extend(RISK_GROUP_DRIVERS.get(group.upper(), []))
    if inferred:
        return list(dict.fromkeys(inferred)), "SYSTEM_RISK_GROUP"
    return [], "SYSTEM_MAPPING_MISSING"


def build_handoff(path: Path = DEFAULT_HANDOFF) -> dict[str, Any]:
    run_id, structural, taxonomy, portfolio = _current_inputs()
    positions = portfolio.get("positions") or [] if isinstance(portfolio, dict) else []

    ordered: list[str] = []
    mapping_counts: dict[str, int] = {}
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        drivers, mapping = _system_drivers_for_position(pos, structural)
        mapping_counts[mapping] = mapping_counts.get(mapping, 0) + 1
        for driver in drivers:
            if driver not in ordered:
                ordered.append(driver)

    enabled_ids = set(taxonomy.loc[pd.to_numeric(taxonomy["enabled"], errors="coerce").eq(1), "driver_id"].astype(str))
    ordered = [d for d in ordered if d in enabled_ids]
    selected = ordered[:MAX_TARGETS]
    truncated = max(0, len(ordered) - len(selected))
    tax = taxonomy.copy()
    if "driver_id" in tax.columns:
        tax["driver_id"] = tax["driver_id"].fillna("").astype(str).str.upper()
    lookup = {str(r.get("driver_id", "")).upper(): r for _, r in tax.iterrows()}

    targets = []
    for rank, driver_id in enumerate(selected, start=1):
        r = lookup.get(driver_id)
        targets.append({
            "research_priority": rank,
            "driver_id": driver_id,
            "driver_label": str(r.get("driver_label", driver_id)) if r is not None else driver_id,
            "driver_scope": str(r.get("driver_scope", "UNKNOWN")) if r is not None else "UNKNOWN",
            "activation_evidence_required": str(r.get("activation_evidence_required", "Source-backed evidence that the economic driver is currently active.")) if r is not None else "Source-backed evidence that the economic driver is currently active.",
            "counter_evidence_required": str(r.get("counter_evidence_required", "Evidence that the driver is inactive, reversed, or materially weakened.")) if r is not None else "Evidence that the driver is inactive, reversed, or materially weakened.",
            "price_cannot_activate_driver": True,
        })

    handoff = {
        "contract": "ALPHA_HUNTER_V3_PORTFOLIO_MAINTENANCE_HANDOFF",
        "research_run_id": run_id,
        "lane": "PORTFOLIO_MAINTENANCE",
        "causal_rule": "Research the economic driver itself. Price cannot create causality. Holdings are intentionally omitted.",
        "research_targets": targets,
        "target_count": len(targets),
        "target_truncated_count": truncated,
        "mapping_counts": mapping_counts,
        "privacy_rule": "No holdings, weights, balances, cost basis, P/L, or per-position actions are present in this handoff.",
    }
    path.write_text(json.dumps(handoff, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return handoff


def _unknown(driver_id: str, run_id: str, reason: str) -> dict[str, Any]:
    return {
        "driver_id": driver_id,
        "state": "UNKNOWN",
        "confidence": 0.0,
        "primary_cause": reason,
        "industry_scope": "UNKNOWN",
        "supporting_evidence": [],
        "counter_evidence": [],
        "source_count": 0,
        "event_date": None,
        "source_dates": [],
        "researched_at_utc": _utcnow(),
        "research_run_id": run_id,
    }


def ingest(handoff_path: Path = DEFAULT_HANDOFF, raw_path: Path = DEFAULT_RAW, out_path: Path = DEFAULT_VALIDATED) -> dict[str, Any]:
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    run_id = str(handoff.get("research_run_id", ""))
    target_ids = [str(x.get("driver_id", "")) for x in handoff.get("research_targets", []) if str(x.get("driver_id", ""))]
    target_set = set(target_ids)

    supplied: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    if target_ids:
        try:
            payload = _extract_json(raw_path.read_text(encoding="utf-8"))
            if str(payload.get("research_run_id", "")) != run_id:
                raise ResearchContractError("maintenance research run_id mismatch")
            results = payload.get("results")
            if not isinstance(results, list):
                raise ResearchContractError("maintenance results must be a list")
            for result in results:
                if not isinstance(result, dict):
                    errors.append("non-object result rejected")
                    continue
                driver_id = str(result.get("driver_id", ""))
                if driver_id not in target_set or driver_id in supplied:
                    errors.append(f"unnominated/duplicate maintenance driver rejected: {driver_id}")
                    continue
                try:
                    if str(result.get("research_run_id", "")) != run_id:
                        raise ResearchContractError("per-driver run_id mismatch")
                    validate_research_result(result, target_set)
                    urls = {
                        e.get("source_url")
                        for e in (result.get("supporting_evidence") or []) + (result.get("counter_evidence") or [])
                        if isinstance(e, dict) and e.get("source_url")
                    }
                    if int(result.get("source_count", -1)) != len(urls):
                        raise ResearchContractError("source_count must equal unique evidence URLs")
                    # Maintenance EXIT logic is stricter than opportunity discovery: an INACTIVE
                    # claim also needs external evidence. Unsupported negatives fail to UNKNOWN.
                    if str(result.get("state", "")).upper() == "INACTIVE" and len(urls) < 1:
                        raise ResearchContractError("maintenance INACTIVE requires source-backed evidence")
                    supplied[driver_id] = result
                except Exception as exc:
                    errors.append(f"{driver_id}: {exc}")
        except Exception as exc:
            errors.append(str(exc))

    final = [supplied.get(d) or _unknown(d, run_id, "Maintenance research missing or failed deterministic validation.") for d in target_ids]
    status = "PASS" if len(supplied) == len(target_ids) else ("NO_TARGETS" if not target_ids else "PARTIAL_FAIL_CLOSED")
    out = {
        "contract": "ALPHA_HUNTER_V3_VALIDATED_PORTFOLIO_MAINTENANCE",
        "status": status,
        "research_run_id": run_id,
        "validated_at_utc": _utcnow(),
        "target_count": len(target_ids),
        "validated_count": len(supplied),
        "target_truncated_count": int(handoff.get("target_truncated_count", 0) or 0),
        "errors": errors,
        "results": final,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def private_board_overlay(board: pd.DataFrame, run_id: str, path: Path | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Append ephemeral synthetic driver rows for the private existing-position engine only.

    These rows are never written back to decision_board.csv.  ACTIVE becomes a source-backed
    driver classification only. INACTIVE is kept separate from price BROKEN.
    UNKNOWN stays unresolved and therefore fails closed to REVIEW_RESEARCH.
    """
    p = path or Path(os.getenv("ALPHA_HUNTER_MAINTENANCE_RESEARCH_PATH", str(DEFAULT_VALIDATED)))
    if not p.exists():
        return board.copy(), {
            "maintenance_lane_status": "NOT_AVAILABLE",
            "maintenance_target_count": 0,
            "maintenance_validated_count": 0,
            "maintenance_private_artifact_committed": False,
        }
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return board.copy(), {
            "maintenance_lane_status": "INVALID_JSON",
            "maintenance_target_count": 0,
            "maintenance_validated_count": 0,
            "maintenance_private_artifact_committed": False,
        }
    if payload.get("contract") != "ALPHA_HUNTER_V3_VALIDATED_PORTFOLIO_MAINTENANCE" or str(payload.get("research_run_id", "")) != str(run_id):
        return board.copy(), {
            "maintenance_lane_status": "MIXED_OR_INVALID_SNAPSHOT",
            "maintenance_target_count": int(payload.get("target_count", 0) or 0),
            "maintenance_validated_count": 0,
            "maintenance_private_artifact_committed": False,
        }

    rows = []
    for r in payload.get("results") or []:
        state = str(r.get("state", "UNKNOWN")).upper()
        source_count = int(r.get("source_count", 0) or 0)
        source_backed = source_count > 0
        if state == "ACTIVE" and source_backed:
            dynamic, provenance, reaction = "UNRESOLVED", "UNRESOLVED", "UNKNOWN"
        elif state == "INACTIVE" and source_backed:
            dynamic, provenance, reaction = "UNRESOLVED", "UNRESOLVED", "UNKNOWN"
        else:
            dynamic, provenance, reaction = "UNRESOLVED", "UNRESOLVED", "MAINTENANCE_UNKNOWN"
        rows.append({
            "ticker": "",
            "driver_id": str(r.get("driver_id", "")),
            "dynamic_driver_state": dynamic,
            "provenance_status": provenance,
            "polarity": "POSITIVE",
            "reaction_state": reaction,
            "maintenance_state": state if source_backed else "UNKNOWN",
            "_private_maintenance_row": True,
        })

    private_board = board.copy()
    # Add mapping-only edges outside the opportunity filter, never fabricated prices.
    from canonical_gate import validate_canonical_snapshot
    from decision_engine import apply_edge_provenance
    gate = validate_canonical_snapshot(OUT)
    if gate.get("gate_status") == "PASS" and gate.get("run_id") == run_id:
        graph = pd.read_csv(OUT / "structural_exposure_graph.csv", dtype={"taiwan_code": str})
        full = full_exposure_board(graph, board)
        added = full.iloc[len(board):].copy()
        if not added.empty:
            added = added.drop(columns=[c for c in added if c.startswith("edge_") or c == "researched_provenance_status"], errors="ignore")
            added = apply_edge_provenance(added, Path("input/edge_provenance.csv"))
            private_board = pd.concat([board, added], ignore_index=True)
    private_board["_private_maintenance_row"] = False
    if rows:
        private_board = pd.concat([private_board, pd.DataFrame(rows)], ignore_index=True, sort=False)
    return private_board, {
        "maintenance_lane_status": str(payload.get("status", "UNKNOWN")),
        "maintenance_target_count": int(payload.get("target_count", 0) or 0),
        "maintenance_validated_count": int(payload.get("validated_count", 0) or 0),
        "maintenance_target_truncated_count": int(payload.get("target_truncated_count", 0) or 0),
        "maintenance_private_artifact_committed": False,
        "maintenance_privacy_rule": "Maintenance target/result artifacts remain ephemeral; only aggregate metadata may enter public decision_packet.json.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build", "ingest"])
    args = parser.parse_args()
    if args.command == "build":
        h = build_handoff()
        print(json.dumps({"target_count": h["target_count"], "target_truncated_count": h["target_truncated_count"], "mapping_counts": h["mapping_counts"]}, sort_keys=True))
    else:
        r = ingest()
        print(json.dumps({"status": r["status"], "target_count": r["target_count"], "validated_count": r["validated_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
