from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import subprocess
import sys

if __name__ == "__main__" and "--refresh" in sys.argv:
    for name in [
        "position_cio_advisory.json", "position_alias_actions.json",
        "portfolio_allocation_v2.json", "portfolio_allocation_advisory.json",
        "cio_advisory.json", "cio_advisory.csv",
    ]:
        (Path("output") / name).unlink(missing_ok=True)
    for script in ["risk_regime.py", "global_alignment_v2.py", "entry_plan_run_v2.py"]:
        subprocess.run([sys.executable, script], check=True)
    subprocess.run([sys.executable, __file__], check=True)
    # Keep exact V2 plans as diagnostics; the daily brief exposes only four advisory actions.
    result = subprocess.run([sys.executable, "entry_plan_trace_v2.py"], check=False)
    if result.returncode:
        print("WARNING: optional entry trace failed; daily action board is intact")
    raise SystemExit(0)

from canonical_evidence import assert_output_lineage

OUT = Path("output")
run_id = assert_output_lineage(["decision_packet.json", "risk_regime.json"])


def load(name: str) -> dict:
    path = OUT / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv(name: str) -> pd.DataFrame:
    path = OUT / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype={"taiwan_code": str, "code": str})
    except Exception:
        return pd.DataFrame()


def md(value) -> str:
    return str(value if value is not None else "UNKNOWN").replace("|", "/").replace("\n", " ")


def _select_opportunities(limit: int = 5) -> list[dict]:
    from opportunity_advisory import assess, rank_opportunities, validate_company_research
    from canonical_evidence import load_histories
    from research_handoff import company_research_targets
    from datetime import datetime, timezone
    candidates = company_research_targets(OUT, research_only=False)
    histories = load_histories(list({r['ticker'] for r in candidates}))
    research = load('research_result_v3.json')
    now = datetime.now(timezone.utc).isoformat()
    accepted = {}
    coverage = {}
    targets = {(r['ticker'], r['driver_id']) for r in candidates}
    if (research.get('status') == 'PASS' and research.get('research_run_id') == run_id):
        coverage = {(r.get('ticker'), r.get('driver_id')): r for r in research.get('company_research_coverage', []) if isinstance(r, dict)}
        for r in research.get('company_opportunities') or []:
            try:
                validate_company_research(r, run_id, targets, now)
                accepted[(r['ticker'], r['driver_id'])] = r
            except (ValueError, TypeError):
                continue
    rejected = {r.get('driver_id') for r in research.get('results', []) if r.get('state') == 'INACTIVE'} if research.get('research_run_id') == run_id and research.get('status') == 'PASS' else set()
    rows = []
    for candidate in candidates:
        candidate['driver_rejected'] = candidate['driver_id'] in rejected
        evidence = accepted.get((candidate['ticker'], candidate['driver_id']))
        row = assess(candidate, evidence, load('risk_regime.json'), histories.get(candidate['ticker']), now)
        checked = coverage.get((candidate['ticker'], candidate['driver_id']))
        row['research_completed'] = bool(evidence or checked)
        if checked and not evidence:
            row['why'] = str(checked.get('reason') or row['why'])
            row['main_risk'] = 'Exact company / driver transmission remains unverified; no entry recommendation'
        row['research_priority'] = candidate.get('research_priority', 0)
        rows.append(row)
    top = rank_opportunities(rows, limit)
    from opportunity_advisory import VERSION
    payload = dict(policy_version=VERSION, source_run_id=run_id, generated_at_utc=now,
                   public_lineage_id=(load('decision_packet.json').get('decision_bridge') or {}).get('public_lineage_id'),
                   auto_trade_allowed=False, top_opportunities=top, all_candidates=rows)
    # Git publication preserves all nominations for prospective audits, not just winners.
    cleaned = json.loads(pd.Series([payload]).to_json(orient='values'))[0]
    (OUT / 'opportunity_advisory.json').write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')
    return top


packet = load("decision_packet.json")
regime = load("risk_regime.json")
activation = packet.get("activation_layer") or {}
launch = packet.get("launch_layer") or {}
opportunities = _select_opportunities(5)

lines = [
    "# Alpha Hunter — Action Board", "",
    f"- Run: `{run_id}`",
    f"- Market session: `{regime.get('risk_snapshot_date', 'UNKNOWN')}`",
    f"- Risk regime: **{regime.get('regime', 'UNKNOWN')}**",
    f"- Causal evidence: `{activation.get('source', 'UNKNOWN')}`",
    "- Core rule: find the anomaly -> understand WHY -> validate the same driver globally -> act only if price still offers a setup.",
    "",
    "## Simple Opportunity Brief", "",
]

if opportunities:
    for i, row in enumerate(opportunities, 1):
        lines += [f"### {i}. {md(row['ticker'])} {md(row['name'])} — {row['action']}", ""]
        for label, key in [('WHY', 'why'), ('Driver', 'driver'), ('Driver state', 'driver_state'),
                           ('Company transmission', 'company_transmission'),
                           ('International price', 'international_price_state'),
                           ('International causal', 'international_causal_state'),
                           ('Current gate', 'missing_gate'), ('International evidence', 'international'), ('Relative', 'relative'),
                           ('Regime', 'regime'), ('Technical state', 'technical'),
                           ('Why price', 'price_reason'), ('Entry', 'entry'),
                           ('Invalidation', 'invalidation'), ('Add trigger', 'add_trigger'),
                           ('Main counter-evidence', 'main_counter_evidence'), ('Main risk', 'main_risk'), ('What would make us wrong', 'what_would_make_us_wrong')]:
            lines.append(f"- **{label}:** {md(row.get(key, 'Unverified'))}")
        if row['action'] == 'EARLY BUY':
            lines.append('- **Initial size:** 35% of planned position; reassess before adding.')
        for evidence in row.get('evidence', []) + row.get('international_evidence', []):
            lines.append(f"- Evidence: {md(evidence['claim'])} [{md(evidence['source_title'])}]({evidence['source_url']})")
        lines.append('')
else:
    lines.append('- No sufficiently researched opportunity in this snapshot.')
lines += [
    '', '- BUY / EARLY BUY are advisory views at the displayed entry zone, never brokerage orders.',
    '- A gap outside the zone or new thesis counter-evidence requires reassessment before taking risk.',
    '- Prices and R/R use sealed closed sessions; upside references are resistance or disclosed base-height scenarios, not return forecasts.',
    '- Automatic order execution remains disabled. Frozen execution permissions are unchanged.', '',
]

(OUT / "action_board.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote simplified canonical action board: run_id={run_id} opportunities={len(opportunities)}")
