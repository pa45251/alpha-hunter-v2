from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUT = Path("output")
BOARD_PATH = OUT / "action_board.md"
ALIGN_PATH = OUT / "global_alignment_v2.json"
ENTRY_PATH = OUT / "entry_plans_v2.json"
ROTATION_PATH = OUT / "portfolio_allocation_v2.json"

START = "<!-- ENTRY_V2_START -->"
END = "<!-- ENTRY_V2_END -->"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        if v != v:
            return "—"
        return f"{v:.2f}" if abs(v) >= 10 else f"{v:.4f}"
    return str(v).replace("|", "/").replace("\n", " ")


def _best(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    usable = [r for r in rows if bool(r.get("entry_structure_valid"))]
    if not usable:
        return None
    pool = usable
    def key(r: dict[str, Any]):
        status = str(r.get("entry_status", ""))
        order = 0 if status == "CONFIRMED_NEXT_SESSION_CONDITIONAL" else 1 if "WAITING" in status else 2
        score = r.get("global_alignment_score")
        try:
            score = float(score)
        except Exception:
            score = -1.0
        return (order, -score)
    return sorted(pool, key=key)[0]


def _plan_lines(title: str, plan: dict[str, Any] | None) -> list[str]:
    lines = [f"### {title}"]
    if not plan:
        return lines + ["- **NONE** — no candidate currently has a valid canonical V2 plan.", ""]
    lines += [
        f"- **{_fmt(plan.get('ticker'))} {_fmt(plan.get('name'))}** — `{_fmt(plan.get('current_action'))}` / `{_fmt(plan.get('entry_status'))}`",
        f"- Entry style: `{_fmt(plan.get('entry_style'))}`",
        f"- Trigger: **{_fmt(plan.get('trigger_price'))}**",
        f"- Buy zone: **{_fmt(plan.get('buy_zone_low'))} – {_fmt(plan.get('buy_zone_high'))}**",
        f"- Invalidation: **{_fmt(plan.get('invalidation_price'))}**",
        f"- Why now: {_fmt(plan.get('why_now'))}",
        f"- Why not now: {_fmt(plan.get('why_not_now'))}",
        "",
    ]
    return lines


def build_block(alignment: dict[str, Any], entries: dict[str, Any], rotation: dict[str, Any]) -> str:
    top = alignment.get("top_aligned") or []
    strongest = top[0] if top else None
    fresh = _best(entries.get("fresh") or [])
    pullback = _best(entries.get("pullback") or [])
    continuation = _best(entries.get("continuation") or [])

    lines = [
        START,
        "## Alpha Hunter V2 — Global Alignment + Exact Entry",
        "- Rule: alignment/edge scores are relative evidence ranks, **not win probabilities**.",
        "- Rule: EOD output never claims BUY_NOW without a fresh executable quote inside the buy zone.",
        "",
        "### A. Strongest Global-Aligned Trend",
    ]
    if strongest:
        lines.append(
            f"- **{_fmt(strongest.get('ticker'))} {_fmt(strongest.get('name'))}** — alignment `{_fmt(strongest.get('alignment_score'))}` / "
            f"global `{_fmt(strongest.get('international_theme'))}` / reaction `{_fmt(strongest.get('reaction_state'))}` / action `{_fmt(strongest.get('alignment_action'))}`"
        )
    else:
        lines.append("- **NONE** — no stock passes the V2 global-alignment hard gates.")
    lines += [""]
    lines += _plan_lines("B. Best Fresh Entry", fresh)
    lines += _plan_lines("C. Best Pullback Entry", pullback)
    lines += _plan_lines("D. Best Continuation Entry", continuation)

    lines += ["### E. Rotation / Exact Execution"]
    rots = rotation.get("rotations") or []
    if rots:
        r = rots[0]
        lines += [
            f"- Source: **{_fmt(r.get('source_alias'))}** → Destination: **{_fmt(r.get('destination_ticker'))} {_fmt(r.get('destination_name'))}**",
            f"- State: `{_fmt(r.get('rotation_action'))}`; trim now **{_fmt(r.get('suggested_source_trim_pct_now'))}%**",
            f"- Trigger: **{_fmt(r.get('trigger_price'))}**; Buy zone **{_fmt(r.get('buy_zone_low'))} – {_fmt(r.get('buy_zone_high'))}**; Invalidation **{_fmt(r.get('invalidation_price'))}**",
            f"- Required before rotation: `{_fmt(r.get('entry_trigger_required'))}`",
        ]
    else:
        lines.append("- **NO ROTATION NOW** — no destination simultaneously passes the canonical V2 opportunity + entry gate.")
    lines += [
        "",
        "V2 is shadow/advisory only. Exact levels are structure-derived conditional plans, not brokerage orders.",
        END,
    ]
    return "\n".join(lines)


def inject_block(old: str, block: str) -> str:
    if START in old and END in old:
        pre = old.split(START, 1)[0].rstrip()
        post = old.split(END, 1)[1].lstrip()
        return (pre + "\n\n" if pre else "") + block + ("\n\n" + post if post else "\n")
    marker = "# Alpha Hunter — Action Board"
    if old.startswith(marker):
        rest = old[len(marker):].lstrip("\n")
        return marker + "\n\n" + block + "\n\n" + rest
    return block + "\n\n" + old


def main() -> None:
    from canonical_evidence import assert_output_lineage
    assert_output_lineage(["decision_packet.json", "global_alignment_v2.json", "entry_plans_v2.json", "portfolio_allocation_v2.json"])
    if not BOARD_PATH.exists():
        raise RuntimeError("ACTION_BOARD_MISSING")
    alignment = _load(ALIGN_PATH)
    entries = _load(ENTRY_PATH)
    rotation = _load(ROTATION_PATH)
    old = BOARD_PATH.read_text(encoding="utf-8")
    block = build_block(alignment, entries, rotation)
    BOARD_PATH.write_text(inject_block(old, block), encoding="utf-8")
    print("Injected Entry V2 A-E action board summary")


if __name__ == "__main__":
    main()
