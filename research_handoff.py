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
EXPECTED_BRANCH = "main"
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


if __name__ == "__main__":
    result = build_research_handoff("output")
    print(json.dumps(result, ensure_ascii=False, indent=2))
