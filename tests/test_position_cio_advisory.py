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


def test_output_contract_is_alias_only(tmp_path: Path, monkeypatch):
    theme_path = tmp_path / "theme_breadth.csv"
    pd.DataFrame([
        {"theme":"Biotech","above_ma20_pct":1,"above_ma60_pct":1,"positive_rs5_pct":1,"positive_rs20_pct":1,"near_20d_high_pct":1,"breadth_confidence":"HIGH"},
        {"theme":"Genomics","above_ma20_pct":1,"above_ma60_pct":1,"positive_rs5_pct":1,"positive_rs20_pct":1,"near_20d_high_pct":0.5,"breadth_confidence":"LOW"},
    ]).to_csv(theme_path, index=False)
    monkeypatch.setattr(pca, "THEME_PATH", theme_path)
    monkeypatch.setattr(pca, "ALIAS_ACTION_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(pca, "load_risk_policy", lambda: {"max_single_position_pct":65,"max_theme_exposure_pct":70,"max_gross_exposure_pct":216,"max_new_position_pct":3,"min_avg_turnover_twd":1,"max_position_loss_pct":10})
    monkeypatch.setattr(pca, "load_portfolio_state", lambda: {"market_value_twd":1000,"financing_debt_twd":0,"cash_twd":0,"positions":[{"ticker":"00898","market_value_twd":1000,"risk_groups":["BIOTECH_RISK"]}]})
    monkeypatch.setattr(pca, "load_alias_map", lambda portfolio: {"00898":"標的B"})
    payload = pca.build_position_cio_advisory()
    assert payload["positions"][0]["alias"] == "標的B"
    assert payload["positions"][0]["advisory_action"] == "HOLD_BIAS"
    text = json.dumps(payload, ensure_ascii=False)
    assert "00898" not in text
    assert "BIOTECH_RISK" not in text
    assert "Biotech" not in text


def test_residual_is_ignored(tmp_path: Path, monkeypatch):
    theme_path = tmp_path / "theme_breadth.csv"
    pd.DataFrame([{"theme":"Biotech","above_ma20_pct":1,"above_ma60_pct":1,"positive_rs5_pct":1,"positive_rs20_pct":1,"near_20d_high_pct":1,"breadth_confidence":"HIGH"}]).to_csv(theme_path, index=False)
    monkeypatch.setattr(pca, "THEME_PATH", theme_path)
    monkeypatch.setattr(pca, "ALIAS_ACTION_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(pca, "load_risk_policy", lambda: {"max_single_position_pct":65,"max_theme_exposure_pct":70,"max_gross_exposure_pct":216,"max_new_position_pct":3,"min_avg_turnover_twd":1,"max_position_loss_pct":10})
    monkeypatch.setattr(pca, "load_portfolio_state", lambda: {"market_value_twd":1000,"financing_debt_twd":0,"cash_twd":0,"positions":[{"ticker":"006208","market_value_twd":0.5,"risk_groups":["TAIWAN_BROAD"]},{"ticker":"00898","market_value_twd":999.5,"risk_groups":["BIOTECH_RISK"]}]})
    monkeypatch.setattr(pca, "load_alias_map", lambda portfolio: {"006208":"零碎部位","00898":"標的B"})
    payload = pca.build_position_cio_advisory()
    assert payload["positions"][0]["advisory_action"] == "IGNORE_RESIDUAL"
