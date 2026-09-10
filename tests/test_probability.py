"""Exact hypergeometric and multivariate probability."""

from __future__ import annotations

from fractions import Fraction
from math import comb, isclose

import pytest

from cyberpunk_deck_math.config import RuleConfig
from cyberpunk_deck_math.probability import hypergeom as h
from cyberpunk_deck_math.probability import multivariate as m
from cyberpunk_deck_math.probability import sells


def test_pmf_matches_definition():
    N, K, n, k = 40, 3, 6, 1
    expected = comb(K, k) * comb(N - K, n - k) / comb(N, n)
    assert isclose(h.pmf(N, K, n, k), expected)


def test_pmf_sums_to_one():
    total = sum(h.pmf(40, 25, 9, k) for k in range(0, 10))
    assert isclose(total, 1.0, abs_tol=1e-12)


def test_at_least_one_is_complement_of_none():
    N, K, n = 40, 2, 9
    assert isclose(h.at_least(N, K, n, 1), 1 - comb(N - K, n) / comb(N, n))


def test_at_most_and_at_least_are_consistent():
    N, K, n = 40, 25, 9
    for k in range(0, 8):
        assert isclose(h.at_most(N, K, n, k) + h.at_least(N, K, n, k + 1), 1.0)


def test_exact_counts_supported():
    N, K, n = 40, 3, 9
    assert h.exactly(N, K, n, 0) > 0
    assert h.exactly(N, K, n, 3) > 0
    assert h.exactly(N, K, n, 4) == 0


def test_more_copies_never_reduce_access():
    values = [h.at_least(40, copies, 9, 1) for copies in (1, 2, 3)]
    assert values == sorted(values)


def test_mean_matches_formula():
    assert isclose(h.mean(40, 25, 9), 9 * 25 / 40)


def test_validation_errors():
    with pytest.raises(ValueError):
        h.at_least(40, 41, 6, 1)
    with pytest.raises(ValueError):
        h.at_least(40, 3, 41, 1)


def test_exact_fraction_is_rational():
    value = h.pmf_exact(40, 25, 9, 5)
    assert isinstance(value, Fraction)


def test_multivariate_reduces_to_hypergeometric():
    groups = [m.Group("a", 3)]
    exact = m.probability(groups, 40, 9, lambda c: c["a"] >= 1)
    assert isclose(exact, h.at_least(40, 3, 9, 1))


def test_multivariate_joint_distribution_sums_to_one():
    groups = [m.Group("a", 3), m.Group("b", 25)]
    total = sum(p for _, p in m.joint_distribution(groups, 40, 9))
    assert total == Fraction(1)


def test_multivariate_compound_is_between_marginals():
    groups = [m.Group("target", 2), m.Group("sellables", 25)]
    joint = m.compound_result(groups, 40, 9, {"target": 1, "sellables": 3}).value
    target_only = h.at_least(40, 2, 9, 1)
    assert 0 < joint <= target_only


def test_multivariate_forbidden_group():
    groups = [m.Group("target", 2), m.Group("dead", 6)]
    with_cap = m.compound_result(
        groups, 40, 9, {"target": 1}, forbidden={"dead": 3}
    ).value
    without_cap = m.compound_result(groups, 40, 9, {"target": 1}).value
    assert with_cap < without_cap


def test_overlapping_groups_rejected():
    with pytest.raises(ValueError):
        m.probability([m.Group("a", 30), m.Group("b", 30)], 40, 9, lambda c: True)


def test_consecutive_sells_never_exceeds_weak_form():
    rules = RuleConfig()
    for turn in range(1, 7):
        strong = sells.consecutive_sells(40, 22, turn, rules).value
        weak = sells.at_least_k_sellables_by_turn(40, 22, turn, rules).value
        assert strong <= weak + 1e-12


def test_consecutive_sells_monotone_in_density():
    rules = RuleConfig()
    values = [sells.consecutive_sells(40, s, 4, rules).value for s in (20, 24, 28)]
    assert values == sorted(values)


def test_consecutive_sells_decreasing_in_turn():
    rules = RuleConfig()
    values = [sells.consecutive_sells(40, 25, t, rules).value for t in range(1, 7)]
    assert values == sorted(values, reverse=True)


def test_two_sells_per_turn_is_strictly_harder():
    rules = RuleConfig()
    one = sells.consecutive_sells(40, 25, 3, rules, sells_per_turn=1).value
    two = sells.consecutive_sells(40, 25, 3, rules, sells_per_turn=2).value
    assert two < one


def test_miss_curve_complements_sell_curve():
    rules = RuleConfig()
    curve = sells.sell_curve(40, 25, 3, rules)
    misses = sells.miss_curve(40, 25, 3, rules)
    for turn in curve:
        assert isclose(curve[turn].value + misses[turn].value, 1.0)


def test_density_table_covers_the_50_to_70_band():
    rows = sells.density_table(40, max_turn=3)
    counts = [row.sellables for row in rows]
    assert counts[0] == 20 and counts[-1] == 28
    assert isclose(dict(zip(counts, [r.pct for r in rows]))[25], 0.625)


def test_density_table_scales_with_deck_size():
    rows = sells.density_table(50, max_turn=2)
    assert rows[0].sellables == 25
    assert isclose(rows[0].pct, 0.5)


@pytest.mark.parametrize(
    "size,sellables,pct,expected",
    [
        (40, 23, 0.60, 1),
        (40, 23, 0.625, 2),
        (40, 24, 0.60, 0),
        (40, 25, 0.65, 1),
        (44, 26, 0.625, 2),
    ],
)
def test_cards_needed(size, sellables, pct, expected):
    assert sells.cards_needed(size, sellables, pct) == expected


def test_opening_sellable_probability():
    result = sells.opening_sellables(40, 25, 6, 1)
    assert result.method.is_exact()
    assert result.value > 0.99
