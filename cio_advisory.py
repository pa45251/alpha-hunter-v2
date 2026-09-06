from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json

import pandas as pd


OUT = Path("output")
ADVISORY_VERSION = "1.0"
ENTRY_FRIENDLY_STATES = {"PRE_CONFIRMATION", "EARLY_CONFIRMATION", "CONFIRMING", "PULLBACK"}
DIRECT_LINKAGES = {"DIRECT", "STRONG"}

ACTION_PRIORITY = {
    "BUY_BIAS_STOCK": 0,
    "PREFER_ETF": 1,
    "PROVISIONAL_BUY_BIAS_STOCK": 2,
    "HOLD_BIAS": 3,
    "WAIT_PULLBACK": 4,
    "RESEARCH_FIRST": 5,
    "PASS": 6,
    "AVOID": 7,
}


def _s(row: pd.Series, key: str) -> str:
    return str(row.get(key, "") or "").strip().upper()


def _f(row: pd.Series, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except Exception:
        return default


def _missing_evidence(row: pd.Series) -> list[str]:
    missing: list[str] = []
    if _s(row, "dynamic_driver_state") != "ACTIVE_RESEARCH_VALIDATED":
        missing.append("ACTIVE_DRIVER_VALIDATION")
    if _s(row, "provenance_status") != "SOURCE_BACKED":
        missing.append("COMPANY_EDGE_SOURCE_BACKING")
    if not str(row.get("etf_ticker", "") or "").strip():
        missing.append("ETF_MAPPING")
    return missing


def _advisory_for_row(row: pd.Series) -> dict[str, object]:
    driver = _s(row, "dynamic_driver_state")
    polarity = _s(row, "polarity")
    provenance = _s(row, "provenance_status")
    reaction = _s(row, "reaction_state")
    route = _s(row, "stock_vs_etf_state")
    linkage = _s(row, "linkage_tier")
    linkage_conf = _f(row, "linkage_confidence")
    etf_ticker = str(row.get("etf_ticker", "") or "").strip().upper()

    source_backed = provenance == "SOURCE_BACKED"
    active = driver == "ACTIVE_RESEARCH_VALIDATED"
    direct = linkage in DIRECT_LINKAGES and linkage_conf >= 0.70
    etf_fallback = bool(etf_ticker) and route in {"ETF_CORE_PREFERRED", "STOCK_BLOCKED_WEAK_EDGE"}

    if polarity != "POSITIVE":
        return {
            "advisory_action": "PASS",
            "advisory_confidence": "HIGH",
            "preferred_exposure": "CASH",
            "advisory_rationale": "No validated positive long transmission edge.",
        }

    if driver == "INACTIVE_RESEARCH_VALIDATED":
        return {
            "advisory_action": "AVOID",
            "advisory_confidence": "HIGH",
            "preferred_exposure": "CASH",
            "advisory_rationale": "The causal driver is research-validated inactive.",
        }

    if not active:
        return {
            "advisory_action": "RESEARCH_FIRST",
            "advisory_confidence": "INSUFFICIENT",
            "preferred_exposure": "CASH",
            "advisory_rationale": "The causal driver is not validated active; price strength cannot substitute for causality.",
        }

    if reaction == "BROKEN":
        return {
            "advisory_action": "AVOID",
            "advisory_confidence": "HIGH" if source_backed else "MEDIUM",
            "preferred_exposure": "CASH",
            "advisory_rationale": "The expected Taiwan transmission is broken despite an active global driver.",
        }

    # Important architecture rule: weak/unverified Taiwan stock alpha does NOT block
    # the clean global ETF route. Company provenance is a stock gate, not an ETF gate.
    if route == "ETF_CORE_PREFERRED" or etf_fallback:
        return {
            "advisory_action": "PREFER_ETF",
            "advisory_confidence": "HIGH" if route == "ETF_CORE_PREFERRED" else "MEDIUM",
            "preferred_exposure": "ETF",
            "advisory_rationale": "Global driver is active; ETF is the cleaner exposure because stock alpha is not clearly superior or is not source-backed.",
        }

    if reaction == "EXTENDED":
        return {
            "advisory_action": "WAIT_PULLBACK",
            "advisory_confidence": "HIGH" if source_backed else "MEDIUM",
            "preferred_exposure": "CASH_UNTIL_ENTRY",
            "advisory_rationale": "The thesis may be intact, but current price state is extended and chase risk dominates.",
        }

    if source_backed and route == "STOCK_ALPHA_RESEARCH":
        if reaction in ENTRY_FRIENDLY_STATES:
            return {
                "advisory_action": "BUY_BIAS_STOCK",
                "advisory_confidence": "HIGH" if reaction in {"CONFIRMING", "PULLBACK"} else "MEDIUM",
                "preferred_exposure": "STOCK",
                "advisory_rationale": "Active driver, source-backed company edge, and a non-extended reaction state support a positive stock bias.",
            }
        if reaction == "PERSISTENT":
            return {
                "advisory_action": "HOLD_BIAS",
                "advisory_confidence": "MEDIUM",
                "preferred_exposure": "STOCK",
                "advisory_rationale": "The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing.",
            }

    if not source_backed and direct:
        if reaction in ENTRY_FRIENDLY_STATES:
            return {
                "advisory_action": "PROVISIONAL_BUY_BIAS_STOCK",
                "advisory_confidence": "LOW",
                "preferred_exposure": "STOCK_RESEARCH_ONLY",
                "advisory_rationale": "Active driver and strong structural linkage create a favorable hypothesis, but company-level source backing is still missing.",
            }
        if reaction == "PERSISTENT":
            return {
                "advisory_action": "HOLD_BIAS",
                "advisory_confidence": "LOW",
                "preferred_exposure": "STOCK_RESEARCH_ONLY",
                "advisory_rationale": "Price transmission is persistent, but company-level source backing is incomplete; do not convert this into an executable buy.",
            }

    if etf_ticker:
        return {
            "advisory_action": "PREFER_ETF",
            "advisory_confidence": "MEDIUM",
            "preferred_exposure": "ETF",
            "advisory_rationale": "The global driver is active but the stock case is not sufficiently verified; prefer the mapped ETF exposure.",
        }

    return {
        "advisory_action": "RESEARCH_FIRST",
        "advisory_confidence": "LOW",
        "preferred_exposure": "CASH",
        "advisory_rationale": "The global driver is active, but neither a sufficiently verified stock edge nor a clean ETF fallback is available.",
    }


def build_cio_advisory(board: pd.DataFrame) -> pd.DataFrame:
    if board is None or board.empty:
        return pd.DataFrame()

    x = board.copy()
    decisions = x.apply(_advisory_for_row, axis=1, result_type="expand")
    for col in decisions.columns:
        x[col] = decisions[col]

    x["advisory_version"] = ADVISORY_VERSION
    x["advisory_missing_evidence"] = x.apply(lambda r: ";".join(_missing_evidence(r)), axis=1)
    x["advisory_is_order"] = False
    x["auto_trade_allowed"] = False
    x["advisory_priority"] = x["advisory_action"].map(ACTION_PRIORITY).fillna(99).astype(int)
    x["research_priority_score"] = pd.to_numeric(x.get("research_priority_score", 0), errors="coerce").fillna(0.0)

    # Deduplicate ETF fallbacks so one global driver does not appear multiple times merely
    # because several Taiwan stocks map to the same ETF. Stock ideas remain ticker-specific.
    exposure_key = []
    for _, r in x.iterrows():
        if str(r.get("preferred_exposure", "")).upper() == "ETF":
            exposure_key.append(f"ETF::{r.get('driver_id', '')}::{r.get('etf_ticker', '')}")
        else:
            exposure_key.append(f"STOCK::{r.get('driver_id', '')}::{r.get('ticker', '')}")
    x["_advisory_key"] = exposure_key
    x = x.sort_values(["advisory_priority", "research_priority_score"], ascending=[True, False])
    x = x.drop_duplicates("_advisory_key", keep="first").reset_index(drop=True)
    x["advisory_rank"] = range(1, len(x) + 1)

    preferred = [
        "advisory_rank", "advisory_version", "run_id", "global_theme", "driver_id", "driver_label",
        "taiwan_code", "ticker", "name", "etf_ticker", "stock_vs_etf_state", "preferred_exposure",
        "advisory_action", "advisory_confidence", "advisory_rationale", "advisory_missing_evidence",
        "dynamic_driver_state", "provenance_status", "reaction_state", "linkage_tier", "linkage_confidence",
        "research_priority_score", "candidate_action", "portfolio_action", "advisory_is_order", "auto_trade_allowed",
    ]
    return x[[c for c in preferred if c in x.columns]]


def build_advisory_packet(advisory: pd.DataFrame, run_id: str) -> dict:
    counts = advisory["advisory_action"].value_counts(dropna=False).to_dict() if not advisory.empty else {}
    cols = [c for c in [
        "advisory_rank", "global_theme", "driver_id", "ticker", "name", "etf_ticker",
        "preferred_exposure", "advisory_action", "advisory_confidence", "advisory_rationale",
        "advisory_missing_evidence", "reaction_state", "provenance_status", "research_priority_score",
    ] if c in advisory.columns]
    return {
        "contract": "ALPHA_HUNTER_CIO_ADVISORY_PACKET",
        "advisory_version": ADVISORY_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now().astimezone().isoformat(),
        "advisory_is_order": False,
        "auto_trade_allowed": False,
        "purpose": "Directional CIO decision support under uncertainty. Execution permissions remain governed by the frozen shadow execution lane.",
        "action_counts": {str(k): int(v) for k, v in counts.items()},
        "top_advisories": advisory[cols].head(30).to_dict(orient="records") if cols else [],
        "decision_rule": "Always separate recommendation from execution permission. Active causal evidence may support a directional bias even when execution remains blocked. Weak Taiwan stock evidence should fall back to ETF or cash, not to endless research.",
    }


def write_outputs(board_path: Path = OUT / "decision_board.csv") -> tuple[pd.DataFrame, dict]:
    if not board_path.exists():
        raise RuntimeError(f"Missing decision board: {board_path}")
    board = pd.read_csv(board_path, dtype={"taiwan_code": str})
    advisory = build_cio_advisory(board)
    run_id = str(advisory.iloc[0].get("run_id", "")) if not advisory.empty else ""
    packet = build_advisory_packet(advisory, run_id)
    advisory.to_csv(OUT / "cio_advisory.csv", index=False)
    (OUT / "cio_advisory.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return advisory, packet


def main() -> None:
    advisory, packet = write_outputs()
    print(f"CIO advisory rows: {len(advisory)}")
    print(f"CIO advisory counts: {packet.get('action_counts', {})}")
    print("Advisory outputs are directional research decisions, never brokerage orders.")


if __name__ == "__main__":
    main()
