"""Exhaustive company research accounting; this module grants no trading action."""
from collections import Counter, defaultdict
from research_admission_v4 import thesis_id

OUTCOMES = ('SUPPORTED', 'REJECTED', 'UNKNOWN_AFTER_RESEARCH', 'TRANSPORT_FAILED', 'SCHEMA_FAILED')
COMPLETED = set(OUTCOMES[:3])


def identity(row):
    return str(row.get('thesis_id') or thesis_id(str(row.get('ticker')), str(row.get('driver_id')), row.get('event_id')))


def resolve_identity(row, targets):
    """Legacy missing driver is recoverable only with one unambiguous nomination."""
    if not isinstance(row, dict):
        raise ValueError('NON_OBJECT_COMPANY_RESULT')
    matches = [t for t in targets
               if (not row.get('thesis_id') or identity(t) == row['thesis_id'])
               and (not row.get('ticker') or t['ticker'] == row['ticker'])
               and (not row.get('driver_id') or t['driver_id'] == row['driver_id'])
               and (not row.get('event_id') or t.get('event_id') == row['event_id'])]
    if not (row.get('ticker') or row.get('thesis_id')) or len(matches) != 1:
        raise ValueError('AMBIGUOUS_OR_UNNOMINATED_COMPANY_IDENTITY')
    target = matches[0]
    return dict(row, ticker=target['ticker'], driver_id=target['driver_id'],
                thesis_id=identity(target), event_id=target.get('event_id'))


def finalize(targets, opportunities, coverage, failures, default_failure=None):
    """Exactly one terminal per admitted thesis. Contradictions fail closed."""
    ids = [identity(t) for t in targets]
    if len(ids) != len(set(ids)):
        raise ValueError('DUPLICATE_ADMITTED_THESIS')
    groups = defaultdict(lambda: defaultdict(list))
    diagnostics = []
    for kind, rows in [('opportunity', opportunities), ('coverage', coverage), ('failure', failures)]:
        if not isinstance(rows, list):
            diagnostics.append('MALFORMED_' + kind.upper())
            continue
        for row in rows:
            try:
                normalized = resolve_identity(row, targets)
                groups[normalized['thesis_id']][kind].append(normalized)
            except ValueError as exc:
                diagnostics.append(str(exc))
                # Ambiguous same-ticker results invalidate every affected thesis; never guess.
                for target in targets:
                    if isinstance(row, dict) and row.get('ticker') == target.get('ticker'):
                        groups[identity(target)]['failure'].append({'failure_code': 'SCHEMA_FAILED', 'reason': str(exc)})
    terminal, accepted = [], []
    for target in targets:
        tid = identity(target)
        parts = groups[tid]
        opp, cov, fail = parts['opportunity'], parts['coverage'], parts['failure']
        state, reason = default_failure or ('SCHEMA_FAILED', 'COMPANY_RESULT_OMITTED_FROM_RETURNED_PAYLOAD')
        if fail:
            state = 'TRANSPORT_FAILED' if all(x.get('failure_code') == 'TRANSPORT_FAILED' for x in fail) else 'SCHEMA_FAILED'
            reason = '; '.join(str(x.get('reason')) for x in fail)
        elif len(opp) > 1 or len(cov) > 1:
            state, reason = 'SCHEMA_FAILED', 'DUPLICATE_COMPANY_TERMINAL'
        elif opp:
            state = 'REJECTED' if opp[0].get('driver_state') == 'REJECTED' else 'SUPPORTED'
            reason = str(opp[0].get('why') or 'Validated company research')
            if cov and cov[0].get('status') != state:
                state, reason = 'SCHEMA_FAILED', 'CONFLICTING_COMPANY_TERMINALS'
            else:
                accepted.append(opp[0])
        elif cov:
            row = cov[0]
            state = row.get('status')
            if state == 'UNRESOLVED':
                state = row.get('reason_code', 'UNKNOWN_AFTER_RESEARCH')
            reason = row.get('reason')
            # SUPPORTED/REJECTED cannot be asserted by a coverage label without evidence.
            if state not in set(OUTCOMES[2:]) or not isinstance(reason, str) or not reason.strip():
                state, reason = 'SCHEMA_FAILED', 'INVALID_OR_UNBACKED_TERMINAL_OUTCOME'
        terminal.append(dict(thesis_id=tid, ticker=target['ticker'], driver_id=target['driver_id'],
                             event_id=target.get('event_id'), status=state, reason_code=state,
                             reason=reason, research_completed=state in COMPLETED))
    counts = Counter(r['status'] for r in terminal)
    summary = dict(admitted=len(ids), terminal_count=len(terminal),
                   counts={s: counts[s] for s in OUTCOMES},
                   exhaustive=True, research_complete=all(r['research_completed'] for r in terminal))
    return accepted, terminal, summary, diagnostics
