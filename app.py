from datetime import datetime, time
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

TAIPEI = ZoneInfo("Asia/Taipei")
OUT = Path("output")

st.set_page_config(page_title="Alpha Hunter v2.7", page_icon="🌎", layout="wide")
st.title("🌎 Alpha Hunter v2.7 — Causal Research → Decision Bridge")
st.caption(
    "Global price structure nominates research. Research validates the exact causal driver. "
    "Structural exposure, Taiwan reaction, ETF-vs-stock, entry, risk and exit remain separate auditable layers."
)

mf = OUT / "manifest.json"
if not mf.exists():
    st.error("🚨 DATA CONTRACT MISSING — run GitHub Actions first.")
    st.stop()
manifest = json.loads(mf.read_text(encoding="utf-8"))

gate_path = OUT / "gate_report.json"
gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else {}
if gate.get("gate_status") == "PASS":
    st.success(f"🔒 DETERMINISTIC HARD GATE: PASS — run_id {gate.get('run_id')}")
else:
    st.error(f"🚨 DETERMINISTIC HARD GATE: {gate.get('gate_status', 'MISSING')} — {gate.get('failure_code', 'NO_GATE_REPORT')}")
    st.stop()


def parse_dt(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=TAIPEI)
        return d.astimezone(TAIPEI)
    except Exception:
        return None


def freshness_gate(m):
    now = datetime.now(TAIPEI)
    generated = parse_dt(m.get("generated_at_taipei"))
    if generated is None:
        return "STALE", "No valid generated_at_taipei", None
    age_h = (now - generated).total_seconds() / 3600
    weekend_window = now.weekday() in (5, 6) or (now.weekday() == 0 and now.time() < time(7, 45))
    max_age = 84 if weekend_window else 30
    if m.get("status") != "PASS":
        return "WARNING", f"Manifest status is {m.get('status')}", age_h
    if str(m.get("schema_version")) != "2.6":
        return "WARNING", f"Expected scanner schema 2.6, found {m.get('schema_version')}", age_h
    if age_h > max_age:
        return "STALE", f"Manifest is {age_h:.1f} hours old", age_h
    return "FRESH", "Canonical manifest passed and scanner run is recent.", age_h


status, reason, age_h = freshness_gate(manifest)
if status == "FRESH":
    st.success(f"✅ DATA STATUS: FRESH — {reason}")
elif status == "WARNING":
    st.warning(f"⚠️ DATA STATUS: WARNING — {reason}")
else:
    st.error(f"🚨 DATA STATUS: STALE — {reason}")

G = manifest.get("global", {})
T = manifest.get("taiwan", {})
C = manifest.get("causal_engine", {})
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Global scanned", G.get("scanned_count", "?"))
c2.metric("Global themes", G.get("theme_count", "?"))
c3.metric("Taiwan universe", T.get("universe_count", "?"))
c4.metric("Taiwan scanned", T.get("scanned_count", "?"))
c5.metric("Taiwan candidates", T.get("candidate_count", "?"))
c6.metric("Unresolved causal tasks", C.get("research_queue_count", "?"))

st.info(
    "Hard rule: PRICE CANNOT CREATE CAUSALITY. Gate first, score second. "
    "A strong driver cannot rescue weak company provenance, and a correct thesis does not justify chasing EXTENDED price action."
)

with st.expander("Canonical contract / known model risks"):
    st.json(manifest)

tabs = st.tabs([
    "Decision Board", "Global Leaders", "Taiwan Candidates", "Causal Research Queue",
    "Structural Matches", "Breadth", "Graph Audit"
])

with tabs[0]:
    st.subheader("v2.7 Research → Decision Bridge")
    dp = OUT / "decision_packet.json"
    db = OUT / "decision_board.csv"
    if dp.exists():
        packet = json.loads(dp.read_text(encoding="utf-8"))
        if str(packet.get("run_id")) != str(manifest.get("run_id")):
            st.error("🚨 MIXED_SNAPSHOT_DATA — decision packet run_id does not match manifest.")
        else:
            st.caption(
                "This board is deliberately conservative. Until ETF-vs-stock, entry trigger, portfolio risk and shadow-audit modules are validated, "
                "automatic BUY/SELL is disabled. WATCH_ENTRY means the causal/provenance/reaction gates passed far enough to justify final-entry research."
            )
            st.warning("影子驗證模式：BUY／SELL 為研究訊號，尚未取得實盤資格。")
            release = packet.get("launch_layer") or {}
            st.caption(f"規則版本：{release.get('strategy_version', '未驗證')}｜首次審查：2026-11-29；不自動升級")
            a, b, c = st.columns(3)
            a.metric("Decision contract", packet.get("decision_contract_version", "?"))
            b.metric("Auto trade", "DISABLED" if not packet.get("auto_trade_allowed", False) else "ENABLED")
            bcounts = packet.get("action_counts", {})
            c.metric("WATCH_ENTRY", bcounts.get("WATCH_ENTRY", 0))
            with st.expander("Decision packet / remaining modules"):
                st.json(packet)
    else:
        st.warning("Decision packet missing — run the current GitHub Actions workflow.")

    if db.exists():
        d = pd.read_csv(db, dtype={"taiwan_code": str})
        pref = [c for c in [
            "execution_action", "deployment_mode", "candidate_action", "decision_stage", "global_theme", "driver_id", "taiwan_code", "ticker", "name",
            "reaction_state", "dynamic_driver_state", "provenance_status", "linkage_tier", "linkage_confidence",
            "rs_20d_vs_bench", "rs_60d_vs_bench", "acceleration", "decision_blockers", "research_priority_score"
        ] if c in d.columns]
        st.dataframe(d[pref] if pref else d, use_container_width=True, height=680)

with tabs[1]:
    p = OUT / "market_snapshot.csv"
    if p.exists():
        d = pd.read_csv(p)
        cols = [c for c in [
            "ticker", "name", "theme", "last_price_date", "price", "ret_5d", "rs_20d_vs_bench",
            "rs_60d_vs_bench", "acceleration", "keynes_legacy", "keynes_v2", "leader_score_v1", "raw_leader_state"
        ] if c in d.columns]
        st.dataframe(d[cols].head(120), use_container_width=True, height=620)

with tabs[2]:
    p = OUT / "taiwan_candidates.csv"
    if p.exists():
        d = pd.read_csv(p, dtype={"code": str})
        st.caption("Balanced discovery funnel: confirmed + early/pre-confirmation + capped extended names. NOT a buy list.")
        cols = [c for c in [
            "candidate_rank", "candidate_bucket", "reaction_state", "code", "ticker", "name", "exchange", "industry",
            "last_price_date", "price", "ret_5d", "ret_20d", "rs_20d_vs_bench", "rs_60d_vs_bench", "acceleration",
            "keynes_legacy", "keynes_v2", "bias20", "avg_turnover20_twd", "taiwan_candidate_score_v1", "taiwan_early_score_v2"
        ] if c in d.columns]
        st.dataframe(d[cols], use_container_width=True, height=680)

with tabs[3]:
    p = OUT / "causal_research_queue.csv"
    st.warning(
        "Every unresolved driver below still requires external causal research. Price action nominated the broad theme; it did NOT prove which sub-driver is active."
    )
    if p.exists():
        d = pd.read_csv(p)
        st.dataframe(d, use_container_width=True, height=680)

with tabs[4]:
    p = OUT / "structural_matches.csv"
    st.warning(
        "Structural Match ≠ active causal transmission. These rows answer 'who could economically benefit if this driver is active?' "
        "They are built from the full Taiwan scan, not only the top-150 funnel."
    )
    if p.exists():
        d = pd.read_csv(p, dtype={"taiwan_code": str})
        pref = [c for c in [
            "research_priority_score", "global_theme", "driver_id", "driver_label", "taiwan_code", "name", "industry",
            "economic_role", "linkage_tier", "linkage_confidence", "polarity", "causal_time_state", "reaction_state",
            "in_top_candidate_funnel", "rs_20d_vs_bench", "acceleration", "keynes_v2", "dynamic_driver_state", "causal_status"
        ] if c in d.columns]
        st.dataframe(d[pref] if pref else d, use_container_width=True, height=680)

with tabs[5]:
    a, b = st.columns(2)
    with a:
        st.subheader("Global theme breadth")
        p = OUT / "theme_breadth.csv"
        if p.exists():
            st.dataframe(pd.read_csv(p), use_container_width=True, height=600)
    with b:
        st.subheader("Taiwan industry breadth")
        p = OUT / "taiwan_industry_breadth.csv"
        if p.exists():
            st.dataframe(pd.read_csv(p), use_container_width=True, height=600)

with tabs[6]:
    st.subheader("Structural exposure graph audit")
    st.caption(
        "Edges are slow-moving economic hypotheses and have provenance/review fields. A SEED edge is not equivalent to source-backed verification."
    )
    p = OUT / "causal_graph_audit.csv"
    if p.exists():
        d = pd.read_csv(p, dtype={"taiwan_code": str})
        st.dataframe(d, use_container_width=True, height=520)
        if "review_overdue" in d.columns:
            c1, c2, c3 = st.columns(3)
            c1.metric("Edges", len(d))
            c2.metric("Review overdue", int(d["review_overdue"].fillna(False).sum()))
            c3.metric("Missing source-backed provenance", int(d["missing_provenance"].fillna(False).sum()))
    with st.expander("Causal driver taxonomy"):
        p = OUT / "causal_driver_taxonomy.csv"
        if p.exists():
            st.dataframe(pd.read_csv(p), use_container_width=True, height=480)
    with st.expander("Structural exposure graph"):
        p = OUT / "structural_exposure_graph.csv"
        if p.exists():
            st.dataframe(pd.read_csv(p, dtype={"taiwan_code": str}), use_container_width=True, height=520)

st.caption(
    "Layer discipline: Python scanner = what moved; Research = which exact driver is active and why; structural graph = who has economic exposure; "
    "Taiwan Sensor = price reaction; Decision Layer = ETF/stock/cash + entry/risk/exit; Shadow Audit = point-in-time accountability."
)
