"""Run existing bounded research after deterministic gap-directed retrieval refinement."""
import json
import os
from pathlib import Path

import company_research_runner as base
from research_targeted_retrieval_v1 import enhance_prefetch


def main():
    handoff_path = Path(os.getenv('ALPHA_HUNTER_RESEARCH_SELECTION_PATH', '/tmp/research_handoff.json'))
    prefetch_path = Path(os.getenv('ALPHA_HUNTER_RESEARCH_TRANSPORT_PATH', '/tmp/research_prefetch_v3.json'))
    handoff = json.loads(handoff_path.read_text())
    prefetch = json.loads(prefetch_path.read_text())
    if handoff['run_id'] != prefetch.get('research_run_id'):
        raise RuntimeError('RESEARCH_TRANSPORT_RUN_MISMATCH')

    prefetch = enhance_prefetch(handoff, prefetch, timeout=12, per_query=3)
    prefetch_path.write_text(json.dumps(prefetch, ensure_ascii=False, indent=2))

    result = base.run(
        handoff,
        prefetch,
        Path('.alpha-hunter/company_research_cache.json'),
        Path('/tmp/company_research_logs'),
    )
    Path('output/research_result_v3.raw.txt').write_text(json.dumps(result, ensure_ascii=False))
    Path('output/company_research_execution.json').write_text(
        json.dumps(dict(run_id=handoff['run_id'], tasks=result['execution_ledger'],
                        targeted_retrieval=prefetch.get('targeted_retrieval_version')), indent=2)
    )


if __name__ == '__main__':
    main()
