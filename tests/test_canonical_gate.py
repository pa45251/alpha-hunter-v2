import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from canonical_gate import validate_canonical_snapshot

TAIPEI = ZoneInfo("Asia/Taipei")


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_gate_rejects_mixed_run(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    files = {
        "causal_research_queue.csv": pd.DataFrame({"run_id": ["A"], "driver_id": ["D1"], "activation_state": ["UNRESOLVED_RESEARCH_REQUIRED"]}),
        "structural_matches.csv": pd.DataFrame({"run_id": ["B"], "driver_id": ["D1"], "decision_eligible": [False]}),
        "causal_graph_audit.csv": pd.DataFrame({"run_id": ["A"], "driver_id": ["D1"]}),
        "causal_driver_taxonomy.csv": pd.DataFrame({"driver_id": ["D1"]}),
        "structural_exposure_graph.csv": pd.DataFrame({"driver_id": ["D1"], "taiwan_code": ["0001"]}),
        "taiwan_candidates.csv": pd.DataFrame({"ticker": ["0001.TW"]}),
    }
    for name, df in files.items():
        df.to_csv(out / name, index=False)
    declared=[]
    for name in files:
        p=out/name
        declared.append({"name":name,"sha256":sha(p),"raw_url":f"https://raw.githubusercontent.com/pa45251/alpha-hunter-v2/main/output/{name}"})
    today=datetime.now(TAIPEI).date().isoformat()
    manifest={
        "repository":"pa45251/alpha-hunter-v2","branch":"main","schema_version":"2.6","scanner_version":"2.6.0",
        "run_id":"A","status":"PASS","missing_required_files":[],"pipeline_checks":{"x":True},
        "canonical_manifest_raw_url":"https://raw.githubusercontent.com/pa45251/alpha-hunter-v2/main/output/manifest.json",
        "generated_at_taipei":datetime.now(TAIPEI).isoformat(),"global":{"latest_price_date":today},"taiwan":{"latest_price_date":today},
        "authoritative_files":declared,
    }
    (out/"manifest.json").write_text(json.dumps(manifest))
    r=validate_canonical_snapshot(out)
    assert r["gate_status"] == "FAIL"
    assert r["failure_code"] == "MIXED_SNAPSHOT_DATA"
