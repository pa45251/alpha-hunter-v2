import hashlib
import json
from pathlib import Path

import pytest

from research_handoff import build_research_handoff


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def build_valid_fixture(out: Path, run_id: str = "RUN-A") -> None:
    out.mkdir()
    manifest = {
        "repository": "pa45251/alpha-hunter-v2",
        "branch": "main",
        "schema_version": "2.6",
        "scanner_version": "2.6.0",
        "run_id": run_id,
        "status": "PASS",
    }
    write_json(out / "manifest.json", manifest)
    manifest_sha = sha(out / "manifest.json")
    write_json(out / "gate_report.json", {
        "gate_status": "PASS",
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
    })
    write_json(out / "research_packet.json", {
        "gate_status": "PASS",
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
    })


def test_handoff_hashes_terminal_artifacts_without_cycle(tmp_path):
    out = tmp_path / "output"
    build_valid_fixture(out)
    h = build_research_handoff(out)
    assert h["handoff_status"] == "PASS"
    assert h["run_id"] == "RUN-A"
    assert h["artifacts"]["manifest"]["sha256"] == sha(out / "manifest.json")
    assert h["artifacts"]["gate_report"]["sha256"] == sha(out / "gate_report.json")
    assert h["artifacts"]["research_packet"]["sha256"] == sha(out / "research_packet.json")
    assert (out / "research_handoff.json").exists()


def test_handoff_rejects_mixed_run(tmp_path):
    out = tmp_path / "output"
    build_valid_fixture(out)
    packet = json.loads((out / "research_packet.json").read_text())
    packet["run_id"] = "RUN-B"
    write_json(out / "research_packet.json", packet)
    with pytest.raises(RuntimeError, match="RUN_ID_MISMATCH"):
        build_research_handoff(out)
    assert not (out / "research_handoff.json").exists()


def test_handoff_rejects_manifest_hash_mismatch(tmp_path):
    out = tmp_path / "output"
    build_valid_fixture(out)
    gate = json.loads((out / "gate_report.json").read_text())
    gate["manifest_sha256"] = "bad"
    write_json(out / "gate_report.json", gate)
    with pytest.raises(RuntimeError, match="GATE_MANIFEST_HASH_MISMATCH"):
        build_research_handoff(out)
