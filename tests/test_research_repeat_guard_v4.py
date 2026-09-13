from __future__ import annotations

from research_repeat_guard_v4 import filter_repeats


def _handoff():
    return {
        "company_research_targets": [
            {
                "ticker": "1111.TW",
                "driver_id": "DRIVER_A",
                "thesis_id": "thesis-a",
                "research_question": "Is A active?",
                "missing_gate": "CAUSAL_UNVERIFIED",
                "reaction_state": "PERSISTENT",
                "international_price_state": "DEVELOPING",
                "entry_research_ready": True,
            },
            {
                "ticker": "2222.TW",
                "driver_id": "DRIVER_A",
                "thesis_id": "thesis-b",
                "research_question": "Is A active for B?",
                "missing_gate": "CAUSAL_UNVERIFIED",
                "reaction_state": "PERSISTENT",
                "international_price_state": "DEVELOPING",
                "entry_research_ready": True,
            },
        ],
        "research_targets": [{"driver_id": "DRIVER_A"}],
    }


def _prefetch(extra_url=None):
    sources = [{"source_url": "https://example.com/a"}]
    if extra_url:
        sources.append({"source_url": extra_url})
    return {
        "company_targets": [
            {"ticker": "1111.TW", "driver_id": "DRIVER_A", "candidate_sources": []},
            {"ticker": "2222.TW", "driver_id": "DRIVER_A", "candidate_sources": []},
        ],
        "targets": [{"driver_id": "DRIVER_A", "candidate_sources": sources}],
    }


def _signature(question, urls):
    return {
        "question": question,
        "urls": sorted(urls),
        "wake": ["PERSISTENT", "DEVELOPING", True],
    }


def test_same_unresolved_question_and_sources_is_skipped():
    previous = {
        "items": [{
            "thesis_id": "thesis-a",
            "outcome": "UNRESOLVED",
            "signature": _signature("Is A active?", ["https://example.com/a"]),
        }]
    }
    filtered, skipped = filter_repeats(_handoff(), _prefetch(), previous)
    assert [x["thesis_id"] for x in filtered["company_research_targets"]] == ["thesis-b"]
    assert skipped[0]["thesis_id"] == "thesis-a"
    assert len(filtered["research_targets"]) == 1


def test_new_source_wakes_previously_unresolved_question():
    previous = {
        "items": [{
            "thesis_id": "thesis-a",
            "outcome": "UNRESOLVED",
            "signature": _signature("Is A active?", ["https://example.com/a"]),
        }]
    }
    filtered, skipped = filter_repeats(_handoff(), _prefetch("https://example.com/new"), previous)
    assert len(filtered["company_research_targets"]) == 2
    assert skipped == []


def test_resolved_previous_item_is_not_silently_skipped_as_unknown():
    previous = {
        "items": [{
            "thesis_id": "thesis-a",
            "outcome": "RESOLVED",
            "signature": _signature("Is A active?", ["https://example.com/a"]),
        }]
    }
    filtered, skipped = filter_repeats(_handoff(), _prefetch(), previous)
    assert len(filtered["company_research_targets"]) == 2
    assert skipped == []
