from __future__ import annotations

import json
from pathlib import Path

OUT = Path("output")
BOARD = OUT / "action_board.md"
ALIGN = OUT / "global_alignment.json"


def _md(v) -> str:
    return str(v if v is not None else "").replace("|", "/").replace("\n", " ").strip()


def main() -> None:
    if not BOARD.exists():
        raise RuntimeError("ACTION_BOARD_MISSING")
    if not ALIGN.exists():
        raise RuntimeError("GLOBAL_ALIGNMENT_OUTPUT_MISSING")
    packet = json.loads(ALIGN.read_text(encoding="utf-8"))
    top = packet.get("top_aligned") or []
    old = BOARD.read_text(encoding="utf-8")

    lines = [
        "## 0.5 Global Alignment Leaderboard",
        "- Purpose: find Taiwan stocks whose own trend quality is supported by the corresponding international market and an ACTIVE causal driver.",
        "- Alignment score is a relative opportunity/evidence score, **not a calibrated win probability**.",
    ]
    if top:
        best = top[0]
        lines.append(
            f"- Highest alignment now: **{_md(best.get('ticker'))} {_md(best.get('name'))}** — "
            f"score `{_md(best.get('alignment_score'))}` / `{_md(best.get('alignment_action'))}` / "
            f"global `{_md(best.get('international_theme'))}` / reaction `{_md(best.get('reaction_state'))}`"
        )
        lines += [
            "",
            "| Rank | Taiwan stock | Global theme | Alignment | Global | Taiwan | Breadth | Keynes | State |",
            "|---:|---|---|---:|---:|---:|---:|---:|---|",
        ]
        for r in top[:10]:
            lines.append(
                f"| {_md(r.get('alignment_rank'))} | {_md(r.get('ticker'))} {_md(r.get('name'))} | "
                f"{_md(r.get('international_theme'))} | {_md(r.get('alignment_score'))} | "
                f"{_md(r.get('global_trend_score'))} | {_md(r.get('taiwan_trend_score'))} | "
                f"{_md(r.get('international_breadth_score'))} | {_md(r.get('keynes_quality_rank'))} | "
                f"{_md(r.get('alignment_action'))} |"
            )
    else:
        lines.append("- No stock currently passes all Global Alignment hard gates.")
    lines += ["", "Global Alignment is advisory only; BROKEN/EXTENDED names cannot become fresh entries through this leaderboard.", ""]
    block = "\n".join(lines)

    marker = "# Alpha Hunter — Action Board"
    if old.startswith(marker):
        rest = old[len(marker):].lstrip("\n")
        new = marker + "\n\n" + block + "\n" + rest
    else:
        new = block + "\n" + old
    BOARD.write_text(new, encoding="utf-8")
    print(f"Prepended Global Alignment summary: eligible={len(top)}")


if __name__ == "__main__":
    main()
