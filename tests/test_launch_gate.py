import json
from pathlib import Path
import shutil

import pandas as pd
import pytest

from launch_gate import ROOT, apply_launch_gate, evaluate_launch, proposed_pilot_size
from shadow_audit import append_shadow_audit, seal_public_snapshot


def test_buy_never_grants_live_permission():
    b, meta = apply_launch_gate(pd.DataFrame([{"portfolio_action": "BUY_STOCK", "auto_trade_allowed": True}]))
    assert b.iloc[0]["portfolio_action"] == "BUY_STOCK"
    assert b.iloc[0]["execution_action"] == "NO_LIVE_ORDER"
    assert not b.iloc[0]["live_execution_authorized"]
    assert not meta["live_execution_authorized"]
    assert meta["freeze_integrity_pass"]


def test_invalid_config_blocks_instead_of_defaulting_to_live(tmp_path):
    assert not evaluate_launch(tmp_path)["freeze_integrity_pass"]
    assert not evaluate_launch(tmp_path)["live_execution_authorized"]


def test_frozen_rule_edit_blocks_promotion(tmp_path):
    frozen = json.loads((ROOT / "config/frozen_strategy_v1.json").read_text())
    for name in [*frozen["file_hashes"], "config/frozen_strategy_v1.json"]:
        dest = tmp_path / name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    assert evaluate_launch(tmp_path)["freeze_integrity_pass"]
    p = tmp_path / "config/launch_policy.json"
    data = json.loads(p.read_text()); data["mode"] = "LIVE"; p.write_text(json.dumps(data))
    report = evaluate_launch(tmp_path)
    assert not report["freeze_integrity_pass"]
    assert not report["live_execution_authorized"]


def size(**overrides):
    args = dict(net_equity=1_000_000, initial_net_equity=1_000_000, stop_distance_pct=5,
                current_pilot_value=0, open_planned_loss=0, cumulative_pilot_pnl=0, inputs_valid=True)
    args.update(overrides)
    return proposed_pilot_size(**args)


def test_position_size_respects_each_budget():
    assert size()["proposed_value"] == 20_000
    assert size(current_pilot_value=45_000)["proposed_value"] == 5_000
    assert size(open_planned_loss=2_250)["proposed_value"] == 5_000
    assert not size()["live_execution_authorized"]


@pytest.mark.parametrize("overrides", [{"leveraged": True}, {"inputs_valid": False},
    {"stop_distance_pct": 0}, {"net_equity": float("nan")}, {"cumulative_pilot_pnl": -5_000},
    {"open_planned_loss": 2_500}, {"current_pilot_value": 50_000}])
def test_sizing_blocks_invalid_or_exhausted_budget(overrides):
    assert size(**overrides)["proposed_value"] == 0


def test_audit_rerun_preserves_first_timestamp(tmp_path):
    b = pd.DataFrame([{"run_id": "R", "ticker": "X", "driver_id": "D", "strategy_version": "V1"}])
    path = str(tmp_path / "audit.csv")
    first = append_shadow_audit(b, path)
    second = append_shadow_audit(b, path)
    assert len(second) == 1
    assert first.iloc[0]["audit_at_utc"] == second.iloc[0]["audit_at_utc"]


def test_evidence_seal_is_idempotent_and_drops_private_columns(tmp_path):
    p = tmp_path / "journal.jsonl"
    board = pd.DataFrame([{"ticker": "PUBLIC", "driver_id": "D", "private_balance": "SECRET"}])
    args = (board, "R", {"strategy_version": "V1"}, [])
    first = seal_public_snapshot(*args, path=p)
    before = p.read_text()
    assert seal_public_snapshot(*args, path=p) == first
    assert p.read_text() == before
    assert "SECRET" not in before
