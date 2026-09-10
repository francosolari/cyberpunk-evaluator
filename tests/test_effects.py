"""Generic effect metadata, conditions, and the interpretation workflow."""

from __future__ import annotations

import pytest

from cyberpunk_deck_math.effects import interpreter
from cyberpunk_deck_math.effects.conditions import evaluate_all, evaluate_condition
from cyberpunk_deck_math.effects.generic import Effect, apply_effect, card_effects
from cyberpunk_deck_math.models import Card


def test_effect_validation():
    with pytest.raises(ValueError):
        Effect(trigger="not_a_trigger", effect="draw")
    with pytest.raises(ValueError):
        Effect(trigger="on_play", effect="teleport")
    with pytest.raises(ValueError):
        Effect(trigger="on_play", effect="draw", conditions=[{"type": "vibes", "value": 1}])


def test_street_cred_parity_condition():
    condition = {"type": "street_cred_parity", "value": "even"}
    assert evaluate_condition(condition, {"street_cred": 4}) is True
    assert evaluate_condition(condition, {"street_cred": 3}) is False


def test_unknown_context_returns_none_not_true():
    condition = {"type": "distinct_gigs", "operator": ">=", "value": 3}
    assert evaluate_condition(condition, {}) is None
    assert evaluate_all([condition], {}) is None
    assert evaluate_all([condition], {}, unknown_is=False) is False


def test_numeric_operators():
    condition = {"type": "distinct_gigs", "operator": ">=", "value": 3}
    assert evaluate_condition(condition, {"distinct_gigs": 3}) is True
    assert evaluate_condition(condition, {"distinct_gigs": 2}) is False


def test_card_type_in_play_uses_membership():
    condition = {"type": "card_type_in_play", "value": "gear"}
    assert evaluate_condition(condition, {"card_types_in_play": ["gear", "unit"]}) is True
    assert evaluate_condition(condition, {"card_types_in_play": ["unit"]}) is False


def test_opponent_proxy_requires_resolution():
    condition = {"type": "opponent_state_proxy", "value": "valid_target"}
    assert evaluate_condition(condition, {"opponent_state_proxy": {"valid_target": True}}) is True
    unresolved = {"opponent_state_proxy": {"valid_target": 0.2}}
    assert evaluate_condition(condition, unresolved) is None


def test_effect_cache_returns_same_parse():
    card = Card(card_id="c", name="C", effect_metadata=[
        {"trigger": "on_play", "effect": "draw", "amount": 2}
    ])
    first = card_effects(card, "on_play")
    second = card_effects(card, "on_play")
    assert first is second
    assert card_effects(card, "on_call") == []


def test_apply_draw_effect_moves_cards(rules):
    import random

    from cyberpunk_deck_math.simulation.state import GameState

    state = GameState(rules=rules, rng=random.Random(1),
                      deck=[Card(card_id=str(i), name=f"c{i}") for i in range(5)])
    effect = Effect("on_play", "draw", 2, source_card="Source")
    record = apply_effect(effect, state, state.context())
    assert record["applied"] == 2
    assert len(state.hand) == 2
    assert state.draws_by_source["Source"] == 2


def test_conditional_effect_does_not_fire_when_unknown(rules):
    import random

    from cyberpunk_deck_math.simulation.state import GameState

    state = GameState(rules=rules, rng=random.Random(1),
                      deck=[Card(card_id="1", name="c")])
    effect = Effect("on_play", "draw", 1,
                    conditions=[{"type": "opponent_state_proxy", "value": "valid_target"}])
    record = apply_effect(effect, state, {})
    assert record["applied"] == 0


def test_gain_resource_effect(rules):
    import random

    from cyberpunk_deck_math.simulation.state import GameState

    state = GameState(rules=rules, rng=random.Random(1))
    apply_effect(Effect("on_call", "gain_resource", 2), state, {})
    assert state.eddies == 2 and state.ready_eddies == 2


def test_unmodelled_effects_are_flagged(rules):
    import random

    from cyberpunk_deck_math.simulation.state import GameState

    state = GameState(rules=rules, rng=random.Random(1))
    record = apply_effect(Effect("on_play", "search", 1), state, {})
    assert record["unmodelled"] is True


def test_human_interpretation_is_authoritative():
    card = Card(card_id="x", name="X", rules_text="Draw 1.")
    interpreter.set_human_interpretation(card, [{"trigger": "on_play", "effect": "draw", "amount": 1}])
    assert card.interpretation_status == "human_verified"
    assert card.rules_text == "Draw 1."  # official text preserved


def test_llm_proposal_is_not_authoritative():
    card = Card(card_id="x", name="X", rules_text="Draw 1.")
    interpreter.attach_proposal(
        card,
        {
            "effects": [{"trigger": "on_play", "effect": "draw", "amount": 1}],
            "confidence": "medium",
            "rationale": "the text says draw 1",
            "unrepresentable": ["something odd"],
        },
    )
    assert card.interpretation_status == "llm_proposed"
    assert "unrepresentable" in card.interpretation_notes
    interpreter.verify_interpretation(card, "tester")
    assert card.interpretation_status == "human_verified"


def test_verify_requires_an_interpretation():
    with pytest.raises(ValueError):
        interpreter.verify_interpretation(Card(card_id="x", name="X"))


def test_proposal_requires_rules_text():
    with pytest.raises(ValueError):
        interpreter.propose_interpretation(Card(card_id="x", name="X"))


def test_invalid_proposal_metadata_rejected():
    with pytest.raises(ValueError):
        interpreter.attach_proposal(
            Card(card_id="x", name="X"),
            {"effects": [{"trigger": "on_play", "effect": "explode"}]},
        )


def test_interpretation_report_groups_by_status(database):
    report = interpreter.interpretation_report(list(database)[:5])
    assert set(report) == {"raw", "llm_proposed", "human_verified"}
