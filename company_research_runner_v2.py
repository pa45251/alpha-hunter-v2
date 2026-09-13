"""Run bounded research after deterministic gap-directed retrieval refinement.

This wrapper only changes execution semantics: company calls are serialized to avoid
provider/CLI contention, and unverifiable company support is conservatively downgraded
to UNKNOWN_AFTER_RESEARCH before ingest. Evidence gates are never relaxed.
"""
import concurrent.futures
import json
import os
from pathlib import Path

import company_research_runner as base
from company_research_terminal import identity
from company_source_documents import verify_document_claim
from research_targeted_retrieval_v1 import enhance_prefetch


class _SerialExecutor:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def map(self, fn, *iterables, timeout=None, chunksize=1):
        return map(fn, *iterables)


def _logged_call(task, sources, shared, key, log_dir):
    payload, failure = base.invoke(task, sources, shared, key, log_dir)
    if failure and str(failure[1]).startswith('CLI_EXIT_'):
        path = log_dir / f'{key}.stderr.txt'
        try:
            tail = ' '.join(path.read_text(errors='replace').split())[-1200:]
        except OSError:
            tail = ''
        if tail:
            print(f'copilot stderr {key}: {tail}', flush=True)
    return payload, failure


def _downgrade_unverifiable_support(result, prefetch, handoff):
    """Drop unsupported model support; never repair it into support.

    A bad/missing exact quote means the proposed company thesis is not evidentially
    complete. That is an investment UNKNOWN, not a transport/schema outage, provided
    thesis identity itself is valid.
    """
    docs_by_key = {}
    for packet in prefetch.get('company_targets', []):
        key = (str(packet.get('ticker')), str(packet.get('driver_id')))
        docs_by_key[key] = {
            str(source.get('source_url')): source
            for source in packet.get('candidate_sources', [])
            if source.get('source_url')
        }

    downgrade = {}
    kept = []
    for row in result.get('company_opportunities', []):
        key = (str(row.get('ticker')), str(row.get('driver_id')))
        docs = docs_by_key.get(key, {})
        try:
            exposures = row.get('exposure_evidence') or []
            if row.get('driver_state') != 'REJECTED' and not exposures:
                raise ValueError('SOURCE_BACKED_COMPANY_EXPOSURE_REQUIRED')
            for item in exposures:
                verify_document_claim(item, docs, specific=True)
            for item in row.get('fundamental_evidence') or []:
                verify_document_claim(item, docs)
            specific = [
                item for item in row.get('fundamental_evidence') or []
                if (docs.get(item.get('source_url')) or {}).get('evidence_role') != 'GENERIC_REVENUE_ONLY'
            ]
            if row.get('driver_state') != 'REJECTED' and not specific:
                raise ValueError('SPECIFIC_COMPANY_TRANSMISSION_REQUIRED')
            if row.get('driver_state') == 'REJECTED':
                counter = row.get('counter_evidence') or []
                if not counter:
                    raise ValueError('SOURCE_BACKED_REJECTION_REQUIRED')
                for item in counter:
                    verify_document_claim(item, docs, specific=True)
            kept.append(row)
        except ValueError as exc:
            code = str(exc)
            if code not in {
                'COMPANY_CLAIM_QUOTE_NOT_IN_DOCUMENT',
                'GENERIC_REVENUE_CANNOT_PROVE_SPECIFIC_DRIVER',
                'SOURCE_BACKED_COMPANY_EXPOSURE_REQUIRED',
                'SPECIFIC_COMPANY_TRANSMISSION_REQUIRED',
                'SOURCE_BACKED_REJECTION_REQUIRED',
            }:
                kept.append(row)
                continue
            downgrade[identity(row)] = (
                f'Proposed company support did not survive deterministic evidence verification: {code}'
            )
    result['company_opportunities'] = kept

    if not downgrade:
        return result

    targets = {identity(target): target for target in handoff.get('company_research_targets', [])}
    coverage = []
    emitted = set()
    for row in result.get('company_research_coverage', []):
        tid = identity(row)
        if tid not in downgrade:
            coverage.append(row)
            continue
        target = targets.get(tid)
        if target and tid not in emitted:
            coverage.append(dict(
                thesis_id=tid,
                ticker=target['ticker'],
                driver_id=target['driver_id'],
                event_id=target.get('event_id') or '',
                status='UNKNOWN_AFTER_RESEARCH',
                reason_code='UNKNOWN_AFTER_RESEARCH',
                reason=downgrade[tid],
                research_completed=True,
            ))
            emitted.add(tid)
    for tid, reason in downgrade.items():
        if tid in emitted:
            continue
        target = targets.get(tid)
        if target:
            coverage.append(dict(
                thesis_id=tid,
                ticker=target['ticker'],
                driver_id=target['driver_id'],
                event_id=target.get('event_id') or '',
                status='UNKNOWN_AFTER_RESEARCH',
                reason_code='UNKNOWN_AFTER_RESEARCH',
                reason=reason,
                research_completed=True,
            ))
    result['company_research_coverage'] = coverage
    return result


def main():
    handoff_path = Path(os.getenv('ALPHA_HUNTER_RESEARCH_SELECTION_PATH', '/tmp/research_handoff.json'))
    prefetch_path = Path(os.getenv('ALPHA_HUNTER_RESEARCH_TRANSPORT_PATH', '/tmp/research_prefetch_v3.json'))
    handoff = json.loads(handoff_path.read_text())
    prefetch = json.loads(prefetch_path.read_text())
    if handoff['run_id'] != prefetch.get('research_run_id'):
        raise RuntimeError('RESEARCH_TRANSPORT_RUN_MISMATCH')

    prefetch = enhance_prefetch(handoff, prefetch, timeout=12, per_query=3)
    prefetch_path.write_text(json.dumps(prefetch, ensure_ascii=False, indent=2))

    original_executor = concurrent.futures.ThreadPoolExecutor
    concurrent.futures.ThreadPoolExecutor = _SerialExecutor
    try:
        result = base.run(
            handoff,
            prefetch,
            Path('.alpha-hunter/company_research_cache.json'),
            Path('/tmp/company_research_logs'),
            call=_logged_call,
        )
    finally:
        concurrent.futures.ThreadPoolExecutor = original_executor

    result = _downgrade_unverifiable_support(result, prefetch, handoff)
    Path('output/research_result_v3.raw.txt').write_text(json.dumps(result, ensure_ascii=False))
    Path('output/company_research_execution.json').write_text(
        json.dumps(dict(run_id=handoff['run_id'], tasks=result['execution_ledger'],
                        targeted_retrieval=prefetch.get('targeted_retrieval_version'),
                        execution_mode='SERIAL_COMPANY_CALLS'), indent=2)
    )


if __name__ == '__main__':
    main()
