"""Allowlisted aggregate diagnostics; never export model text, URLs or private inputs."""
import json
from pathlib import Path

ERROR_CODES = {
 'research contract marker mismatch':'CONTRACT_MARKER',
 'research run_id mismatch':'RUN_ID',
 'per-driver run_id mismatch':'RUN_ID',
 'no valid top-level JSON object':'JSON_TRANSPORT',
 'empty autonomous research output':'EMPTY_RESPONSE',
 'future research timestamp':'FUTURE_RESEARCH_CLOCK',
 'published after research':'FUTURE_PUBLICATION',
 'source_count must equal':'SOURCE_COUNT',
 'missing fields':'MISSING_FIELDS',
 'unnominated/non-target':'TARGET_ID',
 'duplicate driver':'DUPLICATE_DRIVER',
}

def summarize(out):
    try:
        p=json.loads((Path(out)/'research_result_v3.json').read_text())
        codes=sorted({next((code for phrase,code in ERROR_CODES.items() if phrase in str(e)), 'OTHER_VALIDATION') for e in p.get('errors',[])})
        rows=p.get('results',[])
        count=sum(r.get('source_count',0) for r in rows if type(r.get('source_count')) is int)
        status=p.get('status')
        if status not in ('PASS','PARTIAL_FAIL_CLOSED','RESEARCH_UNAVAILABLE'):status='INVALID_STATUS'
        return {'status':status,'target_count':len(rows),'source_count':count,'validation_codes':codes,
                'classification':'D_INGEST_SCHEMA_OR_CONTRACT' if codes else ('A_OR_B_RETRIEVAL_EVIDENCE_UNRESOLVED' if count==0 else 'VALIDATED_SOURCE_COVERAGE')}
    except Exception:
        return {'classification':'F_DIAGNOSTIC_INPUT_UNAVAILABLE'}
