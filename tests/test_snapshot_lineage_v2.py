import json
from pathlib import Path

import pytest

import snapshot_lineage_v2 as sl


def _write_inputs(tmp_path: Path, manifest_hash: str = "abc"):
    (tmp_path / "manifest.json").write_text(json.dumps({"run_id": "RUN1"}), encoding="utf-8")
    (tmp_path / "gate_report.json").write_text(json.dumps({
        "gate_status": "PASS", "run_id": "RUN1", "manifest_sha256": manifest_hash,
    }), encoding="utf-8")


def test_current_gate_and_manifest_hash_pass(monkeypatch, tmp_path):
    _write_inputs(tmp_path)
    monkeypatch.setattr(sl, "validate_canonical_snapshot", lambda _: {
        "gate_status": "PASS", "run_id": "RUN1", "manifest_sha256": "abc", "failure_code": None,
    })
    meta = sl.assert_decision_snapshot_current(tmp_path)
    assert meta["persisted_gate_matches_current_files"] is True
    assert meta["mixed_snapshot_allowed"] is False


def test_changed_files_after_persisted_gate_fail_closed(monkeypatch, tmp_path):
    _write_inputs(tmp_path, "old-hash")
    monkeypatch.setattr(sl, "validate_canonical_snapshot", lambda _: {
        "gate_status": "PASS", "run_id": "RUN1", "manifest_sha256": "new-hash", "failure_code": None,
    })
    with pytest.raises(RuntimeError, match="MANIFEST_HASH_MISMATCH"):
        sl.assert_decision_snapshot_current(tmp_path)


def test_fresh_revalidation_failure_blocks_decision(monkeypatch, tmp_path):
    _write_inputs(tmp_path)
    monkeypatch.setattr(sl, "validate_canonical_snapshot", lambda _: {
        "gate_status": "FAIL", "run_id": "RUN1", "manifest_sha256": "abc", "failure_code": "HASH_OR_FILE_INTEGRITY_FAILED",
    })
    with pytest.raises(RuntimeError, match="REVALIDATION_FAILED"):
        sl.assert_decision_snapshot_current(tmp_path)
