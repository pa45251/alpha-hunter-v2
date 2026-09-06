"""Decision entrypoint that injects ephemeral portfolio-maintenance research.

The public decision board is built and written exactly as before.  Only the
in-memory board passed to the existing-position engine receives maintenance
research rows, so private portfolio research cannot leak into public CSVs.
"""
from __future__ import annotations

import json
from pathlib import Path

import decision_run
from existing_position import apply_existing_position_engine as _base_existing_position_engine
from portfolio_maintenance_research import private_board_overlay


def _maintenance_existing_position_engine(board):
    manifest = json.loads(Path("output/manifest.json").read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id", ""))
    private_board, maintenance_meta = private_board_overlay(board, run_id)
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
