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

RESEARCH_GATES = {
    'DRIVER_UNKNOWN',
    'GLOBAL_PRICE_UNCONFIRMED',
    'CAUSAL_UNVERIFIED',
    'COMPANY_TRANSMISSION_UNVERIFIED',
}
BLOCKING_STAGE = {
    'DRIVER_UNKNOWN': 'EXPOSURE',
    'GLOBAL_PRICE_UNCONFIRMED': 'ACTIVATION',
    'CAUSAL_UNVERIFIED': 'ACTIVATION',
    'COMPANY_TRANSMISSION_UNVERIFIED': 'TRANSMISSION',
    'ENTRY': 'ENTRY',
    'GLOBAL_REJECTED': 'REJECTED',
}


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


def _decision_state(row: dict) -> str:
    """Keep evidence incompleteness separate from an actual trading WAIT.

    RESEARCH is an assessment state, not a fifth trading action. A true WAIT is reserved
    for a thesis that has reached the ENTRY gate but whose timing/setup is not ready.
    """
    if row.get('action') == 'PASS':
        return 'PASS'
    if row.get('missing_gate') in RESEARCH_GATES:
        return 'RESEARCH'
    return str(row.get('action') or 'WAIT')


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
        from entry_risk import validate_plan
        validate_plan(row)
        checked = coverage.get((candidate['ticker'], candidate['driver_id']))
        row['research_completed'] = bool(evidence or checked)
        if checked and not evidence:
            row['why'] = str(checked.get('reason') or row['why'])
            row['main_risk'] = 'Exact company / driver transmission remains unverified; no entry recommendation'
        row['research_priority'] = candidate.get('research_priority', 0)
        row['research_eligible'] = bool(candidate.get('research_eligible'))
        row['blocking_stage'] = BLOCKING_STAGE.get(row.get('missing_gate'), 'EXPOSURE')
        row['decision_state'] = _decision_state(row)
        rows.append(row)
    top = rank_opportunities(rows, limit)
    from opportunity_advisory import VERSION
    from entry_risk import RISK_CONTRACT
    payload = dict(policy_version=VERSION, risk_contract=RISK_CONTRACT, source_run_id=run_id, generated_at_utc=now,
                   public_lineage_id=(load('decision_packet.json').get('decision_bridge') or {}).get('public_lineage_id'),
                   auto_trade_allowed=False, top_opportunities=top, all_candidates=rows)
    # Git publication preserves every nomination for prospective audits; the Markdown board
    # below spends human attention only on qualified trading decisions and active research.
    cleaned = json.loads(pd.Series([payload]).to_json(orient='values'))[0]
    (OUT / 'opportunity_advisory.json').write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')
    return top


def _render_row(lines: list[str], row: dict, index: int, label: str) -> None:
    lines += [f"### {index}. {md(row['ticker'])} {md(row['name'])} — {label}", ""]
    for field_label, key in [('WHY', 'why'), ('Driver', 'driver'), ('Blocking stage', 'blocking_stage'),
                             ('Driver state', 'driver_state'), ('Company transmission', 'company_transmission'),
                             ('International price', 'international_price_state'),
                             ('International causal', 'international_causal_state'),
                             ('Current gate', 'missing_gate'), ('International evidence', 'international'),
                             ('Relative', 'relative'), ('Regime', 'regime'), ('Technical state', 'technical'),
                             ('Why price', 'price_reason'), ('Entry state', 'entry_state'), ('Entry', 'entry'),
                             ('Actual price risk', 'risk_summary'), ('Invalidation', 'invalidation'),
                             ('Add trigger', 'add_trigger'), ('Main counter-evidence', 'main_counter_evidence'),
                             ('Main risk', 'main_risk'), ('What would make us wrong', 'what_would_make_us_wrong')]:
        lines.append(f"- **{field_label}:** {md(row.get(key, 'Unverified'))}")
    if row.get('action') == 'EARLY BUY':
        lines.append('- **Initial size:** 35% of planned position; reassess before adding.')
    for evidence in row.get('evidence', []) + row.get('international_evidence', []):
        lines.append(f"- Evidence: {md(evidence['claim'])} [{md(evidence['source_title'])}]({evidence['source_url']})")
    lines.append('')


packet = load("decision_packet.json")
regime = load("risk_regime.json")
activation = packet.get("activation_layer") or {}
launch = packet.get("launch_layer") or {}
opportunities = _select_opportunities(5)

trade_rows = [r for r in opportunities if r.get('decision_state') in {'BUY', 'EARLY BUY', 'WAIT'}]
research_rows = [r for r in opportunities if r.get('decision_state') == 'RESEARCH' and r.get('research_eligible')]
deferred_research = [r for r in opportunities if r.get('decision_state') == 'RESEARCH' and not r.get('research_eligible')]
pass_rows = [r for r in opportunities if r.get('decision_state') == 'PASS']
counts = {
    'BUY': sum(r.get('decision_state') == 'BUY' for r in opportunities),
    'EARLY BUY': sum(r.get('decision_state') == 'EARLY BUY' for r in opportunities),
    'WAIT': sum(r.get('decision_state') == 'WAIT' for r in opportunities),
    'RESEARCH': sum(r.get('decision_state') == 'RESEARCH' for r in opportunities),
    'PASS': sum(r.get('decision_state') == 'PASS' for r in opportunities),
}

lines = [
    "# Alpha Hunter — Action Board", "",
    f"- Run: `{run_id}`",
    f"- Market session: `{regime.get('risk_snapshot_date', 'UNKNOWN')}`",
    f"- Risk regime: **{regime.get('regime', 'UNKNOWN')}**",
    f"- Causal evidence: `{activation.get('source', 'UNKNOWN')}`",
    "- Core rule: price nominates; company facts define exposure; independent evidence validates the driver; company evidence validates transmission; price/risk decides timing.",
    f"- Decision counts: BUY={counts['BUY']} / EARLY BUY={counts['EARLY BUY']} / WAIT={counts['WAIT']} / RESEARCH={counts['RESEARCH']} / PASS={counts['PASS']}",
    "- RESEARCH is an unresolved evidence state, not a trading recommendation.",
    "",
    "## Trading Decision Queue", "",
]

if trade_rows:
    for i, row in enumerate(trade_rows, 1):
        _render_row(lines, row, i, row['decision_state'])
else:
    lines.append('- No thesis-qualified BUY / EARLY BUY / WAIT in this snapshot.')

lines += ["", "## Active Research Queue", ""]
if research_rows:
    # This is presentation-only. The canonical JSON retains every candidate; showing the
    # first 12 prevents unresolved evidence from consuming the entire human attention budget.
    for i, row in enumerate(research_rows[:12], 1):
        _render_row(lines, row, i, f"RESEARCH — {row['blocking_stage']}")
    if len(research_rows) > 12:
        lines.append(f"- {len(research_rows) - 12} additional research-eligible candidates remain in the canonical JSON ledger.")
else:
    lines.append('- No price-relevant unresolved candidate requires active research.')

lines += [
    "", "## Ledger Summary", "",
    f"- Deferred unresolved candidates: {len(deferred_research)}",
    f"- PASS candidates: {len(pass_rows)}",
    f"- Total canonical candidates retained for audit: {len(opportunities)}",
    '', '- BUY / EARLY BUY are advisory views at the displayed entry zone, never brokerage orders.',
    '- WAIT means the thesis reached the entry stage but timing/setup is not ready; unresolved evidence is shown as RESEARCH instead.',
    '- A gap outside the zone or new thesis counter-evidence requires reassessment before taking risk.',
    '- Prices and R/R use sealed closed sessions; upside references are resistance or disclosed base-height scenarios, not return forecasts.',
    '- Automatic order execution remains disabled. Frozen execution permissions are unchanged.', '',
]

(OUT / "action_board.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote first-principles action board: run_id={run_id} decisions={len(trade_rows)} active_research={len(research_rows)} total={len(opportunities)}")
