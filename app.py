from pathlib import Path
import pandas as pd
import streamlit as st

from scanner_core import ScanConfig, run_scan, write_outputs, append_audit_log

st.set_page_config(page_title="Alpha Hunter v2", page_icon="🌎", layout="wide")
st.title("🌎 Alpha Hunter v2 — Global Trend Sensor")
st.caption("Quant sensor only. Final causality / thesis / trade decision belongs to the research layer.")

if st.button("🚀 Run live scan", type="primary"):
    with st.spinner("Scanning global universe..."):
        r = run_scan("config/universe.csv", ScanConfig())
        write_outputs(r)
        append_audit_log(r)
    st.success("Scan complete")

snap = Path("output/market_snapshot.csv")
breadth = Path("output/theme_breadth.csv")
registry = Path("output/leader_registry.csv")

if snap.exists():
    df = pd.read_csv(snap)
    st.subheader("Dynamic leaders")
    cols = [c for c in ["ticker","name","theme","price","ret_5d","rs_20d_vs_bench","rs_60d_vs_bench","keynes_legacy","keynes_v2","leader_score_v1","raw_leader_state"] if c in df.columns]
    st.dataframe(df[cols].head(80), use_container_width=True, height=550)
else:
    st.info("No snapshot yet. Click Run live scan or run daily_scan.py.")

if breadth.exists():
    st.subheader("Theme breadth")
    st.dataframe(pd.read_csv(breadth), use_container_width=True)

if registry.exists():
    st.subheader("Leader registry with hysteresis")
    st.dataframe(pd.read_csv(registry), use_container_width=True)
