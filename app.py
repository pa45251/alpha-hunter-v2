from datetime import datetime, time
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

TAIPEI = ZoneInfo("Asia/Taipei")
OUT = Path("output")

st.set_page_config(page_title="Alpha Hunter v2.3", page_icon="🌎", layout="wide")
st.title("🌎 Alpha Hunter v2.3 — Global + Taiwan Sensor")
st.caption(
    "Official data comes from scheduled GitHub Actions. Global Sensor finds world leadership; "
    "Taiwan Sensor scans the full TWSE/TPEX common-stock universe and only publishes the research funnel outputs."
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

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Global scanned", G.get("scanned_count", "?"))
c2.metric("Global themes", G.get("theme_count", "?"))
c3.metric("Taiwan universe", T.get("universe_count", "?"))
c4.metric("Taiwan scanned", T.get("scanned_count", "?"))
c5.metric("Taiwan candidates", T.get("candidate_count", "?"))

st.info(
    "Automation: GitHub Actions is the official trigger. You do not need to open this app. "
    "Taiwan full-market rows are scanned in-memory; only candidates/breadth/universe/contract outputs are committed, "
    "which avoids unnecessary Git repository growth."
)

with st.expander("Canonical data contract / freshness details"):
    st.json(manifest)


tab1, tab2, tab3, tab4 = st.tabs([
    "Global Leaders", "Taiwan Candidates", "Global → Taiwan Hypotheses", "Breadth"
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
        st.warning("taiwan_candidates.csv is not available yet. Run the v2.3 workflow.")

with tab3:
    p = OUT / "transmission_watchlist.csv"
    if p.exists():
        df = pd.read_csv(p, dtype={"taiwan_code": str})
        st.warning("Every row is HYPOTHESIS_ONLY. Causal / fundamental validation is mandatory before decision use.")
        st.dataframe(df, use_container_width=True, height=680)
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

st.caption(
    "Research rule: Scanner outputs describe observable market structure. Gemini validates causes/catalysts/counter-evidence. "
    "Final ETF vs stock, position risk, entry and exit remain downstream decisions."
)
