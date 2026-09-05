from datetime import datetime, time
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

TAIPEI = ZoneInfo("Asia/Taipei")

st.set_page_config(page_title="Alpha Hunter v2.2", page_icon="🌎", layout="wide")
st.title("🌎 Alpha Hunter v2.2 — Global Trend Sensor")
st.caption(
    "Official data comes from the scheduled GitHub Actions scan. "
    "This dashboard is view-only and does not create the official daily snapshot."
)

OUT = Path("output")
snap = OUT / "market_snapshot.csv"
breadth = OUT / "theme_breadth.csv"
registry = OUT / "leader_registry.csv"
meta_file = OUT / "market_snapshot.json"
universe_file = Path("config/universe.csv")


def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI)
        return dt.astimezone(TAIPEI)
    except Exception:
        return None


def _freshness(meta: dict):
    """Operational freshness gate for the scheduled snapshot.

    It deliberately judges the *scanner run*, not merely calendar distance from
    the last market date. This avoids false stale alarms on weekends/holidays.
    """
    now = datetime.now(TAIPEI)
    generated = _parse_dt(meta.get("generated_at_taipei"))
    quality = meta.get("scan_quality", {}) or {}

    if generated is None:
        return "STALE", "No valid scanner timestamp was found.", None

    age_h = (now - generated).total_seconds() / 3600
    weekday = now.weekday()  # Mon=0 ... Sun=6

    # Weekend, or Monday before the scheduled morning scan, can legitimately
    # still use Friday's recently generated snapshot.
    weekend_window = weekday in (5, 6) or (weekday == 0 and now.time() < time(7, 45))
    max_age_h = 84 if weekend_window else 30

    scanned = int(quality.get("scanned_count", 0) or 0)
    expected = None
    try:
        expected = len(pd.read_csv(universe_file)) if universe_file.exists() else None
    except Exception:
        expected = None

    coverage = (scanned / expected) if expected else None
    earliest = quality.get("earliest_price_date")
    latest = quality.get("latest_price_date")

    date_spread_days = None
    try:
        date_spread_days = (
            pd.Timestamp(latest).normalize() - pd.Timestamp(earliest).normalize()
        ).days
    except Exception:
        pass

    if age_h > max_age_h:
        return (
            "STALE",
            f"Official scanner output is {age_h:.1f} hours old. Do not use it for a new trading decision.",
            age_h,
        )

    if coverage is not None and coverage < 0.95:
        return (
            "WARNING",
            f"Scanner ran recently, but coverage is only {coverage:.1%} ({scanned}/{expected}).",
            age_h,
        )

    if date_spread_days is not None and date_spread_days > 3:
        return (
            "WARNING",
            f"Scanner ran recently, but security price dates span {date_spread_days} calendar days.",
            age_h,
        )

    return "FRESH", "Scheduled scanner output is recent and coverage checks passed.", age_h


if not meta_file.exists():
    st.error("🚨 STALE DATA — No official scanner metadata exists yet. Do not use this dashboard for a trading decision.")
    st.stop()

try:
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
except Exception as exc:
    st.error(f"🚨 STALE DATA — Could not read scanner metadata: {exc}")
    st.stop()

status, status_reason, age_h = _freshness(meta)
quality = meta.get("scan_quality", {}) or {}
generated = _parse_dt(meta.get("generated_at_taipei"))

if status == "FRESH":
    st.success(f"✅ DATA STATUS: FRESH — {status_reason}")
elif status == "WARNING":
    st.warning(f"⚠️ DATA STATUS: WARNING — {status_reason}")
else:
    st.error(f"🚨 DATA STATUS: STALE — {status_reason}")
    st.error("Hard gate: refresh the GitHub Actions scan before using these data for a new market decision.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Last market data", str(quality.get("latest_price_date", "Unknown")))
c2.metric(
    "Scanner generated (Taipei)",
    generated.strftime("%Y-%m-%d %H:%M") if generated else "Unknown",
)
c3.metric("Securities scanned", str(quality.get("scanned_count", "Unknown")))
c4.metric("Themes", str(quality.get("theme_count", "Unknown")))

with st.expander("Freshness gate details"):
    st.write(
        "The dashboard validates the scheduled scan timestamp, universe coverage, and dispersion of last price dates. "
        "Weekends and Monday before the scheduled scan receive a wider freshness window so Friday data are not falsely labeled stale."
    )
    st.json(
        {
            "status": status,
            "scanner_age_hours": round(age_h, 2) if age_h is not None else None,
            "generated_at_taipei": meta.get("generated_at_taipei"),
            "latest_price_date": quality.get("latest_price_date"),
            "earliest_price_date": quality.get("earliest_price_date"),
            "scanned_count": quality.get("scanned_count"),
            "theme_count": quality.get("theme_count"),
            "schema_version": meta.get("schema_version"),
        }
    )

st.info(
    "Automation: GitHub Actions runs the official scan at approximately 06:55 Asia/Taipei on weekdays. "
    "You do not need to open this app to trigger it. GitHub may occasionally start scheduled jobs a few minutes late."
)

if snap.exists():
    df = pd.read_csv(snap)
    st.subheader("Dynamic leaders")
    cols = [
        c for c in [
            "ticker", "name", "theme", "last_price_date", "price", "ret_5d",
            "rs_20d_vs_bench", "rs_60d_vs_bench", "acceleration",
            "keynes_legacy", "keynes_v2", "leader_score_v1", "raw_leader_state"
        ] if c in df.columns
    ]
    st.dataframe(df[cols].head(100), use_container_width=True, height=550)
else:
    st.error("market_snapshot.csv is missing from output/. Run the GitHub Actions workflow.")

if breadth.exists():
    st.subheader("Theme breadth")
    bdf = pd.read_csv(breadth)
    st.dataframe(bdf, use_container_width=True)

if registry.exists():
    st.subheader("Leader registry with hysteresis")
    rdf = pd.read_csv(registry)
    st.dataframe(rdf, use_container_width=True)

st.caption(
    "Research rule: FRESH means the automated data layer is usable as an input, not that any security is a buy. "
    "Causality, fundamentals, counter-evidence, portfolio fit, entry and exit still belong to the research layer."
)
