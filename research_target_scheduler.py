from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

CONTRACT = "ALPHA_HUNTER_RESEARCH_TARGET_SCHEDULER_V1"
ENTRY_STATES = {"PRE_CONFIRMATION", "EARLY_CONFIRMATION", "CONFIRMING", "PULLBACK", "PERSISTENT"}
KEEP_FIELDS = (
    "research_priority", "global_theme", "driver_id", "driver_label", "driver_scope",
    "global_theme_strength_v2", "global_latest_price_date", "activation_evidence_required",
    "counter_evidence_required", "price_cannot_activate_driver",
)


def _priority(row: dict) -> float:
    try:
        return float(row.get("research_priority", 0) or 0)
    except Exception:
        return 0.0


def _theme_context(structural: pd.DataFrame | None) -> dict[str, tuple[int, int]]:
    if structural is None or structural.empty or "global_theme" not in structural.columns:
        return {}
    x = structural.copy()
    breadth = x.get("semantic_breadth_state", pd.Series("UNKNOWN", index=x.index)).fillna("UNKNOWN").astype(str).str.upper()
    reaction = x.get("reaction_state", pd.Series("UNKNOWN", index=x.index)).fillna("UNKNOWN").astype(str).str.upper()
    out: dict[str, tuple[int, int]] = {}
    for theme, idx in x.groupby("global_theme").groups.items():
        i = list(idx)
        healthy = int(breadth.loc[i].eq("HEALTHY").any())
        entry = int(reaction.loc[i].isin(ENTRY_STATES).any())
        out[str(theme)] = (healthy, entry)
    return out


def select_research_targets(
    queue_rows: list[dict],
    structural: pd.DataFrame | None = None,
    max_targets: int = 10,
    max_per_theme: int = 2,
) -> list[dict]:
    """Diversify scarce research capacity without allowing price to create causality.

    Taiwan breadth/reaction may only nominate a theme earlier for external research.
    They are never emitted as causal supporting evidence and never alter the required
    ACTIVE/INACTIVE/UNKNOWN evidence contract.
    """
    max_targets = max(1, int(max_targets))
    max_per_theme = max(1, int(max_per_theme))
    dedup: dict[str, dict] = {}
    for raw in queue_rows or []:
        if not isinstance(raw, dict):
            continue
        driver = str(raw.get("driver_id", "")).strip()
        theme = str(raw.get("global_theme", "")).strip() or "UNMAPPED"
        if driver and driver not in dedup:
            row = dict(raw)
            row["global_theme"] = theme
            dedup[driver] = row
    if not dedup:
        return []

    by_theme: dict[str, list[dict]] = {}
    for row in dedup.values():
        by_theme.setdefault(str(row["global_theme"]), []).append(row)
    for rows in by_theme.values():
        rows.sort(key=_priority, reverse=True)

    context = _theme_context(structural)
    def theme_key(theme: str):
        healthy, entry = context.get(theme, (0, 0))
        max_priority = max((_priority(r) for r in by_theme[theme]), default=0.0)
        return (healthy, entry, max_priority)

    themes = sorted(by_theme, key=theme_key, reverse=True)
    selected: list[dict] = []
    counts = {theme: 0 for theme in themes}
    # Round-robin across themes so one hot/ambiguous sector cannot consume the full budget.
    for depth in range(max_per_theme):
        for theme in themes:
            if len(selected) >= max_targets:
                break
            rows = by_theme[theme]
            if depth >= len(rows):
                continue
            selected.append(rows[depth])
            counts[theme] += 1
        if len(selected) >= max_targets:
            break
    return selected


def build_handoff(packet: dict, structural: pd.DataFrame | None, max_targets: int, max_per_theme: int) -> dict:
    rows = packet.get("research_queue_top30") or []
    targets = select_research_targets(rows, structural, max_targets=max_targets, max_per_theme=max_per_theme)
    compact = [{k: row.get(k) for k in KEEP_FIELDS if k in row} for row in targets]
    return {
        "contract": CONTRACT,
        "run_id": packet.get("run_id"),
        "lane": "OPPORTUNITY_DISCOVERY",
        "causal_rule": packet.get("causal_rule") or "PRICE_CANNOT_CREATE_CAUSALITY",
        "scheduler": {
            "policy": "DIVERSIFIED_BOUNDED_RESEARCH",
            "max_targets": int(max_targets),
            "max_per_theme": int(max_per_theme),
            "price_can_nominate_research": True,
            "price_can_create_causality": False,
        },
        "research_targets": compact,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", default="output/research_packet.json")
    ap.add_argument("--structural", default="output/structural_matches.csv")
    ap.add_argument("--out", default="/tmp/research_handoff.json")
    ap.add_argument("--max-targets", type=int, default=10)
    ap.add_argument("--max-per-theme", type=int, default=2)
    args = ap.parse_args()
    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    structural = pd.read_csv(args.structural, dtype={"taiwan_code": str}) if Path(args.structural).exists() else pd.DataFrame()
    handoff = build_handoff(packet, structural, args.max_targets, args.max_per_theme)
    if not handoff["research_targets"]:
        raise SystemExit("No research targets available")
    Path(args.out).write_text(json.dumps(handoff, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("scheduled research drivers:", [r.get("driver_id") for r in handoff["research_targets"]])


if __name__ == "__main__":
    main()
