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
    result = subprocess.run([sys.executable, "entry_plan_trace_v2.py"], check=False)
    if result.returncode:
        print("WARNING: optional entry trace failed; daily action board is intact")
    raise SystemExit(0)

from canonical_evidence import assert_output_lineage

OUT = Path("output")
run_id = assert_output_lineage(["decision_packet.json", "risk_regime.json"])

BLOCKING_STAGE = {
    'DRIVER_UNKNOWN': 'EXPOSURE',
    'GLOBAL_PRICE_WEAK': 'PRICE_RISK',
    'GLOBAL_PRICE_UNCONFIRMED': 'PRICE_RISK',
    'CAUSAL_UNVERIFIED': 'ACTIVATION',
    'COMPANY_TRANSMISSION_UNVERIFIED': 'TRANSMISSION',
    'ENTRY': 'ENTRY',
    'ECONOMIC_DRIVER_REJECTED': 'REJECTED',
}


def load(name: str) -> dict:
    path = OUT / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def md(value) -> str:
    return str(value if value is not None else "UNKNOWN").replace("|", "/").replace("\n", " ")


def _trading_action(row: dict) -> str | None:
    """Return only a qualified trading action.

    Evidence-unresolved rows may retain the legacy internal WAIT field for compatibility,
    but they are not user-facing WAIT decisions until the thesis has reached ENTRY.
    """
    action = str(row.get('action') or '')
    if action in {'BUY', 'EARLY BUY', 'PASS'}:
        return action
    if action == 'WAIT' and row.get('missing_gate') == 'ENTRY':
        return 'WAIT'
    return None


def _select_opportunities(limit: int = 5) -> list[dict]:
    from opportunity_advisory import assess, rank_opportunities, validate_company_research
    from canonical_evidence import load_histories
    from research_handoff import company_research_targets, decision_research_handoff
    from research_admission_v4 import apply_admission, thesis_id
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

    admitted = apply_admission(decision_research_handoff(OUT), out=OUT)
    admission_by_thesis: dict[str, dict] = {}
    for item in admitted.get('company_research_targets') or []:
        if isinstance(item, dict) and item.get('thesis_id'):
            admission_by_thesis[str(item['thesis_id'])] = item
    for item in admitted.get('deferred_candidates') or []:
        if isinstance(item, dict) and item.get('thesis_id'):
            admission_by_thesis[str(item['thesis_id'])] = item

    rows = []
    for candidate in candidates:
        candidate['driver_rejected'] = candidate['driver_id'] in rejected
        candidate['thesis_id'] = candidate.get('thesis_id') or thesis_id(
            str(candidate.get('ticker')), str(candidate.get('driver_id')), candidate.get('event_id')
        )
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
        admission = admission_by_thesis.get(str(row.get('thesis_id'))) or {}
        row['research_state'] = str(admission.get('admission_state') or 'NO_RESEARCH')
        row['research_question'] = admission.get('research_question')
        row['admission_reason'] = admission.get('admission_reason')
        row['wake_condition'] = admission.get('wake_condition')
        row['blocking_stage'] = BLOCKING_STAGE.get(row.get('missing_gate'), 'EXPOSURE')
        row['trading_action'] = _trading_action(row)
        # decision_state is retained for existing consumers, but now means qualified action
        # or explicitly UNQUALIFIED rather than overloading RESEARCH as a trading action.
        row['decision_state'] = row['trading_action'] or 'UNQUALIFIED'
        rows.append(row)

    top = rank_opportunities(rows, limit)
    from opportunity_advisory import VERSION
    from entry_risk import RISK_CONTRACT
    payload = dict(
        policy_version=VERSION,
        risk_contract=RISK_CONTRACT,
        source_run_id=run_id,
        generated_at_utc=now,
        public_lineage_id=(load('decision_packet.json').get('decision_bridge') or {}).get('public_lineage_id'),
        auto_trade_allowed=False,
        research_admission_summary=admitted.get('admission_summary') or {},
        top_opportunities=top,
        all_candidates=rows,
    )
    cleaned = json.loads(pd.Series([payload]).to_json(orient='values'))[0]
    (OUT / 'opportunity_advisory.json').write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')
    return top


def _render_row(lines: list[str], row: dict, index: int, label: str) -> None:
    lines += [f"### {index}. {md(row['ticker'])} {md(row['name'])} — {label}", ""]
    fields = [
        ('WHY', 'why'), ('Driver', 'driver'), ('Blocking stage', 'blocking_stage'),
        ('Driver state', 'driver_state'), ('Company transmission', 'company_transmission'),
        ('International price', 'international_price_state'), ('International causal', 'international_causal_state'),
        ('Current gate', 'missing_gate'), ('Research state', 'research_state'),
        ('Research question', 'research_question'), ('Wake condition', 'wake_condition'),
        ('International evidence', 'international'), ('Relative', 'relative'), ('Regime', 'regime'),
        ('Technical state', 'technical'), ('Why price', 'price_reason'), ('Entry state', 'entry_state'),
        ('Entry', 'entry'), ('Actual price risk', 'risk_summary'), ('Invalidation', 'invalidation'),
        ('Add trigger', 'add_trigger'), ('Main counter-evidence', 'main_counter_evidence'),
        ('Main risk', 'main_risk'), ('What would make us wrong', 'what_would_make_us_wrong'),
    ]
    for field_label, key in fields:
        value = row.get(key)
        if value not in {None, ''}:
            lines.append(f"- **{field_label}:** {md(value)}")
    if row.get('trading_action') in {'BUY', 'EARLY BUY'}:
        lines.append('- **Planned-position ceiling:** 35% of planned position; this is not a risk budget or order size.')
    for evidence in row.get('evidence', []) + row.get('international_evidence', []):
        lines.append(f"- Evidence: {md(evidence['claim'])} [{md(evidence['source_title'])}]({evidence['source_url']})")
    lines.append('')


packet = load("decision_packet.json")
regime = load("risk_regime.json")
activation = packet.get("activation_layer") or {}
opportunities = _select_opportunities(5)

trade_rows = [r for r in opportunities if r.get('trading_action') in {'BUY', 'EARLY BUY', 'WAIT'}]
pass_rows = [r for r in opportunities if r.get('trading_action') == 'PASS']
fact_rows = [r for r in opportunities if r.get('research_state') == 'FACT_CHECK' and not r.get('trading_action')]
observe_rows = [r for r in opportunities if r.get('research_state') == 'OBSERVE' and not r.get('trading_action')]
drop_rows = [r for r in opportunities if r.get('research_state') == 'DROP_THIS_RUN' and not r.get('trading_action')]
no_research_rows = [r for r in opportunities if r.get('research_state') == 'NO_RESEARCH' and not r.get('trading_action')]
trade_counts = {
    action: sum(r.get('trading_action') == action for r in opportunities)
    for action in ['BUY', 'EARLY BUY', 'WAIT', 'PASS']
}
research_counts = {
    'FACT_CHECK': len(fact_rows),
    'OBSERVE': len(observe_rows),
    'DROP_THIS_RUN': len(drop_rows),
    'NO_RESEARCH': len(no_research_rows),
}

lines = [
    "# Alpha Hunter — Action Board", "",
    f"- Run: `{run_id}`",
    f"- Market session: `{regime.get('risk_snapshot_date', 'UNKNOWN')}`",
    f"- Risk regime: **{regime.get('regime', 'UNKNOWN')}**",
    f"- Causal evidence: `{activation.get('source', 'UNKNOWN')}`",
    "- Core rule: price nominates; non-price facts establish economic exposure/activation/transmission; price/risk decides timing.",
    f"- Trading actions: BUY={trade_counts['BUY']} / EARLY BUY={trade_counts['EARLY BUY']} / WAIT={trade_counts['WAIT']} / PASS={trade_counts['PASS']}",
    f"- Research workload: FACT_CHECK={research_counts['FACT_CHECK']} / OBSERVE={research_counts['OBSERVE']} / DROP_THIS_RUN={research_counts['DROP_THIS_RUN']} / NO_RESEARCH={research_counts['NO_RESEARCH']}",
    "- FACT_CHECK is the bounded model-research workload. OBSERVE/DEFERRED rows are not LLM tasks until a wake condition changes.",
    "",
    "## Trading Decision Queue", "",
]

if trade_rows:
    for i, row in enumerate(trade_rows, 1):
        _render_row(lines, row, i, row['trading_action'])
else:
    lines.append('- No thesis-qualified BUY / EARLY BUY / WAIT in this snapshot.')

lines += ["", "## Active Fact-Check Queue", ""]
if fact_rows:
    for i, row in enumerate(fact_rows[:12], 1):
        _render_row(lines, row, i, f"FACT_CHECK — {row['blocking_stage']}")
    if len(fact_rows) > 12:
        lines.append(f"- {len(fact_rows) - 12} additional admitted fact checks remain in the canonical JSON ledger.")
else:
    lines.append('- No candidate currently requires model fact research.')

lines += [
    "", "## Ledger Summary", "",
    f"- Observe / wake-condition candidates: {len(observe_rows)}",
    f"- Dropped this run by deterministic veto: {len(drop_rows)}",
    f"- Other unqualified rows requiring no current research: {len(no_research_rows)}",
    f"- PASS candidates: {len(pass_rows)}",
    f"- Total canonical theses retained for audit: {len(opportunities)}",
    '', '- BUY / EARLY BUY are advisory views at the displayed entry zone, never brokerage orders.',
    '- WAIT is reserved for a thesis that reached ENTRY but is waiting for a concrete timing/setup condition.',
    '- UNKNOWN does not automatically create a research job; FACT_CHECK admission requires a decision-changing factual question.',
    '- A gap outside the zone or new thesis counter-evidence requires reassessment before taking risk.',
    '- Prices and R/R use sealed closed sessions; upside references are resistance or disclosed base-height scenarios, not return forecasts.',
    '- Automatic order execution remains disabled. Frozen execution permissions are unchanged.', '',
]

(OUT / "action_board.md").write_text("\n".join(lines), encoding="utf-8")
print(
    f"Wrote first-principles action board: run_id={run_id} "
    f"trade_decisions={len(trade_rows)} fact_checks={len(fact_rows)} total={len(opportunities)}"
)
