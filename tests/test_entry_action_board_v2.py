from entry_action_board_v2 import START, END, build_block, inject_block


def _alignment():
    return {"top_aligned": [{
        "ticker": "2606.TW", "name": "裕民", "alignment_score": 0.9,
        "international_theme": "Shipping", "reaction_state": "PERSISTENT", "alignment_action": "HOLD_DONT_CHASE",
    }]}


def _entries():
    return {
        "fresh": [{
            "ticker": "2317.TW", "name": "鴻海", "entry_structure_valid": True,
            "global_alignment_score": 0.75, "current_action": "WAIT_BREAKOUT",
            "entry_status": "WAITING_FOR_TRIGGER", "entry_style": "FRESH_BREAKOUT",
            "trigger_price": 200, "buy_zone_low": 200, "buy_zone_high": 205,
            "invalidation_price": 190, "why_now": "", "why_not_now": "WAIT",
        }],
        "pullback": [], "continuation": [],
    }


def test_action_board_has_a_through_e_and_exact_levels():
    block = build_block(_alignment(), _entries(), {"rotations": []})
    for label in ["A. Strongest", "B. Best Fresh", "C. Best Pullback", "D. Best Continuation", "E. Rotation"]:
        assert label in block
    assert "200" in block and "205" in block and "190" in block


def test_inject_is_idempotent_not_duplicate():
    old = "# Alpha Hunter — Action Board\n\nlegacy"
    block = build_block(_alignment(), _entries(), {"rotations": []})
    once = inject_block(old, block)
    twice = inject_block(once, block)
    assert twice.count(START) == 1
    assert twice.count(END) == 1


def test_invalid_watchlist_is_not_presented_as_best_entry():
    invalid = {"ticker":"INVALID", "entry_structure_valid":False,
               "current_action":"PREPARE", "entry_status":"WATCHLIST"}
    block = build_block({"top_aligned":[]}, {"fresh":[invalid], "pullback":[invalid], "continuation":[invalid]}, {"rotations":[]})
    assert "INVALID" not in block
    assert block.count("no candidate currently has a valid canonical V2 plan") == 3
