import pandas as pd

from reverse_discovery import (
    ReverseDiscoveryConfig,
    UNMAPPED_DRIVER_ID,
    build_reverse_candidates,
    build_reverse_driver_queue,
)


def _taiwan_unmapped_universe(n: int = 100) -> pd.DataFrame:
    rows = []
    for i in range(n):
        score = (i + 1) / n
        rows.append({
            "code": f"{5000 + i}",
            "ticker": f"{5000 + i}.TW",
            "name": f"NewTheme{i}",
            "industry": "新題材",
            "taiwan_candidate_score_v1": score,
            "taiwan_early_score_v2": score,
            "rs_20d_vs_bench": score - 0.5,
            "acceleration": score,
            "bias20": 0.01 + 0.001 * i,
            "reaction_state": "PRE_CONFIRMATION" if i == n - 1 else "UNKNOWN",
            "last_price_date": "2026-09-11",
        })
    return pd.DataFrame(rows)


def test_strong_unmapped_anomaly_is_preserved_as_why_research():
    candidates = build_reverse_candidates(
        _taiwan_unmapped_universe(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        ReverseDiscoveryConfig(unmapped_anomaly_percentile_gate=0.985),
    )
    assert not candidates.empty
    assert set(candidates["driver_id"]) == {UNMAPPED_DRIVER_ID}
    row = candidates.iloc[0]
    assert row["pricing_state"] == "UNMAPPED_WHY"
    assert row["activation_state"] == "RESEARCH_WHY_REQUIRED"
    assert bool(row["price_cannot_activate_driver"])
    assert not bool(row["decision_eligible"])


def test_unmapped_anomaly_never_enters_canonical_driver_activation_queue():
    candidates = build_reverse_candidates(
        _taiwan_unmapped_universe(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        ReverseDiscoveryConfig(unmapped_anomaly_percentile_gate=0.985),
    )
    queue = build_reverse_driver_queue(candidates, pd.DataFrame())
    assert queue.empty
