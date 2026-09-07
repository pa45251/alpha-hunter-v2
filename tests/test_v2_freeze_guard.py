import json
import shutil
from pathlib import Path

from v2_freeze_guard import ROOT, evaluate_v2_freeze


def test_current_v2_frozen_baseline_integrity_passes():
    result = evaluate_v2_freeze(ROOT)
    assert result["integrity_pass"]
    assert result["strategy_version"] == "ALPHA_HUNTER_ADVISORY_V2_FROZEN"
    assert result["baseline_commit"] == "33b7d5e310f12d4e3d854c73515572e576e44d5c"
    assert result["baseline_closed_price_date"] == "2026-09-04"
    assert result["live_execution_authorized"] is False
    assert result["threshold_tuning_before_acceptance_review"] is False


def test_mutating_any_frozen_v2_file_requires_new_version(tmp_path: Path):
    registry = json.loads((ROOT / "config/frozen_strategy_v2.json").read_text(encoding="utf-8"))
    for name in registry["file_hashes"]:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    reg_dest = tmp_path / "config/frozen_strategy_v2.json"
    reg_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "config/frozen_strategy_v2.json", reg_dest)

    target = tmp_path / "entry_structure_v2.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# unauthorized drift\n", encoding="utf-8")

    result = evaluate_v2_freeze(tmp_path)
    assert not result["integrity_pass"]
    assert "entry_structure_v2.py" in result["changed_files"]
    assert "V2_FROZEN_RULES_CHANGED_NEW_VERSION_REQUIRED" in result["blockers"]
