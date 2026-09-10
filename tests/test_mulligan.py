"""Mulligan rule engine: features, logic, scoring, profiles."""

from __future__ import annotations

import pytest

from cyberpunk_deck_math.models import Card
from cyberpunk_deck_math.probability.mulligan import (
    And,
    Condition,
    HandContext,
    MulliganPolicy,
    Not,
    Or,
    ScoreConfig,
    builtin_policies,
    hand_features,
    load_policies,
    parse_node,
    score_policy,
)

JACKIE = "Jackie Welles — Ride or Die Choom"


def card(name, cost=2, sellable=True, tags=()):
    return Card(card_id=name, name=name, cost=cost, sellable=sellable, tags=list(tags))


@pytest.fixture()
def context():
    return HandContext(target_names=(JACKIE,))


def test_features_count_sellables_and_targets(context):
    hand = [card("A"), card("B"), card(JACKIE, cost=6, sellable=False)]
    features = hand_features(hand, context)
    assert features["sellables"] == 2
    assert features["target"] == 1
    assert features["hand_size"] == 3
    assert features["sellable_pct"] == pytest.approx(2 / 3)


def test_features_count_draw_sources(context):
    hand = [card("Drawer", tags=["draw"]), card("Plain")]
    assert hand_features(hand, context)["draw_sources"] == 1


def test_effect_metadata_marks_draw_sources(context):
    drawer = card("Effecty")
    drawer.effect_metadata = [{"trigger": "on_play", "effect": "draw", "amount": 1}]
    assert hand_features([drawer], context)["draw_sources"] == 1


def test_expensive_card_feature(context):
    hand = [card("X", cost=4), card("Y", cost=5), card("Z", cost=1)]
    assert hand_features(hand, context)["cards_cost_4_plus"] == 2


def test_and_or_not_logic():
    features = {"sellables": 2.0, "target": 0.0}
    a = Condition("sellables", ">=", 2)
    b = Condition("target", ">=", 1)
    assert And([a, b]).evaluate(features) is False
    assert Or([a, b]).evaluate(features) is True
    assert Not(b).evaluate(features) is True


def test_nested_expression_parsing():
    node = parse_node(
        {
            "all": [
                {"feature": "sellables", "operator": ">=", "value": 2},
                {
                    "any": [
                        {"feature": "target", "operator": ">=", "value": 1},
                        {"feature": "early_draw_sources", "operator": ">=", "value": 1},
                    ]
                },
            ]
        }
    )
    assert node.evaluate({"sellables": 2, "target": 0, "early_draw_sources": 1}) is True
    assert node.evaluate({"sellables": 1, "target": 1, "early_draw_sources": 1}) is False
    assert "AND" in node.describe() and "OR" in node.describe()


def test_unknown_feature_rejected():
    with pytest.raises(ValueError):
        Condition("not_a_feature", ">=", 1)


def test_policy_round_trips_through_json():
    policy = builtin_policies()["Balanced"]
    again = MulliganPolicy.from_dict(policy.to_dict())
    features = {
        "sellables": 2, "target": 1, "early_draw_sources": 0, "early_playables": 0,
    }
    assert again.should_keep(features) == policy.should_keep(features)


def test_mulligan_if_no_draw_card(context):
    policy = builtin_policies()["Draw Engine Priority"]
    no_draw = [card("A"), card("B")]
    with_draw = [card("A"), card("Drawer", tags=["draw"])]
    assert policy.decide(no_draw, context) is False  # mulligan
    assert policy.decide(with_draw, context) is True


def test_mulligan_if_no_target(context):
    policy = builtin_policies()["Target Only"]
    assert policy.decide([card("A")], context) is False
    assert policy.decide([card(JACKIE, sellable=False)], context) is True


def test_minimum_sellables_condition(context):
    policy = builtin_policies()["2+ Sellables"]
    assert policy.decide([card("A"), card("B", sellable=False)], context) is False
    assert policy.decide([card("A"), card("B")], context) is True


def test_low_curve_policy_mulligans_clogged_hands(context):
    policy = builtin_policies()["Low Curve"]
    clogged = [card("A", cost=4), card("B", cost=5), card("C", cost=6)]
    assert policy.decide(clogged, context) is False
    assert policy.decide([card("A", cost=1)], context) is True


def test_score_based_policy(context):
    config = ScoreConfig.from_dict(
        {
            "card_scores": {JACKIE: 3.0},
            "sellable_score": 1.0,
            "interactions": [
                {"when": {"feature": "sellables", "operator": ">=", "value": 2}, "points": 2}
            ],
        }
    )
    policy = score_policy("threshold 6", 6, config)
    strong = [card("A"), card("B"), card(JACKIE, sellable=False)]
    weak = [card("A", sellable=False), card("B", sellable=False)]
    assert policy.decide(strong, context) is True
    assert policy.decide(weak, context) is False


def test_score_interaction_penalty(context):
    config = ScoreConfig(
        sellable_score=1.0,
        interactions=[{"when": {"feature": "sellables", "operator": "==", "value": 0}, "points": -3}],
    )
    features = hand_features(
        [card("A", sellable=False)], HandContext(target_names=(JACKIE,), score_config=config)
    )
    assert features["score"] == -3.0


def test_score_config_normalizes_card_names():
    config = ScoreConfig.from_dict({"card_scores": {JACKIE: 3}})
    assert config.card_scores["jackie welles ride or die choom"] == 3.0


def test_saved_profiles_load_from_disk():
    policies = load_policies(["profiles/mulligan"])
    assert "Jackie or Draw" in policies
    assert "Jackie Score Based" in policies
    assert policies["Jackie Score Based"].score_config is not None


def test_no_mulligan_policy_always_keeps(context):
    assert builtin_policies()["No Mulligan"].decide([card("A", sellable=False)], context) is True


def test_policy_describe_is_readable():
    text = builtin_policies()["Target or Draw"].describe()
    assert text.startswith("KEEP IF")
    assert "OR" in text
