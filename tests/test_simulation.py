"""Simulation: determinism, resources, Legends, gigs, and agreement with exact math."""

from __future__ import annotations

import random
from math import isclose, sqrt

import pytest

from cyberpunk_deck_math.models import Card, Deck, DeckEntry, PlayabilityProfile
from cyberpunk_deck_math.probability import hypergeom, sells
from cyberpunk_deck_math.probability.mulligan import builtin_policies
from cyberpunk_deck_math.simulation.board_proxy import BoardProxy
from cyberpunk_deck_math.simulation.game import proportion_result, resource_threshold_rate, simulate
from cyberpunk_deck_math.simulation.gigs import GigDistribution
from cyberpunk_deck_math.simulation.legends import call_legend, setup_legends
from cyberpunk_deck_math.simulation.pilot import PilotPolicy
from cyberpunk_deck_math.simulation.state import GameState

TARGET = "Jackie Welles — Ride or Die Choom"


def within_ci(observed, expected, n, sigmas=4.0):
    se = sqrt(max(expected * (1 - expected), 1e-9) / n)
    return abs(observed - expected) <= sigmas * se


def test_simulation_is_deterministic(deck, profile):
    policy = PilotPolicy(target_names=(TARGET,), profile=profile)
    a = simulate(deck, policy, iterations=800, seed=7, max_turn=3)
    b = simulate(deck, policy, iterations=800, seed=7, max_turn=3)
    assert a.counts == b.counts
    assert a.totals == b.totals


def test_different_seeds_differ(deck, profile):
    policy = PilotPolicy(target_names=(TARGET,), profile=profile)
    a = simulate(deck, policy, iterations=800, seed=1, max_turn=3)
    b = simulate(deck, policy, iterations=800, seed=2, max_turn=3)
    assert a.counts != b.counts


def test_simulated_target_access_matches_hypergeometric(deck, flat_profile):
    """With no mulligan, P(target seen by T3) must match the exact value."""
    policy = PilotPolicy(target_names=(TARGET,), profile=flat_profile, mulligan=None)
    n = 20_000
    summary = simulate(deck, policy, iterations=n, seed=11, max_turn=3)
    observed = summary.counts["target_seen"][2] / n
    expected = hypergeom.at_least(deck.size, deck.copies_of(TARGET), 9, 1)
    assert within_ci(observed, expected, n)


def test_simulated_sell_rate_matches_exact_when_pilot_only_sells(deck):
    """A pilot that never plays cards should reproduce the exact sell curve."""
    profile = PlayabilityProfile(
        name="never plays", defaults={"legal": 0.0, "strategic": 0.0, "sell_willingness": 1.0}
    )
    # No plays and no Legend Calls: nothing but natural draws and sells, which is
    # exactly what the closed-form sell math models.
    policy = PilotPolicy(
        profile=profile,
        play_non_target_cards=False,
        min_sell_willingness=0.0,
        call_legend_for_draw=False,
    )
    n = 20_000
    summary = simulate(deck, policy, iterations=n, seed=13, max_turn=4)
    for turn in (1, 2, 3, 4):
        observed = summary.counts["sells_through"][turn - 1] / n
        expected = sells.consecutive_sells(deck.size, deck.sellable_count, turn).value
        assert within_ci(observed, expected, n), (turn, observed, expected)


def test_legend_draws_improve_sell_consistency(deck):
    """The Legend's conditional draw is a real gain the closed form cannot see."""
    profile = PlayabilityProfile(
        name="never plays", defaults={"legal": 0.0, "strategic": 0.0, "sell_willingness": 1.0}
    )
    shared = dict(play_non_target_cards=False, min_sell_willingness=0.0)
    without = simulate(
        deck, PilotPolicy(profile=profile, call_legend_for_draw=False, **shared),
        iterations=6_000, seed=29, max_turn=6,
    )
    with_legend = simulate(
        deck, PilotPolicy(profile=profile, call_legend_for_draw=True, **shared),
        iterations=6_000, seed=29, max_turn=6,
    )
    assert with_legend.counts["sells_through"][5] >= without.counts["sells_through"][5]
    assert with_legend.draws_by_source.get("Muamar Reyes — El Capitán", 0) > 0


def test_playing_sellables_reduces_simulated_sell_consistency(deck, profile):
    policy = PilotPolicy(target_names=(TARGET,), profile=profile)
    n = 4_000
    summary = simulate(deck, policy, iterations=n, seed=17, max_turn=5)
    simulated = summary.counts["sells_through"][4] / n
    exact = sells.consecutive_sells(deck.size, deck.sellable_count, 5).value
    assert simulated < exact


def test_mulligan_policy_raises_target_rate(deck, profile):
    n = 4_000
    baseline = simulate(
        deck, PilotPolicy(target_names=(TARGET,), profile=profile), iterations=n, seed=5, max_turn=3
    )
    aggressive = simulate(
        deck,
        PilotPolicy(
            target_names=(TARGET,), profile=profile,
            mulligan=builtin_policies()["Target Only"],
        ),
        iterations=n, seed=5, max_turn=3,
    )
    assert aggressive.counts["target_seen"][2] > baseline.counts["target_seen"][2]


def test_layers_are_ordered(deck, profile):
    policy = PilotPolicy(target_names=(TARGET,), profile=profile)
    n = 4_000
    summary = simulate(deck, policy, iterations=n, seed=19, max_turn=3)
    seen = summary.counts["target_seen"][2]
    in_hand = summary.counts["target_in_hand"][2]
    affordable = summary.counts["target_affordable"][2]
    legal = summary.counts["target_legal"][2]
    strategic = summary.counts["target_strategic"][2]
    assert seen >= in_hand >= affordable >= legal >= strategic


def test_resource_accounting_spends_eddies_then_legends(rules):
    state = GameState(rules=rules, rng=random.Random(0))
    state.legends = setup_legends(
        [Card(card_id=str(i), name=f"L{i}", is_legend=True) for i in range(3)], random.Random(0)
    )
    state.eddies = state.ready_eddies = 2
    assert state.available_resources == 5  # 2 eddies + 3 legends
    spent = state.spend(4)
    assert spent == 4
    assert state.ready_eddies == 0
    assert sum(1 for l in state.legends if l.spent) == 2
    assert state.resources_spent == 4


def test_selling_creates_one_eddie(rules):
    card = Card(card_id="s", name="S", sellable=True)
    state = GameState(rules=rules, rng=random.Random(0), hand=[card])
    assert state.sell(card) is True
    assert state.eddies == rules.eddie_value
    assert state.cards_sold == [card]
    assert state.sells_by_turn[state.turn] == 1


def test_playing_requires_resources(rules):
    card = Card(card_id="c", name="C", cost=3, type="Unit")
    state = GameState(rules=rules, rng=random.Random(0), hand=[card])
    assert state.play(card) is False
    state.eddies = state.ready_eddies = 3
    assert state.play(card) is True
    assert card in state.units and state.ready_eddies == 0


def test_legend_order_is_randomized():
    cards = [Card(card_id=str(i), name=f"L{i}", is_legend=True) for i in range(3)]
    orders = {
        tuple(l.card.name for l in setup_legends(cards, random.Random(seed)))
        for seed in range(30)
    }
    assert len(orders) > 1


def test_legend_call_applies_conditional_draw(rules):
    legend = Card(
        card_id="m", name="Muamar", is_legend=True,
        effect_metadata=[
            {"trigger": "on_call", "effect": "draw", "amount": 1,
             "conditions": [{"type": "distinct_gigs", "operator": ">=", "value": 3}]}
        ],
    )
    state = GameState(rules=rules, rng=random.Random(0),
                      deck=[Card(card_id=str(i), name=f"c{i}") for i in range(5)])
    state.legends = setup_legends([legend], random.Random(0))
    state.gig_values = [1, 2]
    state.street_cred = 3
    records = call_legend(state, state.legends[0])
    assert records and records[0]["applied"] == 0  # only two distinct gigs

    state.legends[0].ready = True
    state.legends[0].called_this_turn = False
    state.gig_values = [1, 2, 3]
    records = call_legend(state, state.legends[0])
    assert records[0]["applied"] == 1
    assert state.draws_by_source["Muamar"] == 1


def test_calling_a_legend_consumes_its_resource_value(rules):
    legend = Card(card_id="m", name="M", is_legend=True)
    state = GameState(rules=rules, rng=random.Random(0))
    state.legends = setup_legends([legend], random.Random(0))
    before = state.available_resources
    call_legend(state, state.legends[0])
    assert state.available_resources == before - rules.legend_resource_value


def test_gig_distribution_respects_weights():
    distribution = GigDistribution.from_mapping({1: 3, 6: 1})
    rng = random.Random(4)
    rolls = [distribution.roll(rng) for _ in range(4000)]
    assert isclose(rolls.count(1) / len(rolls), 0.75, abs_tol=0.03)
    assert isclose(distribution.mean(), (1 * 3 + 6 * 1) / 4)


def test_gig_distribution_from_observations():
    distribution = GigDistribution.from_observations([2, 2, 5])
    assert distribution.probabilities() == {2: pytest.approx(2 / 3), 5: pytest.approx(1 / 3)}


def test_non_uniform_distribution_is_not_assumed():
    uniform = GigDistribution.uniform(6)
    assert uniform.mean() == 3.5
    skewed = GigDistribution.from_mapping({6: 1})
    assert skewed.mean() == 6.0


def test_board_proxy_samples_configured_probability():
    proxy = BoardProxy(probabilities={"valid_target": {1: 0.0, 3: 1.0}})
    rng = random.Random(0)
    assert proxy.resolve(1, rng)["valid_target"] is False
    assert proxy.resolve(3, rng)["valid_target"] is True


def test_board_proxy_round_trips():
    proxy = BoardProxy()
    again = BoardProxy.from_dict(proxy.to_dict())
    assert again.probability("valid_target", 4) == proxy.probability("valid_target", 4)


def test_confidence_interval_shrinks_with_sample_size():
    small = proportion_result(500, 1_000, "p")
    large = proportion_result(50_000, 100_000, "p")
    assert small.standard_error > large.standard_error
    assert large.ci95[0] < 0.5 < large.ci95[1]


def test_resource_threshold_rate_increases_with_turn(deck, profile):
    policy = PilotPolicy(target_names=(TARGET,), profile=profile)
    early = resource_threshold_rate(deck, 6, 2, policy, iterations=1500, seed=3)
    late = resource_threshold_rate(deck, 6, 5, policy, iterations=1500, seed=3)
    assert late.value > early.value
    assert late.method.value.startswith("SIMULATED")


def test_simulation_rejects_impossible_configurations(deck, profile):
    tiny = Deck(name="tiny", main=[DeckEntry(Card(card_id="c", name="C"), 5)])
    with pytest.raises(ValueError):
        simulate(tiny, PilotPolicy(profile=profile), iterations=10, max_turn=6)


def test_mulligan_rate_recorded(deck, profile):
    policy = PilotPolicy(
        target_names=(TARGET,), profile=profile, mulligan=builtin_policies()["Sell Stability"]
    )
    summary = simulate(deck, policy, iterations=2_000, seed=23, max_turn=2)
    assert 0.0 < summary.mulligans / summary.iterations < 1.0
    assert summary.assumptions["mulligan_policy"] == "Sell Stability"
