from __future__ import annotations

import json
from pathlib import Path

OUT = Path("output")
BOARD = OUT / "action_board.md"
REGIME = OUT / "risk_regime.json"
ALLOC = OUT / "portfolio_allocation_advisory.json"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _md(v) -> str:
    return str(v if v is not None else "").replace("|", "/").replace("\n", " ").strip()


def main() -> None:
    if not BOARD.exists():
        raise RuntimeError("ACTION_BOARD_MISSING")
    risk = _load(REGIME)
    alloc = _load(ALLOC)
    old = BOARD.read_text(encoding="utf-8")

    lines = ["## 0. Portfolio allocation / cash regime"]
    if risk.get("status") == "READY":
        lines += [
            f"- Global risk regime: `{_md(risk.get('regime'))}` / score `{_md(risk.get('risk_score'))}`",
            f"- Target cash / dry-powder buffer: **{_md(risk.get('target_cash_pct'))}%**",
            "- For leveraged portfolios, a higher buffer should generally be implemented by reducing gross exposure before accumulating idle cash.",
        ]
    else:
        lines.append("- Global risk regime unavailable; no cash target is inferred.")

    best = alloc.get("best_new_opportunity") or {}
    if best:
        lines.append(
            f"- Best new opportunity: **{_md(best.get('ticker'))} {_md(best.get('name'))}** — "
            f"`{_md(best.get('advisory_action'))}` / edge `{_md(best.get('edge_score'))}` / reaction `{_md(best.get('reaction_state'))}`"
        )

    rotations = alloc.get("rotations") or []
    if rotations:
        lines += [
            "",
            "| Source alias | Destination | Rotation | Edge spread | Trim source | Redeploy of trim | Keep as buffer |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
        for r in rotations[:5]:
            lines.append(
                f"| {_md(r.get('source_alias'))} | {_md(r.get('destination_ticker'))} {_md(r.get('destination_name'))} | "
                f"{_md(r.get('rotation_action'))} | {_md(r.get('edge_spread'))} | {_md(r.get('suggested_source_trim_pct'))}% | "
                f"{_md(r.get('suggested_redeploy_pct_of_trim'))}% | {_md(r.get('suggested_risk_buffer_pct_of_trim'))}% |"
            )
    else:
        lines.append("- Rotation: no source/destination pair currently clears the policy threshold, or the risk regime blocks redeployment.")

    lines += [
        "",
        "Rotation and cash outputs are CIO advisories only. They do not authorize brokerage orders.",
        "",
    ]
    block = "\n".join(lines)

    marker = "# Alpha Hunter — Action Board"
    if old.startswith(marker):
        rest = old[len(marker):].lstrip("\n")
        new = marker + "\n\n" + block + "\n" + rest
    else:
        new = block + "\n" + old
    BOARD.write_text(new, encoding="utf-8")
    print(f"Prepended portfolio allocation summary: regime={risk.get('regime')} rotations={len(rotations)}")


if __name__ == "__main__":
    main()
