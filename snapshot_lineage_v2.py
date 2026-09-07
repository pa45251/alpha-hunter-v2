from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from canonical_gate import validate_canonical_snapshot

CONTRACT = "ALPHA_HUNTER_SNAPSHOT_LINEAGE_V2"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def assert_decision_snapshot_current(out_dir: str | Path = "output") -> dict[str, Any]:
    """Revalidate the canonical snapshot immediately before decisioning.

    A previously persisted PASS gate is evidence about the files that existed when that gate ran,
    not a durable permission token. Decisioning therefore recomputes the deterministic gate and
    requires the persisted gate's manifest digest to match the current manifest digest.
    """
    out = Path(out_dir)
    manifest_path = out / "manifest.json"
    gate_path = out / "gate_report.json"
    if not manifest_path.exists() or not gate_path.exists():
        raise RuntimeError("SNAPSHOT_LINEAGE_INPUT_MISSING")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        persisted = json.loads(gate_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("SNAPSHOT_LINEAGE_INVALID_JSON") from exc

    fresh = validate_canonical_snapshot(out)
    if persisted.get("gate_status") != "PASS":
        raise RuntimeError("SNAPSHOT_LINEAGE_PERSISTED_GATE_NOT_PASS")
    if fresh.get("gate_status") != "PASS":
        raise RuntimeError(f"SNAPSHOT_LINEAGE_REVALIDATION_FAILED:{fresh.get('failure_code')}")

    manifest_run = str(manifest.get("run_id", ""))
    persisted_run = str(persisted.get("run_id", ""))
    fresh_run = str(fresh.get("run_id", ""))
    if not manifest_run or len({manifest_run, persisted_run, fresh_run}) != 1:
        raise RuntimeError("SNAPSHOT_LINEAGE_RUN_ID_MISMATCH")

    persisted_manifest_hash = str(persisted.get("manifest_sha256", ""))
    fresh_manifest_hash = str(fresh.get("manifest_sha256", ""))
    if not persisted_manifest_hash or persisted_manifest_hash != fresh_manifest_hash:
        raise RuntimeError("SNAPSHOT_LINEAGE_MANIFEST_HASH_MISMATCH")

    return {
        "contract": CONTRACT,
        "run_id": manifest_run,
        "manifest_sha256": fresh_manifest_hash,
        "fresh_gate_status": "PASS",
        "persisted_gate_matches_current_files": True,
        "mixed_snapshot_allowed": False,
    }


def build_public_lineage_id(run_id: str, evidence_paths: Iterable[str | Path]) -> tuple[str, dict[str, str]]:
    """Create a public-data lineage id without hashing private portfolio/risk secrets."""
    pieces: list[str] = [str(run_id)]
    hashes: dict[str, str] = {}
    for raw in evidence_paths:
        p = Path(raw)
        if not p.exists() or not p.is_file():
            continue
        digest = _sha256(p)
        hashes[str(p)] = digest
        pieces.append(f"{p}:{digest}")
    lineage_id = hashlib.sha256("\n".join(pieces).encode("utf-8")).hexdigest()
    return lineage_id, hashes
