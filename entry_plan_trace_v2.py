from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

OUT = Path("output")
PLANS = OUT / "entry_plans_v2.csv"
MANIFEST = OUT / "manifest.json"
TRACE = OUT / "entry_plan_trace_v2.csv"
CONTRACT = "ALPHA_HUNTER_ENTRY_PLAN_TRACE_V2"

TRACE_COLUMNS = [
    "trace_at_utc", "source_run_id", "decision_session", "strategy_version", "ticker", "name",
    "global_theme", "driver_id", "entry_style", "reaction_state", "current_action", "entry_status",
    "entry_structure_valid", "risk_gate_pass", "global_alignment_score", "score_is_probability",
    "trigger_price", "buy_zone_low", "buy_zone_high", "invalidation_price", "reference_pivot",
    "atr_pct", "ma20", "ma60", "rs20", "rs60", "keynes_v2", "why_now", "why_not_now",
]


def _date_from_price_as_of(v) -> str:
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return ""
        return pd.Timestamp(ts).date().isoformat()
    except Exception:
        return ""


def append_entry_plan_trace() -> pd.DataFrame:
    if not PLANS.exists():
        return pd.DataFrame(columns=TRACE_COLUMNS)
    plans = pd.read_csv(PLANS)
    if plans.empty:
        return pd.DataFrame(columns=TRACE_COLUMNS)

    run_id = ""
    if MANIFEST.exists():
        try:
            run_id = str(json.loads(MANIFEST.read_text(encoding="utf-8")).get("run_id", ""))
        except Exception:
            run_id = ""

    x = plans.copy()
    x["trace_at_utc"] = datetime.now(timezone.utc).isoformat()
    x["source_run_id"] = run_id
    x["decision_session"] = x.get("price_as_of_utc", pd.Series("", index=x.index)).map(_date_from_price_as_of)
    x["score_is_probability"] = False
    for c in TRACE_COLUMNS:
        if c not in x.columns:
            x[c] = ""
    x = x[TRACE_COLUMNS]

    TRACE.parent.mkdir(parents=True, exist_ok=True)
    if TRACE.exists():
        old = pd.read_csv(TRACE)
        x = pd.concat([old, x], ignore_index=True)

    # Re-running the exact same source snapshot must not create extra prospective samples.
    key = ["source_run_id", "ticker", "driver_id", "entry_style", "current_action", "entry_status"]
    for c in key:
        x[c] = x[c].fillna("").astype(str)
    x = x.drop_duplicates(key, keep="first")
    x.to_csv(TRACE, index=False)
    return x


def main() -> None:
    x = append_entry_plan_trace()
    print(f"{CONTRACT}: rows={len(x)}; score_is_probability=False; private portfolio data excluded")


if __name__ == "__main__":
    main()
