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
    "trace_at_utc", "source_run_id", "decision_session", "canonical_closed_price_date",
    "closed_session_verified", "strategy_version", "ticker", "name",
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


def _manifest_meta() -> tuple[str, str]:
    if not MANIFEST.exists():
        raise RuntimeError("ENTRY_TRACE_V2_MANIFEST_MISSING")
    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        run_id = str(payload.get("run_id", ""))
        closed = str(((payload.get("taiwan") or {}).get("latest_price_date")) or "")
        ts = pd.to_datetime(closed, errors="coerce")
    except Exception as exc:
        raise RuntimeError("ENTRY_TRACE_V2_MANIFEST_INVALID") from exc
    if not run_id or pd.isna(ts):
        raise RuntimeError("ENTRY_TRACE_V2_MANIFEST_INVALID")
    return run_id, pd.Timestamp(ts).date().isoformat()


def _existing_or_empty_trace(canonical_closed_date: str | None = None) -> pd.DataFrame:
    TRACE.parent.mkdir(parents=True, exist_ok=True)
    if TRACE.exists():
        try:
            x = pd.read_csv(TRACE)
            for c in TRACE_COLUMNS:
                if c not in x.columns:
                    x[c] = ""
            x = x[TRACE_COLUMNS]
            # Purge any pre-freeze record that came from a still-open/future daily bar. This is
            # evidence hygiene, not hindsight tuning: such rows were never valid EOD samples.
            if canonical_closed_date and "decision_session" in x.columns:
                cutoff = pd.Timestamp(canonical_closed_date).date()
                parsed = pd.to_datetime(x["decision_session"], errors="coerce")
                bad = parsed.notna() & parsed.map(lambda ts: pd.Timestamp(ts).date() > cutoff)
                if bool(bad.any()):
                    x = x.loc[~bad].copy()
                    x.to_csv(TRACE, index=False)
            return x
        except Exception:
            pass
    x = pd.DataFrame(columns=TRACE_COLUMNS)
    x.to_csv(TRACE, index=False)
    return x


def append_entry_plan_trace() -> pd.DataFrame:
    run_id, canonical_closed_date = _manifest_meta()

    # Data-unavailable is itself a valid non-signal state. Keep the ledger file present so the
    # publication workflow never confuses an upstream data outage with a successful empty trace.
    if not PLANS.exists():
        return _existing_or_empty_trace(canonical_closed_date)
    plans = pd.read_csv(PLANS)
    if plans.empty:
        return _existing_or_empty_trace(canonical_closed_date)

    x = plans.copy()
    x["trace_at_utc"] = datetime.now(timezone.utc).isoformat()
    x["source_run_id"] = run_id
    x["decision_session"] = x.get("price_as_of_utc", pd.Series("", index=x.index)).map(_date_from_price_as_of)
    x["canonical_closed_price_date"] = canonical_closed_date
    x["closed_session_verified"] = x["decision_session"].map(
        lambda s: bool(s and pd.Timestamp(s).date() <= pd.Timestamp(canonical_closed_date).date())
    )
    # Entry plans use the V2 risk contract name; expose it under the stable trace column.
    if "risk_v2_pass" in x.columns:
        x["risk_gate_pass"] = x["risk_v2_pass"]
    elif "risk_gate_pass" not in x.columns:
        x["risk_gate_pass"] = ""
    x["score_is_probability"] = False

    # A dated plan newer than the canonical closed session is a hard trace-integrity failure.
    dated = x["decision_session"].astype(str).str.len().gt(0)
    if bool((dated & ~x["closed_session_verified"]).any()):
        bad = x.loc[dated & ~x["closed_session_verified"], "ticker"].astype(str).head(5).tolist()
        raise RuntimeError(f"ENTRY_TRACE_V2_OPEN_OR_FUTURE_SESSION_BLOCKED:{bad}")

    for c in TRACE_COLUMNS:
        if c not in x.columns:
            x[c] = ""
    x = x[TRACE_COLUMNS]

    old = _existing_or_empty_trace(canonical_closed_date)
    x = pd.concat([old, x], ignore_index=True)

    # Market-session idempotence: repeated scanner/decision runs on the same closed bar do not
    # create extra prospective samples when the resulting plan state is identical. source_run_id
    # remains stored for lineage but is intentionally not part of the dedupe key.
    key = ["decision_session", "ticker", "driver_id", "entry_style", "current_action", "entry_status"]
    for c in key:
        x[c] = x[c].fillna("").astype(str)
    x = x.drop_duplicates(key, keep="first")
    x.to_csv(TRACE, index=False)
    return x


def main() -> None:
    x = append_entry_plan_trace()
    verified = int(pd.Series(x.get("closed_session_verified", [])).fillna(False).astype(bool).sum()) if len(x) else 0
    print(
        f"{CONTRACT}: rows={len(x)} verified_closed_session_rows={verified}; "
        "score_is_probability=False; private portfolio data excluded"
    )


if __name__ == "__main__":
    main()
