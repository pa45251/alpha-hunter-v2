from company_research_runner import run


def test_every_thesis_called_separately_and_unchanged_never_recalled(tmp_path):
    h = dict(run_id='run', research_targets=[dict(driver_id='D')], company_research_targets=[dict(ticker=str(i),driver_id='D',research_question='why') for i in range(17)])
    p = dict(targets=[], company_targets=[])
    calls = []
    def call(task, sources, shared, key, logs):
        calls.append(task)
        return dict(results=[dict(driver_id='D', state='UNKNOWN')] if task['research_targets'] else [], company_research_coverage=[dict(t, status='UNKNOWN_AFTER_RESEARCH', reason='Missing fact') for t in task['company_research_targets']]), None
    cache = tmp_path/'cache.json'
    first = run(h,p,cache,tmp_path/'logs',call)
    assert len(calls) == 18
    assert all(len(t['company_research_targets']) <= 1 for t in calls)
    assert len(first['company_research_coverage']) == 17
    second = run(h,p,cache,tmp_path/'logs',call)
    assert len(calls) == 18
    assert all(r['cache_hit'] for r in second['execution_ledger'])
    h['company_research_targets'][3]['research_question'] = 'Changed setup question'
    run(h,p,cache,tmp_path/'logs',call)
    assert len(calls) == 19


def test_transport_failure_remains_terminal_and_is_not_retried(tmp_path):
    h = dict(run_id='run', company_research_targets=[dict(ticker='1234',driver_id='D')])
    p = dict(document_contract='EXACT_COMPANY_DOCUMENT_V1', company_targets=[])
    def forbidden(*args):
        raise AssertionError('No document means no model call')
    result=run(h,p,tmp_path/'cache',tmp_path/'logs',forbidden)
    assert result['company_execution_failures'][0]['failure_code']=='TRANSPORT_FAILED'
    assert not result['company_opportunities']


def test_company_call_cannot_write_other_thesis(tmp_path):
    h = dict(run_id='run', company_research_targets=[dict(ticker='1234',driver_id='D')])
    def call(*args):
        return dict(company_research_coverage=[dict(ticker='OTHER',driver_id='D',status='SUPPORTED')]),None
    result=run(h,{},tmp_path/'cache',tmp_path/'logs',call)
    assert result['company_execution_failures'][0]['failure_code']=='SCHEMA_FAILED'
