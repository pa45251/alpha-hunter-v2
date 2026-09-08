import json
from research_runtime_diagnostic import summarize

def test_diagnostic_classifies_schema_without_leaking_content(tmp_path):
    (tmp_path/'research_result_v3.json').write_text(json.dumps({'status':'PARTIAL_FAIL_CLOSED','errors':['PRIVATE_TICKER: per-driver run_id mismatch secret=PRIVATE_VALUE'],'results':[{'source_count':0}]}))
    result=summarize(tmp_path)
    assert result['validation_codes']==['RUN_ID']
    assert result['classification']=='D_INGEST_SCHEMA_OR_CONTRACT'
    assert 'PRIVATE' not in json.dumps(result)

def test_zero_sources_is_not_proof_of_genuine_evidence_absence(tmp_path):
    (tmp_path/'research_result_v3.json').write_text(json.dumps({'status':'PASS','errors':[],'results':[{'source_count':0}]}))
    assert summarize(tmp_path)['classification']=='A_OR_B_RETRIEVAL_EVIDENCE_UNRESOLVED'
