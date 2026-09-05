from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


TIER_WEIGHT = {
    "DIRECT": 1.00,
    "STRONG": 0.85,
    "SECOND_ORDER": 0.60,
    "SPECULATIVE": 0.30,
}

PRICE_STATE_WEIGHT = {
    "PERSISTENT": 1.00,
    "CONFIRMING": 0.90,
    "EARLY_CONFIRMATION": 0.72,
    "PRE_CONFIRMATION": 0.58,
    "PULLBACK": 0.52,
    "EXTENDED": 0.42,
    "BROKEN": 0.10,
    "UNKNOWN": 0.35,
}


@dataclass
class CausalConfig:
    theme_strength_gate: float = 0.55
    edge_confidence_gate: float = 0.55
    max_queue_rows: int = 80
    max_structural_matches: int = 500
    activation_max_age_hours: int = 48


def theme_strength(global_stocks: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for theme, g in global_stocks.groupby("theme", dropna=False):
        if g.empty:
            continue
        rows.append({
            "global_theme": theme,
            "global_n": len(g),
            "global_median_rs20": float(g["rs_20d_vs_bench"].median()),
            "global_positive_rs20_pct": float((g["rs_20d_vs_bench"] > 0).mean()),
            "global_max_leader_score": float(g["leader_score_v1"].max()),
            "global_median_acceleration": float(g["acceleration"].median()),
            "global_latest_price_date": str(g["last_price_date"].max()),
        })
    x = pd.DataFrame(rows)
    if x.empty:
        return x
    rank_cols = [
        "global_median_rs20",
        "global_positive_rs20_pct",
        "global_max_leader_score",
        "global_median_acceleration",
    ]
    for col in rank_cols:
        x[f"r_{col}"] = x[col].rank(pct=True, method="average")
    # Research triage only. Not a trading score.
    x["global_theme_strength_v2"] = (
        0.35 * x["r_global_median_rs20"]
        + 0.25 * x["r_global_positive_rs20_pct"]
        + 0.25 * x["r_global_max_leader_score"]
        + 0.15 * x["r_global_median_acceleration"]
    )
    return x.sort_values("global_theme_strength_v2", ascending=False)


def _top_global_leaders(global_stocks: pd.DataFrame, theme: str, n: int = 5) -> str:
    g = global_stocks[global_stocks["theme"].astype(str) == str(theme)].copy()
    if g.empty:
        return ""
    g = g.sort_values("leader_score_v1", ascending=False).head(n)
    return "; ".join(
        f"{r.ticker}:{r.raw_leader_state}:RS20={getattr(r,'rs_20d_vs_bench',np.nan):.3f}"
        for r in g.itertuples()
    )


def build_causal_research_queue(
    global_stocks: pd.DataFrame,
    taxonomy: pd.DataFrame,
    cfg: CausalConfig = CausalConfig(),
) -> pd.DataFrame:
    """Produce a research queue, not an activated causal narrative.

    Price action can nominate which broad themes deserve research, but cannot decide which
    fine-grained causal driver is active. Every driver starts UNRESOLVED until a Research Layer
    supplies external causal/fundamental evidence.
    """
    ts = theme_strength(global_stocks)
    if ts.empty or taxonomy.empty:
        return pd.DataFrame()
    t = taxonomy.copy()
    t = t[t.get("enabled", 1).fillna(1).astype(int) == 1] if "enabled" in t.columns else t
    q = t.merge(ts, on="global_theme", how="left")
    q = q[q["global_theme_strength_v2"].fillna(0) >= cfg.theme_strength_gate].copy()
    if q.empty:
        return q
    q["activation_state"] = "UNRESOLVED_RESEARCH_REQUIRED"
    q["activation_confidence"] = np.nan
    q["price_cannot_activate_driver"] = True
    q["global_leaders_evidence"] = q["global_theme"].map(
        lambda theme: _top_global_leaders(global_stocks, theme)
    )
    q["research_priority"] = q["global_theme_strength_v2"] * q.get("driver_prior_weight", 1.0).fillna(1.0)
    cols = [
        "research_priority", "global_theme", "driver_id", "driver_label", "driver_scope",
        "global_theme_strength_v2", "global_latest_price_date", "global_leaders_evidence",
        "activation_state", "activation_confidence", "activation_evidence_required",
        "counter_evidence_required", "price_cannot_activate_driver",
    ]
    cols = [c for c in cols if c in q.columns]
    return q.sort_values("research_priority", ascending=False)[cols].head(cfg.max_queue_rows)


def _normalize_code(s) -> str:
    return str(s).strip().split(".")[0].zfill(4)


def _industry_breadth_support(breadth: pd.DataFrame, industry: str) -> float:
    if breadth is None or breadth.empty:
        return np.nan
    col = "theme" if "theme" in breadth.columns else "industry"
    hit = breadth[breadth[col].astype(str) == str(industry)]
    if hit.empty:
        return np.nan
    r = hit.iloc[0]
    vals = []
    for c in ["above_ma20_pct", "positive_rs20_pct", "near_20d_high_pct"]:
        if c in r.index and pd.notna(r[c]):
            vals.append(float(r[c]))
    return float(np.mean(vals)) if vals else np.nan


def _causal_time_state(global_date: str, taiwan_date: str) -> tuple[str, Optional[int]]:
    try:
        gd = pd.Timestamp(global_date).date()
        td = pd.Timestamp(taiwan_date).date()
        d = (gd - td).days
        if d > 0:
            return "GLOBAL_INFORMATION_NEWER", d
        if d < 0:
            return "TAIWAN_INFORMATION_NEWER", d
        return "SAME_MARKET_DATE", 0
    except Exception:
        return "UNKNOWN", None


def build_structural_matches(
    global_stocks: pd.DataFrame,
    taiwan_stocks: pd.DataFrame,
    taiwan_candidates: pd.DataFrame,
    taiwan_breadth: pd.DataFrame,
    exposure_graph: pd.DataFrame,
    taxonomy: pd.DataFrame,
    cfg: CausalConfig = CausalConfig(),
) -> pd.DataFrame:
    """Join structural company-level economic exposures with live market state.

    Crucially, this does NOT require a stock to be in the top-150 candidate funnel. That avoids
    a confirmation/chasing bias and preserves possible pre-confirmation lead-lag opportunities.
    """
    if exposure_graph.empty or taiwan_stocks.empty:
        return pd.DataFrame()
    ts = theme_strength(global_stocks)
    if ts.empty:
        return pd.DataFrame()

    eg = exposure_graph.copy()
    if "enabled" in eg.columns:
        eg = eg[eg["enabled"].fillna(0).astype(int) == 1]
    eg["taiwan_code"] = eg["taiwan_code"].map(_normalize_code)
    eg["linkage_tier"] = eg["linkage_tier"].astype(str).str.upper()
    eg["tier_weight"] = eg["linkage_tier"].map(TIER_WEIGHT).fillna(0)
    eg["linkage_confidence"] = pd.to_numeric(eg["linkage_confidence"], errors="coerce").fillna(0)
    eg["structural_linkage_score"] = eg["tier_weight"] * eg["linkage_confidence"]

    st = taiwan_stocks.copy()
    st["code"] = st["code"].map(_normalize_code)
    cand_codes = set(taiwan_candidates["code"].map(_normalize_code)) if not taiwan_candidates.empty else set()
    st["in_top_candidate_funnel"] = st["code"].isin(cand_codes)

    m = eg.merge(st, left_on="taiwan_code", right_on="code", how="left", suffixes=("_edge", ""))
    # Only publish matches for securities actually present in today's full Taiwan scan.
    # Missing/unavailable securities remain visible through graph audit, not the live match table.
    m = m[m["ticker"].notna()].copy()
    m = m.merge(ts[["global_theme", "global_theme_strength_v2", "global_latest_price_date"]], on="global_theme", how="left")
    m = m[m["global_theme_strength_v2"].fillna(0) >= cfg.theme_strength_gate].copy()
    m = m[m["linkage_confidence"] >= cfg.edge_confidence_gate].copy()
    m = m[m["linkage_tier"] != "SPECULATIVE"].copy()
    if m.empty:
        return m

    m["taiwan_industry_breadth_support"] = m["industry"].map(lambda x: _industry_breadth_support(taiwan_breadth, x))
    if "reaction_state" not in m.columns:
        m["reaction_state"] = "UNKNOWN"
    m["price_state_weight"] = m["reaction_state"].map(PRICE_STATE_WEIGHT).fillna(0.35)
    m["causal_time_state"], m["global_minus_taiwan_calendar_days"] = zip(*[
        _causal_time_state(gd, td) for gd, td in zip(m["global_latest_price_date"], m["last_price_date"])
    ])

    # Rank for research workload only, not expected return. Keep ingredients visible.
    breadth_fill = m["taiwan_industry_breadth_support"].fillna(0.5)
    extension_penalty = np.where(m["reaction_state"].eq("EXTENDED"), 0.78, 1.0)
    m["research_priority_score"] = (
        0.40 * m["structural_linkage_score"]
        + 0.25 * m["global_theme_strength_v2"]
        + 0.20 * m["price_state_weight"]
        + 0.15 * breadth_fill
    ) * extension_penalty

    m["dynamic_driver_state"] = "UNRESOLVED"
    m["causal_status"] = "STRUCTURAL_MATCH_RESEARCH_REQUIRED"
    m["decision_eligible"] = False
    m["why_not_decision_eligible"] = "Dynamic causal driver has not been externally validated."

    cols = [
        "research_priority_score", "global_theme", "driver_id", "driver_label", "global_theme_strength_v2",
        "global_latest_price_date", "taiwan_code", "ticker", "name", "industry", "economic_role",
        "linkage_tier", "linkage_confidence", "structural_linkage_score", "polarity",
        "link_mechanism", "evidence_required", "edge_status", "provenance_status", "review_after",
        "last_price_date", "causal_time_state", "global_minus_taiwan_calendar_days",
        "reaction_state", "in_top_candidate_funnel", "rs_20d_vs_bench", "rs_60d_vs_bench",
        "acceleration", "keynes_v2", "bias20", "taiwan_industry_breadth_support",
        "dynamic_driver_state", "causal_status", "decision_eligible", "why_not_decision_eligible",
    ]
    cols = [c for c in cols if c in m.columns]
    return m.sort_values("research_priority_score", ascending=False)[cols].head(cfg.max_structural_matches)


def validate_driver_activation_file(path: Path, queue: pd.DataFrame, cfg: CausalConfig = CausalConfig()) -> pd.DataFrame:
    """Optional bridge for a future Research Agent write-back.

    An activation file can never create a structural edge. It can only activate driver_ids already
    present in the canonical taxonomy. Stale / poorly sourced activations are rejected.
    """
    if not path.exists() or queue.empty:
        return pd.DataFrame()
    try:
        a = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    req = {"driver_id", "activation_state", "activation_confidence", "as_of_utc", "source_count"}
    if not req.issubset(a.columns):
        return pd.DataFrame()
    valid_ids = set(queue["driver_id"].astype(str))
    a = a[a["driver_id"].astype(str).isin(valid_ids)].copy()
    a["activation_state"] = a["activation_state"].astype(str).str.upper()
    a = a[a["activation_state"].isin(["ACTIVE", "INACTIVE", "UNKNOWN"])]
    a["activation_confidence"] = pd.to_numeric(a["activation_confidence"], errors="coerce")
    a["source_count"] = pd.to_numeric(a["source_count"], errors="coerce")
    now = pd.Timestamp.now(tz="UTC")
    parsed = pd.to_datetime(a["as_of_utc"], utc=True, errors="coerce")
    a["activation_age_hours"] = (now - parsed).dt.total_seconds() / 3600
    a["activation_valid"] = (
        a["activation_age_hours"].between(0, cfg.activation_max_age_hours, inclusive="both")
        & (a["source_count"].fillna(0) >= 1)
        & a["activation_confidence"].between(0, 1, inclusive="both")
    )
    return a


def apply_driver_activation(structural_matches: pd.DataFrame, activations: pd.DataFrame) -> pd.DataFrame:
    if structural_matches.empty:
        return structural_matches
    x = structural_matches.copy()
    if activations.empty:
        return x
    cols = [
        "driver_id", "activation_state", "activation_confidence", "activation_valid",
        "as_of_utc", "source_count", "primary_cause", "counter_evidence", "source_summary"
    ]
    cols = [c for c in cols if c in activations.columns]
    x = x.merge(activations[cols], on="driver_id", how="left")
    active = (
        x.get("activation_valid", False).fillna(False)
        & x.get("activation_state", "UNKNOWN").fillna("UNKNOWN").eq("ACTIVE")
    )
    x.loc[active, "dynamic_driver_state"] = "ACTIVE_RESEARCH_VALIDATED"
    x.loc[active, "causal_status"] = "ACTIVATED_HYPOTHESIS_REQUIRES_FINAL_AUDIT"
    # Still not automatically decision-eligible: scanner/research layers do not make trades.
    x.loc[active, "why_not_decision_eligible"] = "Requires downstream final audit; activation is research evidence, not a trade signal."
    return x


def graph_audit(exposure_graph: pd.DataFrame) -> pd.DataFrame:
    if exposure_graph.empty:
        return pd.DataFrame()
    g = exposure_graph.copy()
    today = pd.Timestamp.now().date()
    g["review_after_parsed"] = pd.to_datetime(g.get("review_after"), errors="coerce").dt.date
    g["review_overdue"] = g["review_after_parsed"].map(lambda x: bool(pd.notna(x) and x < today))
    g["missing_provenance"] = g.get("provenance_status", "").astype(str).ne("SOURCE_BACKED")
    g["duplicate_edge"] = g.duplicated(["driver_id", "taiwan_code", "economic_role"], keep=False)
    return g
