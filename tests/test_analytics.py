"""Analytics: access, playability, burden, density, marginal value, sensitivity."""

from __future__ import annotations

from math import isclose

import pytest

from cyberpunk_deck_math.analytics import (
    access,
    axioms,
    dead_cards,
    deck_summary,
    interpretation,
    marginal_value,
    opportunity_density,
    playability,
    recommender,
    sensitivity,
)
from cyberpunk_deck_math.config import AnalysisConfig, SellableSettings
from cyberpunk_deck_math.models import Card, PlayabilityProfile
from cyberpunk_deck_math.probability import hypergeom

TARGET = "Jackie Welles — Ride or Die Choom"
FILLER = "Placeholder Combat Unit"


def test_raw_access_matches_hypergeometric(deck, rules):
    result = access.raw_access(deck, TARGET, 3, rules)
    expected = hypergeom.at_least(deck.size, 2, rules.cards_seen(3), 1)
    assert isclose(result.value, expected)
    assert result.method.is_exact()


def test_access_curve_is_monotone(deck, rules):
    curve = access.access_curve(deck, TARGET, 6, rules)
    values = [curve["opening"].value] + [curve[f"T{t}"].value for t in range(1, 7)]
    assert values == sorted(values)


def test_copies_comparison_orders_by_copies(deck, rules):
    table = access.copies_comparison(deck.size, (1, 2, 3), 3, rules)
    assert table[1]["T3"].value < table[2]["T3"].value < table[3]["T3"].value


def test_exact_counts_sum_to_one(deck, rules):
    counts = access.exact_counts(deck, TARGET, 3, rules)
    assert isclose(sum(r.value for r in counts.values()), 1.0)


def test_compound_access_is_at_most_each_marginal(deck, rules):
    joint = access.target_and_sellables(deck, TARGET, 3, 4, rules)
    marginal = access.raw_access(deck, TARGET, 3, rules)
    assert joint.value <= marginal.value
    assert joint.method.is_exact()


def test_draw_sources_identified_from_metadata(deck, profile):
    sources = {s.name for s in access.draw_sources_from_deck(deck, profile)}
    assert "Field Operator" in sources
    assert "Memory Relapse" in sources


def test_expected_extra_draws_is_labelled_heuristic(deck, profile, rules):
    source = next(s for s in access.draw_sources_from_deck(deck, profile)
                  if s.name == "Memory Relapse")
    result = access.expected_extra_draws(deck, source, 3, rules)
    assert result.method.is_heuristic()
    assert "Do not substitute" in result.detail
    assert 0.0 <= result.value <= 1.0


def test_conditional_draw_below_unconditional(deck, profile, rules):
    sources = {s.name: s for s in access.draw_sources_from_deck(deck, profile)}
    conditional = access.expected_extra_draws(deck, sources["Memory Relapse"], 3, rules)
    early = access.expected_extra_draws(deck, sources["Field Operator"], 3, rules)
    assert conditional.value < early.value


def test_playability_lookup_uses_the_latest_specified_turn():
    profile = PlayabilityProfile.from_dict(
        {"strategic": {"Card": {"1": 0.0, "3": 0.5, "5": 0.9}}}
    )
    card = Card(card_id="c", name="Card")
    assert [profile.strategic_playability(card, t) for t in range(1, 7)] == [
        0.0, 0.0, 0.5, 0.5, 0.9, 0.9
    ]


def test_strategic_never_exceeds_legal():
    profile = PlayabilityProfile.from_dict(
        {"legal": {"Card": {"1": 0.2}}, "strategic": {"Card": {"1": 0.9}}}
    )
    card = Card(card_id="c", name="Card")
    assert profile.strategic_playability(card, 1) == 0.2


def test_profile_round_trips(profile):
    again = PlayabilityProfile.from_dict(profile.to_dict())
    card = Card(card_id="c", name=TARGET)
    assert again.strategic_playability(card, 3) == profile.strategic_playability(card, 3)


def test_profile_save_and_load(tmp_path, profile):
    path = playability.save_profile(profile, tmp_path / "p.json")
    again = playability.load_profile(path)
    assert again.name == profile.name


def test_playtest_feedback_updates_one_turn(profile):
    card = Card(card_id="c", name="Memory Relapse")
    before = profile.strategic_playability(card, 3)
    playability.record_playtest_feedback(profile, card, 3, 0.04)
    assert profile.strategic_playability(card, 3) == 0.04
    assert before != 0.04
    assert profile.confidence[card.key] == "playtested"


def test_simulation_feedback_is_labelled(profile):
    card = Card(card_id="c", name="Field Operator")
    playability.apply_simulation_feedback(profile, card, {2: 0.42})
    assert profile.strategic_playability(card, 2) == 0.42
    assert "simulation" in profile.rationale[card.key].lower()


def test_default_profile_is_cost_gated(deck):
    profile = playability.default_profile(deck, "cost")
    jackie = deck.find(TARGET).card
    assert profile.legal_playability(jackie, 2) == 0.0
    assert profile.legal_playability(jackie, 6) == 0.6  # the turn the cost is first met
    cheap = deck.find("Zetatech Faceplate").card
    assert profile.legal_playability(cheap, 3) == 1.0


def test_dead_burden_and_density_are_complements(deck, profile):
    for turn in range(1, 7):
        burden = dead_cards.dead_card_burden(deck, profile, turn).total
        density = opportunity_density.opportunity_density(deck, profile, turn).value
        assert isclose(burden + density, 1.0, abs_tol=1e-9)


def test_dead_burden_falls_over_time(deck, profile):
    values = [dead_cards.dead_card_burden(deck, profile, t).total for t in range(1, 7)]
    assert values == sorted(values, reverse=True)


def test_dead_burden_categories_sum_to_the_total(deck, profile):
    breakdown = dead_cards.dead_card_burden(deck, profile, 2, (TARGET,))
    assert isclose(sum(breakdown.by_category.values()), breakdown.total, abs_tol=1e-9)
    assert set(breakdown.by_category) <= set(dead_cards.CATEGORIES)


def test_target_card_held_is_its_own_category(deck, profile):
    breakdown = dead_cards.dead_card_burden(deck, profile, 1, (TARGET,))
    assert "target_held" in breakdown.by_category


def test_low_playability_share(deck, profile):
    share = dead_cards.low_playability_share(deck, profile, 3, 0.10)
    assert 0.0 < share < 1.0


def test_expected_playables_scales_with_hand_size(deck, profile, rules):
    result = opportunity_density.expected_playables_in_hand(deck, profile, 3, rules=rules)
    density = opportunity_density.opportunity_density(deck, profile, 3).value
    assert isclose(result.value, density * rules.cards_seen(3))


def test_marginal_swap_changes_access(deck, profile, database, rules):
    filler = database.require(FILLER)
    comparison = marginal_value.compare_copies(
        deck, TARGET, filler, profile, (2, 3), rules, 4
    )
    assert comparison.deltas["target_access"][3] > 0
    assert comparison.b.sellable_count == comparison.a.sellable_count  # filler not sellable


def test_cutting_a_sellable_moves_density(deck, profile, database, rules):
    filler = database.require("Placeholder Sellable Gig G")
    comparison = marginal_value.compare_copies(
        deck, TARGET, filler, profile, (2, 3), rules, 4
    )
    assert comparison.b.sellable_count == comparison.a.sellable_count - 1
    assert comparison.deltas["sell_consistency"][3] < 0
    assert comparison.notes


def test_deck_size_is_preserved_by_swaps(deck, database):
    variant = deck.with_copies(TARGET, 3, database.require(FILLER))
    assert variant.size == deck.size
    assert variant.copies_of(TARGET) == 3


def test_swap_rejects_impossible_trades(deck, database):
    with pytest.raises(ValueError):
        deck.with_swap(FILLER, database.require(TARGET), count=99)
    with pytest.raises(KeyError):
        deck.with_swap("Nonexistent", database.require(TARGET))


def test_sensitivity_sellable_sweep_is_monotone(deck, rules):
    run = sensitivity.sweep_sellable_target(deck, (0.55, 0.60, 0.65), 3, rules)
    assert run.outcomes == sorted(run.outcomes)
    assert run.method.is_exact()


def test_sensitivity_flags_material_assumptions(deck, profile):
    run = sensitivity.sweep_strategic_playability(
        deck, profile, "Memory Relapse", 3, (0.0, 0.5, 1.0)
    )
    assert run.spread > 0
    assert isinstance(run.material, bool)
    assert "assumption" in run.to_dict()["verdict"] or "stable" in run.to_dict()["verdict"]


def test_sensitivity_sweep_does_not_mutate_the_profile(deck, profile):
    before = profile.strategic_playability(deck.find("Memory Relapse").card, 3)
    sensitivity.sweep_strategic_playability(deck, profile, "Memory Relapse", 3, (0.9,))
    assert profile.strategic_playability(deck.find("Memory Relapse").card, 3) == before


def test_copies_sweep_uses_exact_math(deck, profile, database, rules):
    run = sensitivity.sweep_copies(deck, TARGET, database.require(FILLER), (1, 2, 3), 3, rules)
    assert run.outcomes == sorted(run.outcomes)
    assert run.method.is_exact()


def test_recommender_ranks_low_impact_cards_first(deck, profile):
    recommendation = recommender.recommend_sellable_swaps(deck, profile, SellableSettings())
    names = [c.name for c in recommendation.candidates]
    assert names, "expected non-sellable candidates"
    assert all(not deck.find(n).card.is_sellable for n in names)
    scores = [c.score for c in recommendation.candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(c.tradeoff for c in recommendation.candidates)


def test_recommender_protects_the_target(deck, profile):
    recommendation = recommender.recommend_sellable_swaps(
        deck, profile, SellableSettings(), target_names=(TARGET,)
    )
    assert TARGET not in [c.name for c in recommendation.candidates]


def test_recommender_warns_when_above_range(deck, profile):
    settings = SellableSettings.build(minimum="50%", target="55%", range_min="50%", range_max="55%")
    recommendation = recommender.recommend_sellable_swaps(deck, profile, settings)
    assert any("above the configured" in note for note in recommendation.notes)


def test_axioms_flag_below_minimum(deck, profile):
    config = AnalysisConfig(
        sellable=SellableSettings.build(minimum="70%", target="75%", range_min="70%", range_max="80%")
    )
    messages = [a.message for a in axioms.evaluate_axioms(deck, profile, config)]
    assert any("below the configured" in m for m in messages)


def test_axioms_flag_placeholder_data(deck, profile):
    messages = [a.message for a in axioms.evaluate_axioms(deck, profile)]
    assert any("non-official data source" in m for m in messages)


def test_axiom_thresholds_are_editable(deck, profile):
    config = AnalysisConfig()
    config.warning_thresholds["dead_card_burden_turn3"] = 0.001
    messages = [a.message for a in axioms.evaluate_axioms(deck, profile, config)]
    assert any("dead-card burden" in m for m in messages)


def test_summary_bundles_everything(deck, profile, config):
    summary = deck_summary.summarize(deck, profile, config, (TARGET,))
    assert summary.composition.deck_size == 40
    assert summary.sell.status.sellable_count == 25
    assert set(summary.action_density) == set(range(1, config.max_turn + 1))
    assert TARGET in summary.target_access
    rendered = deck_summary.render_summary(summary)
    assert "EXACT — Hypergeometric" in rendered
    assert "USER / PLAYTESTING HEURISTIC" in rendered


def test_conclusions_are_plain_english(deck, profile, config):
    summary = deck_summary.summarize(deck, profile, config, (TARGET,))
    lines = interpretation.summary_conclusions(summary, (TARGET,), 3)
    assert any("sellables out of" in line for line in lines)
    assert any("EXACT — Hypergeometric" in line for line in lines)


def test_sell_step_sentence_quotes_both_numbers():
    text = interpretation.sell_step_sentence(40, 24, 25, 3)
    assert "24" in text and "25" in text and "percentage points" in text
