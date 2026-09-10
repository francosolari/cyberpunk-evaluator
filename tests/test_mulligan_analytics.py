"""Mulligan analytics and the layered target report (simulation-backed)."""

from __future__ import annotations

import pytest

from cyberpunk_deck_math.analytics import mulligan_analytics
from cyberpunk_deck_math.analytics import target as target_analytics
from cyberpunk_deck_math.probability.mulligan import builtin_policies

TARGET = "Jackie Welles — Ride or Die Choom"


def test_opening_hand_stats_no_mulligan(deck, profile, rules):
    stats = mulligan_analytics.opening_hand_stats(
        deck, builtin_policies()["No Mulligan"], (TARGET,), profile, rules,
        iterations=2_000, seed=3,
    )
    assert stats.mulligan_rate.value == 0.0
    assert stats.keep_rate.value == 1.0
    assert 0.2 < stats.target_in_opening.value < 0.4
    assert stats.average_sellables > 3.0


def test_hard_mulligan_raises_target_rate_and_costs_something(deck, profile, rules):
    baseline = mulligan_analytics.opening_hand_stats(
        deck, builtin_policies()["No Mulligan"], (TARGET,), profile, rules, 2_000, 5
    )
    aggressive = mulligan_analytics.opening_hand_stats(
        deck, builtin_policies()["Target Only"], (TARGET,), profile, rules, 2_000, 5
    )
    assert aggressive.mulligan_rate.value > 0.5
    assert aggressive.target_in_opening.value > baseline.target_in_opening.value


def test_sell_stability_policy_raises_average_sellables(deck, profile, rules):
    baseline = mulligan_analytics.opening_hand_stats(
        deck, builtin_policies()["No Mulligan"], (TARGET,), profile, rules, 2_000, 9
    )
    stability = mulligan_analytics.opening_hand_stats(
        deck, builtin_policies()["Sell Stability"], (TARGET,), profile, rules, 2_000, 9
    )
    assert stability.average_sellables > baseline.average_sellables


def test_policy_comparison_reports_both_axes(deck, profile, rules):
    rows = mulligan_analytics.compare_policies(
        deck,
        [builtin_policies()[name] for name in ("No Mulligan", "Target Only", "2+ Sellables")],
        (TARGET,), profile, rules, iterations=1_500, opening_iterations=1_500,
        seed=11, max_turn=3,
    )
    assert len(rows) == 3
    for row in rows:
        assert set(row.target_by_turn) == {1, 2, 3}
        assert row.sells_through[3].ci95 is not None
        assert row.target_by_turn[3].method.value.startswith("SIMULATED")
    rendered = mulligan_analytics.render_comparison(rows, 3)
    assert "Mull %" in rendered and "Monte Carlo" in rendered


def test_hand_quality_rule_is_configurable(deck, profile, rules):
    strict = mulligan_analytics.HandQualityRule(min_sellables=5, min_early_playables=3)
    lenient = mulligan_analytics.HandQualityRule(
        min_sellables=0, min_early_playables=0, require_target_or_draw=False
    )
    policy = builtin_policies()["No Mulligan"]
    strict_stats = mulligan_analytics.opening_hand_stats(
        deck, policy, (TARGET,), profile, rules, 1_000, 2, quality=strict
    )
    lenient_stats = mulligan_analytics.opening_hand_stats(
        deck, policy, (TARGET,), profile, rules, 1_000, 2, quality=lenient
    )
    assert lenient_stats.good_hand_rate.value == 1.0
    assert strict_stats.good_hand_rate.value < lenient_stats.good_hand_rate.value


def test_target_report_layers_are_ordered_and_labelled(deck, profile, rules):
    report = target_analytics.target_report(
        deck, TARGET, 3, profile, rules,
        mulligan=builtin_policies()["Target or Draw"], iterations=3_000, seed=13,
    )
    assert report.seen.method.is_exact()
    assert report.seen_simulated.value >= report.seen.value  # mulligans dig deeper
    assert report.in_hand.value >= report.affordable.value >= report.legal.value
    assert report.legal.value >= report.strategic.value
    assert report.played.value <= report.strategic.value + 0.01
    assert report.sells_through.method.is_exact()
    rendered = report.render()
    assert "P(seen, no mulligan)" in rendered
    assert "P(actually played by T3)" in rendered


def test_target_report_records_draw_contributions(deck, profile, rules):
    report = target_analytics.target_report(
        deck, TARGET, 3, profile, rules, iterations=2_000, seed=17
    )
    assert "Field Operator" in report.draws_by_source
    assert report.draws_by_source["Field Operator"] > 0


def test_target_report_rejects_cards_outside_the_deck(deck, profile, rules):
    with pytest.raises(KeyError):
        target_analytics.target_report(deck, "Not In Deck", 3, profile, rules, iterations=10)


def test_target_report_exports_all_layers(deck, profile, rules):
    report = target_analytics.target_report(
        deck, TARGET, 3, profile, rules, iterations=1_000, seed=19
    )
    data = report.to_dict()
    assert set(data["layers"]) == {
        "1_raw_card_access", "1b_raw_card_access_with_mulligan", "3_in_hand",
        "4_affordable", "5_legal_playability", "6_strategic_playability",
        "7_actually_played", "2_resource_access",
    }
