"""Integrity guard for the accepted Alpha Hunter V2 prospective baseline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REGISTRY = Path("config/frozen_strategy_v2.json")
CONTRACT = "ALPHA_HUNTER_V2_FREEZE_GUARD"


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def evaluate_v2_freeze(root: Path = ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    changed: list[str] = []
    missing: list[str] = []
    try:
        registry = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    except Exception:
        return {
            "contract": CONTRACT,
            "integrity_pass": False,
            "strategy_version": "UNKNOWN",
            "baseline_commit": None,
            "blockers": ["V2_FREEZE_REGISTRY_INVALID"],
            "changed_files": [],
            "missing_files": [],
        }

    if registry.get("hash_algorithm") != "git_blob_sha1":
        blockers.append("V2_FREEZE_HASH_ALGORITHM_INVALID")
    hashes = registry.get("file_hashes") or {}
    if not isinstance(hashes, dict) or not hashes:
        blockers.append("V2_FROZEN_RULES_MISSING")
        hashes = {}

    for name, expected in hashes.items():
        path = root / str(name)
        if not path.is_file():
            missing.append(str(name))
            continue
        if git_blob_sha1(path) != str(expected):
            changed.append(str(name))

    if missing:
        blockers.append("V2_FROZEN_FILES_MISSING")
    if changed:
        blockers.append("V2_FROZEN_RULES_CHANGED_NEW_VERSION_REQUIRED")

    return {
        "contract": CONTRACT,
        "integrity_pass": not blockers,
        "strategy_version": registry.get("strategy_version", "UNKNOWN"),
        "baseline_commit": registry.get("baseline_commit"),
        "baseline_run_id": registry.get("baseline_run_id"),
        "baseline_closed_price_date": registry.get("baseline_closed_price_date"),
        "deployment_mode": registry.get("deployment_mode"),
        "live_execution_authorized": False,
        "frozen_file_count": len(hashes),
        "blockers": blockers,
        "changed_files": changed,
        "missing_files": missing,
        "threshold_tuning_before_acceptance_review": False,
    }


def main() -> None:
    result = evaluate_v2_freeze()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["integrity_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
