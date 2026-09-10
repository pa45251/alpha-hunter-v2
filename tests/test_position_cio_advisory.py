import hashlib
import json
from pathlib import Path

import pandas as pd

import position_cio_advisory as pca


def test_theme_score_and_classification():
    row = pd.Series({
        "above_ma20_pct": 1.0,
        "above_ma60_pct": 1.0,
        "positive_rs20_pct": 1.0,
        "positive_rs5_pct": 1.0,
        "near_20d_high_pct": 1.0,
    })
    assert pca._theme_score(row) == 1.0
    assert pca._classify(0.8) == "STRONG"
    assert pca._classify(0.6) == "POSITIVE"
    assert pca._classify(0.45) == "MIXED"
    assert pca._classify(0.2) == "WEAK"


def test_private_risk_groups_map_to_expected_public_themes_without_ticker_map():
    pos = {"risk_groups": ["BIOTECH_RISK"]}
    assert pca._theme_keys(pos) == ["Biotech", "Genomics"]
    assert all("00757" not in str(v) and "00898" not in str(v) for v in pca.RISK_GROUP_THEME_MAP.values())


def test_taiwan_etf_detection():
    assert pca._is_taiwan_etf("00757")
    assert pca._is_taiwan_etf("009821.TW")
    assert not pca._is_taiwan_etf("3029")


def test_actual_position_trend_is_not_theme_breadth():
    idx = pd.date_range("2026-01-01", periods=90, freq="B")
    up = pd.Series([100 + i for i in range(90)], index=idx)
    down = pd.Series([190 - i for i in range(90)], index=idx)
    assert pca._classify_position_trend_from_close(up)["state"] == "UPTREND"
    assert pca._classify_position_trend_from_close(down)["state"] == "DOWNTREND_OR_BROKEN"


def _write_regime(tmp_path: Path, rate_pressure: str = "SUPPORTIVE", regime: str = "NORMAL", run_id: str = "RUN1") -> Path:
    path = tmp_path / "risk_regime.json"
    path.write_text(json.dumps({"status":"READY","regime":regime,"source_run_id":run_id,"signals":{"rate_pressure":rate_pressure}}), encoding="utf-8")
    return path


def _write_manifest(tmp_path: Path, theme_path: Path, run_id: str = "RUN1") -> Path:
    digest = hashlib.sha256(theme_path.read_bytes()).hexdigest()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({
        "status":"PASS",
        "run_id":run_id,
        "authoritative_files":[{"relative_path":"output/theme_breadth.csv","sha256":digest}],
    }), encoding="utf-8")
    return path


def _patch_common(tmp_path: Path, monkeypatch, rate_pressure: str = "SUPPORTIVE", trend_state: str = "UPTREND", risk_group: str = "BIOTECH_RISK"):
    theme_path = tmp_path / "theme_breadth.csv"
    pd.DataFrame([
        {"theme":"Biotech","above_ma20_pct":1,"above_ma60_pct":1,"positive_rs5_pct":1,"positive_rs20_pct":1,"near_20d_high_pct":1,"breadth_confidence":"HIGH"},
        {"theme":"Genomics","above_ma20_pct":1,"above_ma60_pct":1,"positive_rs5_pct":1,"positive_rs20_pct":1,"near_20d_high_pct":0.5,"breadth_confidence":"LOW"},
        {"theme":"Copper","above_ma20_pct":1,"above_ma60_pct":1,"positive_rs5_pct":1,"positive_rs20_pct":1,"near_20d_high_pct":1,"breadth_confidence":"HIGH"},
        {"theme":"Uranium","above_ma20_pct":1,"above_ma60_pct":1,"positive_rs5_pct":1,"positive_rs20_pct":1,"near_20d_high_pct":1,"breadth_confidence":"HIGH"},
        {"theme":"Energy","above_ma20_pct":1,"above_ma60_pct":1,"positive_rs5_pct":1,"positive_rs20_pct":1,"near_20d_high_pct":1,"breadth_confidence":"HIGH"},
    ]).to_csv(theme_path, index=False)
    monkeypatch.setattr(pca, "THEME_PATH", theme_path)
    monkeypatch.setattr(pca, "MANIFEST_PATH", _write_manifest(tmp_path, theme_path))
    monkeypatch.setattr(pca, "REGIME_PATH", _write_regime(tmp_path, rate_pressure=rate_pressure))
    monkeypatch.setattr(pca, "ALIAS_ACTION_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(pca, "load_risk_policy", lambda: {"max_single_position_pct":65,"max_theme_exposure_pct":70,"max_gross_exposure_pct":216,"max_new_position_pct":3,"min_avg_turnover_twd":1,"max_position_loss_pct":10})
    monkeypatch.setattr(pca, "load_portfolio_state", lambda: {"market_value_twd":1000,"financing_debt_twd":0,"cash_twd":0,"positions":[{"ticker":"00898","market_value_twd":1000,"risk_groups":[risk_group]}]})
    monkeypatch.setattr(pca, "load_alias_map", lambda portfolio: {"00898":"標的B"})
    monkeypatch.setattr(pca, "_position_trend", lambda ticker: {"state":trend_state,"score":1.0 if trend_state == "UPTREND" else 0.0,"as_of":"2026-09-10"})


def test_output_contract_is_alias_only_and_supportive_macro_holds(tmp_path: Path, monkeypatch):
    _patch_common(tmp_path, monkeypatch, rate_pressure="SUPPORTIVE")
    payload = pca.build_position_cio_advisory()
    row = payload["positions"][0]
    assert payload["source_run_id"] == "RUN1"
    assert row["alias"] == "標的B"
    assert row["trend_state"] == "UPTREND"
    assert row["macro_support"] == "SUPPORTIVE"
    assert row["advisory_action"] == "HOLD_BIAS"
    text = json.dumps(payload, ensure_ascii=False)
    assert "00898" not in text
    assert "BIOTECH_RISK" not in text
    assert "Biotech" not in text


def test_strong_theme_cannot_override_actual_broken_position_trend(tmp_path: Path, monkeypatch):
    _patch_common(tmp_path, monkeypatch, rate_pressure="ADVERSE", trend_state="DOWNTREND_OR_BROKEN")
    payload = pca.build_position_cio_advisory()
    row = payload["positions"][0]
    assert row["signal_state"] == "STRONG"
    assert row["trend_state"] == "DOWNTREND_OR_BROKEN"
    assert row["macro_support"] == "ADVERSE"
    assert row["advisory_action"] == "REDUCE_BIAS"


def test_rate_sensitive_position_is_not_dip_bought_when_yields_adverse(tmp_path: Path, monkeypatch):
    _patch_common(tmp_path, monkeypatch, rate_pressure="ADVERSE")
    payload = pca.build_position_cio_advisory()
    row = payload["positions"][0]
    assert row["trend_state"] == "UPTREND"
    assert row["macro_support"] == "ADVERSE"
    assert row["advisory_action"] == "REVIEW_HOLD"


def test_critical_materials_do_not_get_false_supportive_macro_under_adverse_rates(tmp_path: Path, monkeypatch):
    _patch_common(tmp_path, monkeypatch, rate_pressure="ADVERSE", trend_state="DOWNTREND_OR_BROKEN", risk_group="CRITICAL_MATERIALS")
    payload = pca.build_position_cio_advisory()
    row = payload["positions"][0]
    assert row["macro_support"] == "CONDITIONAL"
    assert row["advisory_action"] == "REDUCE_BIAS"


def test_lineage_mismatch_is_blocked(tmp_path: Path, monkeypatch):
    _patch_common(tmp_path, monkeypatch)
    bad = tmp_path / "risk_regime.json"
    bad.write_text(json.dumps({"status":"READY","regime":"NORMAL","source_run_id":"OTHER","signals":{"rate_pressure":"SUPPORTIVE"}}), encoding="utf-8")
    monkeypatch.setattr(pca, "REGIME_PATH", bad)
    try:
        pca.build_position_cio_advisory()
    except RuntimeError as exc:
        assert "LINEAGE_MISMATCH" in str(exc)
    else:
        raise AssertionError("lineage mismatch must fail closed")


def test_residual_is_ignored(tmp_path: Path, monkeypatch):
    _patch_common(tmp_path, monkeypatch)
    monkeypatch.setattr(pca, "load_portfolio_state", lambda: {"market_value_twd":1000,"financing_debt_twd":0,"cash_twd":0,"positions":[{"ticker":"006208","market_value_twd":0.5,"risk_groups":["TAIWAN_BROAD"]},{"ticker":"00898","market_value_twd":999.5,"risk_groups":["BIOTECH_RISK"]}]})
    monkeypatch.setattr(pca, "load_alias_map", lambda portfolio: {"006208":"零碎部位","00898":"標的B"})
    payload = pca.build_position_cio_advisory()
    assert payload["positions"][0]["advisory_action"] == "IGNORE_RESIDUAL"
