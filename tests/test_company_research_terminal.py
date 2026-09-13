import json
from pathlib import Path
from company_research_terminal import finalize, identity


def target(driver='A', event=None):
    return dict(ticker='1234.TW', driver_id=driver, event_id=event)


def test_legacy_missing_driver_coverage_is_recovered_once():
    _, rows, summary, _ = finalize([target()], [], [dict(ticker='1234.TW', status='UNRESOLVED', reason='No exact facts')], [])
    assert rows[0]['driver_id'] == 'A'
    assert rows[0]['status'] == 'UNKNOWN_AFTER_RESEARCH'
    assert summary['research_complete']


def test_ambiguous_identity_fails_every_affected_thesis():
    _, rows, _, _ = finalize([target(), target('B')], [], [dict(ticker='1234.TW', status='UNRESOLVED', reason='Unknown')], [])
    assert [r['status'] for r in rows] == ['SCHEMA_FAILED'] * 2


def test_duplicate_and_conflicting_results_never_keep_support():
    good = dict(target(), driver_state='CONFIRMED', why='Validated')
    for opportunities, coverage in [([good, good], []), ([good], [dict(target(), status='UNRESOLVED', reason='Missing')])]:
        accepted, rows, _, _ = finalize([target()], opportunities, coverage, [])
        assert not accepted
        assert rows[0]['status'] == 'SCHEMA_FAILED'


def test_transport_schema_unknown_are_distinct():
    targets = [target(x) for x in ['A', 'B', 'C', 'D', 'E']]
    opp = [dict(target('A'), driver_state='CONFIRMED', why='Validated'), dict(target('B'), driver_state='REJECTED', why='Counter evidence')]
    cov = [dict(target('C'), status='UNKNOWN_AFTER_RESEARCH', reason='No exact fact')]
    fail = [dict(target('D'), failure_code='TRANSPORT_FAILED', reason='Timeout')]
    _, rows, summary, _ = finalize(targets, opp, cov, fail)
    assert len(rows) == 5
    assert all(n == 1 for n in summary['counts'].values())
    assert not summary['research_complete']


def test_separate_local_events_keep_identity():
    targets = [target('UNMAPPED_OPPORTUNITY', 'event1'), target('UNMAPPED_OPPORTUNITY', 'event2')]
    cov = [dict(t, status='UNKNOWN_AFTER_RESEARCH', reason='Missing') for t in targets]
    _, rows, _, _ = finalize(targets, [], cov, [])
    assert len({r['thesis_id'] for r in rows}) == 2
    assert all(r['status'] == 'UNKNOWN_AFTER_RESEARCH' for r in rows)


def test_unbacked_rejection_is_schema_failure():
    _, rows, _, _ = finalize([target()], [], [dict(target(), status='REJECTED', reason='Model says no')], [])
    assert rows[0]['status'] == 'SCHEMA_FAILED'


def test_event_lookup_does_not_reuse_sibling_transmission():
    from company_research_terminal import lookup
    a, b = target('UNMAPPED_OPPORTUNITY','A'), target('UNMAPPED_OPPORTUNITY','B')
    assert lookup([a], b) is None
    assert lookup([a,b],b) == b
