"""Decision entrypoint that injects ephemeral portfolio-maintenance research.

The public decision board is built and written exactly as before. Only the
in-memory board passed to the existing-position engine receives maintenance
research rows, so private portfolio research cannot leak into public CSVs.
"""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path

import decision_run
from existing_position import apply_existing_position_engine as _base_existing_position_engine
from portfolio_maintenance_research import private_board_overlay


def _aggregate_private_states(run_id: str) -> dict[str, int]:
    """Expose counts only; never driver ids or position associations."""
    path = Path(os.getenv("ALPHA_HUNTER_MAINTENANCE_RESEARCH_PATH", "/tmp/portfolio_maintenance_result.json"))
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if str(payload.get("research_run_id", "")) != str(run_id):
        return {}
    counts = Counter(str(r.get("state", "UNKNOWN")).upper() for r in (payload.get("results") or []) if isinstance(r, dict))
    return {k: int(v) for k, v in counts.items() if k in {"ACTIVE", "INACTIVE", "UNKNOWN"}}


def _maintenance_existing_position_engine(board):
    manifest = json.loads(Path("output/manifest.json").read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id", ""))
    private_board, maintenance_meta = private_board_overlay(board, run_id)
    maintenance_meta = dict(maintenance_meta or {})
    maintenance_meta["maintenance_state_counts"] = _aggregate_private_states(run_id)
    actions, position_meta = _base_existing_position_engine(private_board)
    position_meta = dict(position_meta or {})
    position_meta["maintenance_research"] = maintenance_meta
    return actions, position_meta


def main() -> None:
    # decision_run imported the function directly; replace that local binding only
    # for this process. No public board writer is changed.
    decision_run.apply_existing_position_engine = _maintenance_existing_position_engine
    decision_run.main()


if __name__ == "__main__":
    main()
