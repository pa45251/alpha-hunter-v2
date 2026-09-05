from datetime import datetime, time
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

TAIPEI = ZoneInfo("Asia/Taipei")
OUT = Path("output")

st.set_page_config(page_title="Alpha Hunter v2.4", page_icon="🌎", layout="wide")
st.title("🌎 Alpha Hunter v2.4 — Global + Taiwan Economic Linkage Sensor")
st.caption(
    "Official data comes from scheduled GitHub Actions. Global Sensor finds world leadership; "
    "Taiwan Sensor scans the full TWSE/TPEX common-stock universe; the v2.4 Transmission Engine only uses explicit "
    "company-level economic linkage edges."
)

manifest_file = OUT / "manifest.json"
if not manifest_file.exists():
    st.error("🚨 DATA CONTRACT MISSING — output/manifest.json does not exist. Run GitHub Actions first.")
    st.stop()

try:
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
except Exception as exc:
    st.error(f"🚨 Could not read manifest.json: {exc}")
    st.stop()


def parse_dt(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=TAIPEI)
        return d.astimezone(TAIPEI)
    except Exception:
        return None


def freshness_gate(m: dict):
    now = datetime.now(TAIPEI)
    generated = parse_dt(m.get("generated_at_taipei"))
    if generated is None:
        return "STALE", "No valid generated_at_taipei in manifest.", None
    age_h = (now - generated).total_seconds() / 3600
    weekend_window = now.weekday() in (5, 6) or (now.weekday() == 0 and now.time() < time(7, 45))
    max_age = 84 if weekend_window else 30
    if m.get("status") != "PASS":
        return "WARNING", f"Manifest status is {m.get('status')}; required data contract is not fully PASS.", age_h
    if str(m.get("schema_version")) != "2.4":
        return "WARNING", f"Expected schema 2.4 but found {m.get('schema_version')}.", age_h
    if age_h > max_age:
        return "STALE", f"Manifest is {age_h:.1f} hours old.", age_h
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
X = manifest.get("transmission", {})

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Global scanned", G.get("scanned_count", "?"))
c2.metric("Global themes", G.get("theme_count", "?"))
c3.metric("Taiwan universe", T.get("universe_count", "?"))
c4.metric("Taiwan scanned", T.get("scanned_count", "?"))
c5.metric("Taiwan candidates", T.get("candidate_count", "?"))
c6.metric("Linkage hypotheses", X.get("candidate_count", "?"))

st.info(
    "Automation: GitHub Actions is the official trigger. You do not need to open this app. "
    "v2.4 disables broad-industry causal matching: a transmission hypothesis can only be promoted when an explicit "
    "company-level Economic Linkage Graph edge exists and passes its linkage hard gate."
)

with st.expander("Canonical data contract / freshness details"):
    st.json(manifest)


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Global Leaders", "Taiwan Candidates", "Economic Linkage Hypotheses", "Breadth", "Linkage Audit"
])

with tab1:
    p = OUT / "market_snapshot.csv"
    if p.exists():
        df = pd.read_csv(p)
        cols = [c for c in [
            "ticker","name","theme","last_price_date","price","ret_5d","rs_20d_vs_bench",
            "rs_60d_vs_bench","acceleration","keynes_legacy","keynes_v2","leader_score_v1","raw_leader_state"
        ] if c in df.columns]
        st.dataframe(df[cols].head(120), use_container_width=True, height=620)
    else:
        st.error("market_snapshot.csv missing")

with tab2:
    p = OUT / "taiwan_candidates.csv"
    if p.exists():
        df = pd.read_csv(p, dtype={"code": str})
        cols = [c for c in [
            "candidate_rank","code","ticker","name","exchange","industry","last_price_date","price",
            "ret_5d","ret_20d","rs_20d_vs_bench","rs_60d_vs_bench","acceleration","keynes_legacy",
            "keynes_v2","bias20","avg_turnover20_twd","taiwan_candidate_score_v1"
        ] if c in df.columns]
        st.caption("Discovery candidates only — NOT Hidden Dragon confirmation and NOT a buy list.")
        st.dataframe(df[cols], use_container_width=True, height=680)
    else:
        st.warning("taiwan_candidates.csv is not available yet. Run the v2.4 workflow.")

with tab3:
    p = OUT / "transmission_watchlist.csv"
    if p.exists():
        df = pd.read_csv(p, dtype={"taiwan_code": str})
        st.warning(
            "Every row is HYPOTHESIS_ONLY. v2.4 requires an explicit company-level economic linkage edge, "
            "but causal / fundamental validation is still mandatory before decision use."
        )
        preferred = [c for c in [
            "global_theme","global_theme_strength_v1","taiwan_code","taiwan_name","taiwan_industry",
            "economic_role","linkage_tier","linkage_confidence","link_mechanism","evidence_required",
            "taiwan_candidate_score_v1","taiwan_rs20","taiwan_acceleration","taiwan_keynes_v2",
            "taiwan_industry_breadth_support","contradiction_flag","combined_hypothesis_score_v2","status"
        ] if c in df.columns]
        st.dataframe(df[preferred] if preferred else df, use_container_width=True, height=680)
    else:
        st.warning("transmission_watchlist.csv missing")

with tab4:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Global theme breadth")
        p = OUT / "theme_breadth.csv"
        if p.exists():
            st.dataframe(pd.read_csv(p), use_container_width=True, height=600)
    with c2:
        st.subheader("Taiwan industry breadth")
        p = OUT / "taiwan_industry_breadth.csv"
        if p.exists():
            st.dataframe(pd.read_csv(p), use_container_width=True, height=600)

with tab5:
    st.subheader("Economic Linkage Graph audit")
    st.caption(
        "PROMOTED means: global theme strong enough + Taiwan stock in the quantitative candidate funnel + "
        "explicit linkage tier/confidence passed. NOT_IN_TAIWAN_FUNNEL is not a rejection of the business linkage; "
        "it only means the Taiwan price/quant signal is not currently strong enough."
    )
    p = OUT / "transmission_linkage_audit.csv"
    if p.exists():
        audit = pd.read_csv(p, dtype={"taiwan_code": str})
        st.dataframe(audit, use_container_width=True, height=520)
        if "audit_status" in audit.columns:
            st.bar_chart(audit["audit_status"].value_counts())
    else:
        st.warning("transmission_linkage_audit.csv missing")
    gp = OUT / "economic_linkage_graph.csv"
    if gp.exists():
        with st.expander("View canonical Economic Linkage Graph"):
            st.dataframe(pd.read_csv(gp, dtype={"taiwan_code": str}), use_container_width=True, height=520)

st.caption(
    "Research rule: Scanner outputs describe observable market structure and explicit economic-linkage hypotheses. "
    "Gemini validates company-specific causality, catalysts, fundamentals and counter-evidence. Final ETF vs stock, "
    "position risk, entry and exit remain downstream decisions."
)
