from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
EXPECTED_REPOSITORY = "pa45251/alpha-hunter-v2"
EXPECTED_BRANCH = os.getenv("GITHUB_REF_NAME", "main")
EXPECTED_SCHEMA = "2.6"
EXPECTED_SCANNER_PREFIX = "2.6"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_research_handoff(out_dir: str | Path = "output") -> dict[str, Any]:
    """Build the terminal, non-circular handoff for the Research Layer.

    The manifest cryptographically authenticates scanner outputs. canonical_gate.py
    validates that manifest and produces gate_report.json + research_packet.json.
    This terminal handoff then hashes those three already-finalized artifacts. Nothing
    upstream hashes research_handoff.json, so there is no circular hash dependency.
    """
    out = Path(out_dir)
    manifest_path = out / "manifest.json"
    gate_path = out / "gate_report.json"
    packet_path = out / "research_packet.json"
    handoff_path = out / "research_handoff.json"

    required = (manifest_path, gate_path, packet_path)
    missing = [p.name for p in required if not p.exists()]
    if missing:
        if handoff_path.exists():
            handoff_path.unlink()
        raise RuntimeError(f"Research handoff forbidden: missing={missing}")

    manifest = _read_json(manifest_path)
    gate = _read_json(gate_path)
    packet = _read_json(packet_path)

    errors: list[str] = []
    if manifest.get("repository") != EXPECTED_REPOSITORY:
        errors.append("REPOSITORY_MISMATCH")
    if manifest.get("branch") != EXPECTED_BRANCH:
        errors.append("BRANCH_MISMATCH")
    if str(manifest.get("schema_version")) != EXPECTED_SCHEMA:
        errors.append("SCHEMA_MISMATCH")
    if not str(manifest.get("scanner_version", "")).startswith(EXPECTED_SCANNER_PREFIX):
        errors.append("SCANNER_VERSION_MISMATCH")
    if manifest.get("status") != "PASS":
        errors.append("MANIFEST_NOT_PASS")
    if gate.get("gate_status") != "PASS":
        errors.append("GATE_NOT_PASS")
    if packet.get("gate_status") != "PASS":
        errors.append("PACKET_NOT_PASS")

    run_ids = {
        str(manifest.get("run_id", "")),
        str(gate.get("run_id", "")),
        str(packet.get("run_id", "")),
    }
    if "" in run_ids or len(run_ids) != 1:
        errors.append("RUN_ID_MISMATCH")

    actual_manifest_sha = _sha256(manifest_path)
    if gate.get("manifest_sha256") != actual_manifest_sha:
        errors.append("GATE_MANIFEST_HASH_MISMATCH")
    if packet.get("manifest_sha256") != actual_manifest_sha:
        errors.append("PACKET_MANIFEST_HASH_MISMATCH")

    if errors:
        if handoff_path.exists():
            handoff_path.unlink()
        raise RuntimeError("Research handoff forbidden: " + ",".join(errors))

    repo = os.getenv("GITHUB_REPOSITORY", EXPECTED_REPOSITORY)
    branch = os.getenv("GITHUB_REF_NAME", EXPECTED_BRANCH)
    run_id = next(iter(run_ids))

    artifacts = {}
    for name, path in (
        ("manifest", manifest_path),
        ("gate_report", gate_path),
        ("research_packet", packet_path),
    ):
        artifacts[name] = {
            "relative_path": f"output/{path.name}",
            "raw_url": f"https://raw.githubusercontent.com/{repo}/{branch}/output/{path.name}",
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }

    handoff = {
        "contract": "ALPHA_HUNTER_V2_6_1_RESEARCH_HANDOFF",
        "handoff_version": "1.0",
        "handoff_status": "PASS",
        "generated_at_taipei": datetime.now(TAIPEI).isoformat(),
        "repository": EXPECTED_REPOSITORY,
        "branch": EXPECTED_BRANCH,
        "schema_version": manifest["schema_version"],
        "scanner_version": manifest["scanner_version"],
        "run_id": run_id,
        "gate_status": gate["gate_status"],
        "causal_rule": "PRICE_CANNOT_CREATE_CAUSALITY",
        "transport_policy": {
            "source_identity": "GitHub repository pa45251/alpha-hunter-v2 branch main only",
            "preferred_transport": "GitHub connector exact path output/research_handoff.json",
            "fallback_transport": f"https://raw.githubusercontent.com/{EXPECTED_REPOSITORY}/{EXPECTED_BRANCH}/output/research_handoff.json",
            "do_not_substitute": [
                "Streamlit tables",
                "GitHub search results",
                "similarly named repositories",
                "forks or alternate branches",
                "cached or reconstructed scanner outputs",
            ],
        },
        "artifacts": artifacts,
        "research_entrypoint": artifacts["research_packet"],
        "research_rule": (
            "Research may begin only when handoff_status=PASS, gate_status=PASS, "
            "run_id is consistent, and the fetched research_packet SHA256 matches this handoff."
        ),
    }
    handoff_path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")
    return handoff


def company_research_targets(out: Path = Path('output'), limit: int | None = None, *, research_only: bool = True) -> list[dict]:
    """Select decision-changing gaps; legacy limit never truncates nominations."""
    import pandas as pd
    manifest = _read_json(out / 'manifest.json')
    run_id = manifest['run_id']
    frames = []
    for name in ['reverse_transmission_candidates.csv', 'structural_matches.csv']:
        path = out / name
        if not path.exists():
            continue
        x = pd.read_csv(path, dtype={'taiwan_code': str})
        if 'run_id' not in x:
            continue
        x = x[x.run_id.astype(str).eq(run_id)]
        if 'ticker' not in x and 'taiwan_ticker' in x:
            x['ticker'] = x['taiwan_ticker']
        if 'ticker' in x:
            frames.append(x)
    candidates_path = out / 'taiwan_candidates.csv'
    if candidates_path.exists():
        candidates = pd.read_csv(candidates_path)
        candidates = candidates[candidates.get('run_id', pd.Series('', index=candidates.index)).astype(str).eq(run_id)]
        mapped = {str(t) for f in frames for t in f['ticker']}
        candidates = candidates[~candidates.ticker.astype(str).isin(mapped)].copy()
        candidates['driver_id'] = 'UNMAPPED_OPPORTUNITY'
        candidates['driver_label'] = 'UNMAPPED / WHY?'
        candidates['research_priority_score'] = candidates.get('taiwan_early_score_v2', 0)
        frames.append(candidates)
    if not frames:
        return []
    x = pd.concat(frames, ignore_index=True)
    x['research_priority'] = pd.to_numeric(x.get('reverse_research_priority', pd.Series(index=x.index, dtype=float)), errors='coerce').fillna(
        pd.to_numeric(x.get('research_priority_score', pd.Series(index=x.index, dtype=float)), errors='coerce')).fillna(0)
    x['_extended'] = x['reaction_state'].isin(['EXTENDED', 'BROKEN'])
    x = x.sort_values(['_extended','research_priority'], ascending=[True,False]).drop_duplicates(['ticker','driver_id'])
    from driver_gates import attach_price_gates, thesis_gates
    from opportunity_advisory import price_plan
    from canonical_evidence import read_evidence
    try:
        saved = read_evidence('market_snapshot.json', out).get('entry_histories') or {}
    except (RuntimeError, OSError, ValueError):
        saved = {}
    cols = ['ticker','name','driver_id','driver_label','driver_scope','global_theme','reaction_state',
            'global_peer_evidence','transmission_gap_proxy','economic_role','research_priority','bias20','ret_5d']
    records = x[[c for c in cols if c in x]].astype(object).where(pd.notna(x[[c for c in cols if c in x]]), None).to_dict('records')
    records = attach_price_gates(records, out)
    current_research = {}
    research_path = out / 'research_result_v3.json'
    if research_path.exists():
        payload = _read_json(research_path)
        if (payload.get('contract') == 'ALPHA_HUNTER_V3_VALIDATED_RESEARCH'
                and payload.get('status') == 'PASS' and payload.get('research_run_id') == run_id):
            current_research = payload
    from opportunity_advisory import validate_company_research
    from research_contract_v3 import validate_research_result
    now = datetime.now(ZoneInfo('UTC')).isoformat()
    company = {}
    nominated = {(c['ticker'], c['driver_id']) for c in records}
    for r in current_research.get('company_opportunities', []):
        try:
            validate_company_research(r, run_id, nominated, now)
            company[(r['ticker'], r['driver_id'])] = r
        except (ValueError, TypeError):
            continue
    rejected = set()
    for r in current_research.get('results', []):
        try:
            validate_research_result(r, {c['driver_id'] for c in records})
            if r.get('research_run_id') == run_id and r.get('state') == 'INACTIVE':
                rejected.add(r['driver_id'])
        except (ValueError, TypeError):
            continue
    # A known global mapping on any nominated edge prevents an unmapped local escape.
    global_tickers = {c['ticker'] for c in records if c.get('driver_id') != 'UNMAPPED_OPPORTUNITY'}
    from driver_gates import sealed_csv
    try:
        graph = sealed_csv('structural_exposure_graph.csv', out)
        global_codes = set(graph['taiwan_code'].astype(str).str.split('.').str[0].str.zfill(4))
    except (RuntimeError, OSError, ValueError, KeyError):
        global_codes = None
    for c in records:
        c['known_global_link'] = c['ticker'] in global_tickers or global_codes is None or c['ticker'].split('.')[0] in global_codes
        c['driver_rejected'] = c['driver_id'] in rejected
        c.update(thesis_gates(c, company.get((c['ticker'], c['driver_id'])), now))
        item = saved.get(c['ticker'])
        hist = pd.DataFrame(item['data'], columns=item['columns'], index=pd.to_datetime(item['index'])) if item else None
        c['entry_research_ready'] = bool(price_plan(hist)['price_ok'] and c.get('reaction_state') not in {'EXTENDED','BROKEN'})
        c['research_eligible'] = c['entry_research_ready'] and c['research_task'] not in {'NONE','WAIT_FOR_MARKET_DATA'}
        if not c['entry_research_ready'] and c['missing_gate'] != 'GLOBAL_REJECTED':
            c['research_task'] = 'WAIT_FOR_ENTRY'
    # The board retains all states; the research lane consumes only actionable gaps.
    return [c for c in records if c['research_eligible']] if research_only else records


def decision_research_handoff(out: Path = Path('output')) -> dict:
    packet = _read_json(out / 'research_packet.json')
    all_candidates = company_research_targets(out, research_only=False)
    eligible = [c for c in all_candidates if c['research_eligible']]
    driver_ids = {c['driver_id'] for c in eligible if c['missing_gate'] == 'CAUSAL_UNVERIFIED'}
    from driver_gates import sealed_csv
    # The packet's Top-30 is a presentation summary, not a nomination authority.
    queue = (sealed_csv('causal_research_queue.csv', out).to_dict('records')
             if (out / 'causal_research_queue.csv').exists() else packet.get('research_queue_top30', []))
    drivers = [r for r in queue if r['driver_id'] in driver_ids]
    return dict(contract='ALPHA_HUNTER_DECISION_GAP_HANDOFF', run_id=packet['run_id'],
                research_targets=drivers, company_research_targets=eligible,
                deferred_candidates=[dict(ticker=c['ticker'], driver_id=c['driver_id'],
                                          missing_gate=c['missing_gate'], research_task=c['research_task'])
                                     for c in all_candidates if not c['research_eligible']])


if __name__ == "__main__":
    result = build_research_handoff("output")
    print(json.dumps(result, ensure_ascii=False, indent=2))
