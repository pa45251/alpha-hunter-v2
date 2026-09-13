from __future__ import annotations

import json
from pathlib import Path

OUT = Path("output")


def _fmt(value) -> str:
    return str(value if value is not None else "UNKNOWN").replace("|", "/").replace("\n", " ")


def build() -> str:
    packet = json.loads((OUT / "deep_review_packet_v4.json").read_text(encoding="utf-8"))
    final = json.loads((OUT / "final_candidate_review_v4.json").read_text(encoding="utf-8"))
    if str(packet.get("run_id") or "") != str(final.get("run_id") or ""):
        raise RuntimeError("FINAL_BOARD_RUN_MISMATCH")
    targets = {str(x.get("thesis_id")): x for x in packet.get("targets") or []}
    lines = [
        "# Alpha Hunter — Final User Action Board",
        "",
        f"- Run: `{_fmt(final.get('run_id'))}`",
        "- This is the user-facing final review layer. Scanner/research boards remain diagnostic.",
        "- Challenger cannot upgrade an action, move entry/stop, change risk gates, or authorize orders.",
        "- Automatic order execution remains disabled.",
        "",
    ]
    results = final.get("results") or []
    if not results:
        lines += [
            "## Final Actions",
            "",
            "- No thesis passed deterministic deep-review admission in this snapshot.",
        ]
        return "\n".join(lines) + "\n"
    lines += ["## Final Actions", ""]
    order = {"BUY": 0, "EARLY BUY": 1, "WAIT": 2, "PASS": 3}
    rows = sorted(results, key=lambda x: (order.get(str(x.get("final_action")), 9), str(x.get("ticker"))))
    for idx, row in enumerate(rows, 1):
        target = targets.get(str(row.get("thesis_id"))) or {}
        lines += [
            f"### {idx}. {_fmt(row.get('ticker'))} {_fmt(target.get('name'))} — {_fmt(row.get('final_action'))}",
            "",
            f"- **Canonical action:** {_fmt(row.get('canonical_action'))}",
            f"- **Challenger verdict:** {_fmt(row.get('challenger_verdict'))}",
            f"- **Driver:** {_fmt(target.get('driver'))}",
            f"- **Company transmission:** {_fmt(target.get('company_transmission'))}",
            f"- **Entry:** {_fmt(target.get('entry'))}",
            f"- **Invalidation:** {_fmt(target.get('invalidation'))}",
            f"- **Worst-zone risk:** {_fmt(target.get('risk_pct'))}",
            f"- **Next validation / add condition:** {_fmt(target.get('next_validation'))}",
            f"- **Counter-evidence:** {_fmt(target.get('counter_evidence'))}",
            f"- **Review rationale:** {_fmt(row.get('rationale'))}",
            "",
        ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    text = build()
    (OUT / "final_action_board_v4.md").write_text(text, encoding="utf-8")
    print("Wrote final user-facing action board")
