from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from causal_engine import TIER_WEIGHT, theme_strength


REVERSE_OUTPUT_COLUMNS = [
    "run_id",
    "reverse_research_priority",
    "driver_id",
    "driver_label",
    "driver_scope",
    "global_theme",
    "global_theme_strength_v2",
    "global_latest_price_date",
    "global_peer_evidence",
    "taiwan_code",
    "ticker",
    "name",
    "industry",
    "economic_role",
    "linkage_tier",
    "linkage_confidence",
    "structural_linkage_score",
    "reaction_state",
    "taiwan_anomaly_score",
    "taiwan_candidate_percentile",
    "taiwan_early_percentile",
    "taiwan_rs20_percentile",
    "taiwan_acceleration_percentile",
    "taiwan_price_reaction_percentile",
    "global_peer_vs_taiwan_gap",
    "transmission_gap_proxy",
    "pricing_state",
    "local_catalyst_status",
    "local_catalyst_check_required",
    "activation_state",
    "price_cannot_activate_driver",
    "decision_eligible",
    "why_not_decision_eligible",
]


@dataclass
class ReverseDiscoveryConfig:
    """Research-only Taiwan-first discovery configuration.

    These thresholds nominate work for causal research. They are not entry thresholds,
    expected-return estimates, or frozen V2 decision parameters.
    """

    anomaly_percentile_gate: float = 0.85
    linkage_confidence_gate: float = 0.55
    max_candidates: int = 160
    max_driver_nominees: int = 5
    max_queue_rows: int = 80


def _normalize_code(value: object) -> str:
    return str(value).strip().split(".")[0].zfill(4)


def _rank01(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    if x.notna().sum() == 0:
        return pd.Series(0.0, index=series.index, dtype=float)
    return x.rank(pct=True, method="average").fillna(0.0).astype(float)


def _top_global_peers(global_stocks: pd.DataFrame, theme: str, n: int = 5) -> str:
    if global_stocks is None or global_stocks.empty or "theme" not in global_stocks.columns:
        return ""
    g = global_stocks[global_stocks["theme"].astype(str) == str(theme)].copy()
    if g.empty:
        return ""
    if "leader_score_v1" in g.columns:
        g = g.sort_values("leader_score_v1", ascending=False)
    g = g.head(n)
    rows: list[str] = []
    for r in g.itertuples():
        ticker = str(getattr(r, "ticker", ""))
        state = str(getattr(r, "raw_leader_state", getattr(r, "state", "")))
        rs20 = getattr(r, "rs_20d_vs_bench", np.nan)
        try:
            rs = f"{float(rs20):.3f}"
        except (TypeError, ValueError):
            rs = "nan"
        rows.append(f"{ticker}:{state}:RS20={rs}")
    return "; ".join(rows)


def _empty_reverse_candidates() -> pd.DataFrame:
    return pd.DataFrame(columns=[c for c in REVERSE_OUTPUT_COLUMNS if c != "run_id"])


def build_reverse_candidates(
    taiwan_stocks: pd.DataFrame,
    global_stocks: pd.DataFrame,
    exposure_graph: pd.DataFrame,
    taxonomy: pd.DataFrame,
    cfg: ReverseDiscoveryConfig = ReverseDiscoveryConfig(),
) -> pd.DataFrame:
    """Nominate Taiwan-first causal research candidates.

    Taiwan price action is allowed to ask *why* a stock is moving, but it cannot activate
    any causal driver. Candidate drivers come only from the pre-existing structural graph;
    the scanner never invents a company-driver relationship from co-movement.
    """
    if taiwan_stocks is None or taiwan_stocks.empty or exposure_graph is None or exposure_graph.empty:
        return _empty_reverse_candidates()

    st = taiwan_stocks.copy()
    if "code" not in st.columns:
        return _empty_reverse_candidates()
    st["code"] = st["code"].map(_normalize_code)

    for col in ("taiwan_candidate_score_v1", "taiwan_early_score_v2", "rs_20d_vs_bench", "acceleration", "bias20"):
        if col not in st.columns:
            st[col] = np.nan

    st["taiwan_candidate_percentile"] = _rank01(st["taiwan_candidate_score_v1"])
    st["taiwan_early_percentile"] = _rank01(st["taiwan_early_score_v2"])
    st["taiwan_rs20_percentile"] = _rank01(st["rs_20d_vs_bench"])
    st["taiwan_acceleration_percentile"] = _rank01(st["acceleration"])
    st["taiwan_positive_bias_percentile"] = _rank01(pd.to_numeric(st["bias20"], errors="coerce").clip(lower=0))
    st["taiwan_anomaly_score"] = st[["taiwan_candidate_percentile", "taiwan_early_percentile"]].max(axis=1)
    st["taiwan_price_reaction_percentile"] = st[["taiwan_rs20_percentile", "taiwan_positive_bias_percentile"]].max(axis=1)

    eg = exposure_graph.copy()
    if "enabled" in eg.columns:
        eg = eg[eg["enabled"].fillna(0).astype(int) == 1]
    eg["taiwan_code"] = eg["taiwan_code"].map(_normalize_code)
    eg["linkage_tier"] = eg["linkage_tier"].astype(str).str.upper()
    eg["linkage_confidence"] = pd.to_numeric(eg["linkage_confidence"], errors="coerce").fillna(0.0)
    eg = eg[(eg["linkage_tier"] != "SPECULATIVE") & (eg["linkage_confidence"] >= cfg.linkage_confidence_gate)].copy()
    if eg.empty:
        return _empty_reverse_candidates()
    eg["tier_weight"] = eg["linkage_tier"].map(TIER_WEIGHT).fillna(0.0)
    eg["structural_linkage_score"] = eg["tier_weight"] * eg["linkage_confidence"]

    m = eg.merge(st, left_on="taiwan_code", right_on="code", how="inner", suffixes=("_edge", ""))
    if m.empty:
        return _empty_reverse_candidates()

    if taxonomy is not None and not taxonomy.empty and "driver_id" in taxonomy.columns:
        tax_cols = [
            c for c in [
                "driver_id", "driver_label", "driver_scope", "activation_evidence_required",
                "counter_evidence_required",
            ] if c in taxonomy.columns
        ]
        tax = taxonomy[tax_cols].drop_duplicates("driver_id")
        m = m.merge(tax, on="driver_id", how="left", suffixes=("", "_taxonomy"))
        for col in ("driver_label", "driver_scope"):
            tax_col = f"{col}_taxonomy"
            if tax_col in m.columns:
                if col not in m.columns:
                    m[col] = m[tax_col]
                else:
                    m[col] = m[col].where(m[col].notna(), m[tax_col])

    ts = theme_strength(global_stocks) if global_stocks is not None and not global_stocks.empty else pd.DataFrame()
    if not ts.empty:
        m = m.merge(
            ts[["global_theme", "global_theme_strength_v2", "global_latest_price_date"]],
            on="global_theme",
            how="left",
        )
    else:
        m["global_theme_strength_v2"] = np.nan
        m["global_latest_price_date"] = ""

    m["global_theme_strength_v2"] = pd.to_numeric(m["global_theme_strength_v2"], errors="coerce").fillna(0.0)
    peer_map = {
        str(theme): _top_global_peers(global_stocks, str(theme))
        for theme in m["global_theme"].dropna().astype(str).unique()
    }
    m["global_peer_evidence"] = m["global_theme"].astype(str).map(peer_map).fillna("")

    reaction = m.get("reaction_state", pd.Series("UNKNOWN", index=m.index)).fillna("UNKNOWN").astype(str)
    m = m[(m["taiwan_anomaly_score"] >= cfg.anomaly_percentile_gate) & reaction.ne("BROKEN")].copy()
    if m.empty:
        return _empty_reverse_candidates()

    m["global_peer_vs_taiwan_gap"] = m["global_theme_strength_v2"] - m["taiwan_price_reaction_percentile"]
    m["transmission_gap_proxy"] = m["global_peer_vs_taiwan_gap"] * m["structural_linkage_score"]
    extension_penalty = np.where(m.get("reaction_state", "UNKNOWN").astype(str).eq("EXTENDED"), 0.72, 1.0)
    m["reverse_research_priority"] = (
        0.45 * m["taiwan_anomaly_score"]
        + 0.30 * m["structural_linkage_score"]
        + 0.25 * m["global_theme_strength_v2"]
    ) * extension_penalty

    m["pricing_state"] = "MIXED_GAP"
    m.loc[m["transmission_gap_proxy"] >= 0.15, "pricing_state"] = "POTENTIAL_UNDERREACTION"
    m.loc[m["transmission_gap_proxy"] <= -0.15, "pricing_state"] = "POSSIBLY_PRICED_IN"
    m.loc[m.get("reaction_state", "UNKNOWN").astype(str).eq("EXTENDED"), "pricing_state"] = "EXTENDED_REVIEW"

    m["local_catalyst_status"] = "UNRESOLVED_RESEARCH_REQUIRED"
    m["local_catalyst_check_required"] = True
    m["activation_state"] = "UNRESOLVED_RESEARCH_REQUIRED"
    m["price_cannot_activate_driver"] = True
    m["decision_eligible"] = False
    m["why_not_decision_eligible"] = (
        "Taiwan price anomaly only nominated research. Exact driver and local-catalyst alternatives require external validation."
    )

    cols = [c for c in REVERSE_OUTPUT_COLUMNS if c != "run_id" and c in m.columns]
    return m.sort_values("reverse_research_priority", ascending=False)[cols].head(cfg.max_candidates)


def build_reverse_driver_queue(
    reverse_candidates: pd.DataFrame,
    taxonomy: pd.DataFrame,
    cfg: ReverseDiscoveryConfig = ReverseDiscoveryConfig(),
) -> pd.DataFrame:
    """Aggregate Taiwan anomalies into canonical driver research tasks."""
    if reverse_candidates is None or reverse_candidates.empty:
        return pd.DataFrame()

    tax = taxonomy.drop_duplicates("driver_id").set_index("driver_id") if taxonomy is not None and not taxonomy.empty else pd.DataFrame()
    rows: list[dict] = []
    for driver_id, g in reverse_candidates.groupby("driver_id", dropna=False):
        driver_id = str(driver_id)
        g = g.sort_values("reverse_research_priority", ascending=False)
        first = g.iloc[0]
        meta = tax.loc[driver_id] if isinstance(tax, pd.DataFrame) and driver_id in tax.index else pd.Series(dtype=object)
        top = g.head(cfg.max_driver_nominees)
        nominees = "; ".join(
            f"{str(r.get('ticker',''))}|{str(r.get('name',''))}|reaction={str(r.get('reaction_state',''))}|"
            f"anomaly={float(r.get('taiwan_anomaly_score',0)):.3f}|gap={float(r.get('transmission_gap_proxy',0)):.3f}"
            for _, r in top.iterrows()
        )
        base_counter = str(meta.get("counter_evidence_required", first.get("counter_evidence_required", "")) or "")
        local_requirement = (
            " For Taiwan reverse nominees, also test company-specific local catalysts such as revenue/earnings, guidance, "
            "contract/tender wins, corporate actions, index/ETF flows or squeezes. A local catalyst is an alternative explanation "
            "for the Taiwan move and must not be used to activate the global driver. Nominees: " + nominees
        )
        rows.append({
            "research_priority": float(g["reverse_research_priority"].max()),
            "global_theme": str(first.get("global_theme", meta.get("global_theme", ""))),
            "driver_id": driver_id,
            "driver_label": str(meta.get("driver_label", first.get("driver_label", driver_id))),
            "driver_scope": str(meta.get("driver_scope", first.get("driver_scope", ""))),
            "global_theme_strength_v2": float(pd.to_numeric(g["global_theme_strength_v2"], errors="coerce").fillna(0).max()),
            "global_latest_price_date": str(first.get("global_latest_price_date", "")),
            "global_leaders_evidence": str(first.get("global_peer_evidence", "")),
            "activation_state": "UNRESOLVED_RESEARCH_REQUIRED",
            "activation_confidence": np.nan,
            "activation_evidence_required": str(meta.get("activation_evidence_required", first.get("activation_evidence_required", ""))),
            "counter_evidence_required": base_counter + local_requirement,
            "price_cannot_activate_driver": True,
            "nomination_origin": "TAIWAN_REVERSE",
            "reverse_nominee_count": int(g["ticker"].nunique()),
            "reverse_nominees": nominees,
            "local_catalyst_check_required": True,
            "transmission_gap_proxy_max": float(pd.to_numeric(g["transmission_gap_proxy"], errors="coerce").max()),
            "taiwan_reverse_anomaly_max": float(pd.to_numeric(g["taiwan_anomaly_score"], errors="coerce").max()),
        })
    return pd.DataFrame(rows).sort_values("research_priority", ascending=False).head(cfg.max_queue_rows)


def merge_research_queues(
    global_queue: pd.DataFrame,
    reverse_queue: pd.DataFrame,
    max_rows: int = 80,
) -> pd.DataFrame:
    """Merge global-first and Taiwan-first nominations without letting either activate causality."""
    frames: list[pd.DataFrame] = []
    if global_queue is not None and not global_queue.empty:
        g = global_queue.copy()
        g["nomination_origin"] = "GLOBAL_THEME"
        g["reverse_nominee_count"] = 0
        g["reverse_nominees"] = ""
        g["local_catalyst_check_required"] = False
        g["transmission_gap_proxy_max"] = np.nan
        g["taiwan_reverse_anomaly_max"] = np.nan
        frames.append(g)
    if reverse_queue is not None and not reverse_queue.empty:
        frames.append(reverse_queue.copy())
    if not frames:
        return pd.DataFrame()

    x = pd.concat(frames, ignore_index=True, sort=False)
    rows: list[dict] = []
    for driver_id, group in x.groupby("driver_id", dropna=False):
        group = group.sort_values("research_priority", ascending=False)
        base = group.iloc[0].to_dict()
        origins = sorted(set(group["nomination_origin"].dropna().astype(str)))
        reverse_rows = group[group["nomination_origin"].astype(str).eq("TAIWAN_REVERSE")]
        base["nomination_origin"] = "+".join(origins)
        base["research_priority"] = float(pd.to_numeric(group["research_priority"], errors="coerce").max())
        base["global_theme_strength_v2"] = float(pd.to_numeric(group.get("global_theme_strength_v2"), errors="coerce").fillna(0).max())
        base["activation_state"] = "UNRESOLVED_RESEARCH_REQUIRED"
        base["activation_confidence"] = np.nan
        base["price_cannot_activate_driver"] = True
        if not reverse_rows.empty:
            rr = reverse_rows.iloc[0]
            base["reverse_nominee_count"] = int(pd.to_numeric(reverse_rows["reverse_nominee_count"], errors="coerce").fillna(0).max())
            base["reverse_nominees"] = str(rr.get("reverse_nominees", ""))
            base["local_catalyst_check_required"] = True
            base["transmission_gap_proxy_max"] = float(pd.to_numeric(reverse_rows["transmission_gap_proxy_max"], errors="coerce").max())
            base["taiwan_reverse_anomaly_max"] = float(pd.to_numeric(reverse_rows["taiwan_reverse_anomaly_max"], errors="coerce").max())
            # Preserve the explicit local-catalyst counter-evidence requirement even when
            # the global-first row had the higher research priority.
            reverse_counter = str(rr.get("counter_evidence_required", ""))
            if reverse_counter:
                base["counter_evidence_required"] = reverse_counter
        rows.append(base)

    out = pd.DataFrame(rows)
    return out.sort_values("research_priority", ascending=False).head(max_rows).reset_index(drop=True)


def reverse_nominated_driver_ids(reverse_queue: pd.DataFrame) -> set[str]:
    if reverse_queue is None or reverse_queue.empty or "driver_id" not in reverse_queue.columns:
        return set()
    return set(reverse_queue["driver_id"].dropna().astype(str))
