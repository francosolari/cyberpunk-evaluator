"""Mechanical and effective sellable density, status, and targets."""

from __future__ import annotations

from math import isclose

import pytest

from cyberpunk_deck_math.analytics import sell_density
from cyberpunk_deck_math.config import SellableSettings, normalize_pct
from cyberpunk_deck_math.models import Card, Deck, DeckEntry, PlayabilityProfile


def make_deck(size: int, sellables: int) -> Deck:
    sellable = Card(card_id="s", name="Sellable", sellable=True, cost=1)
    other = Card(card_id="n", name="NonSellable", sellable=False, cost=1)
    deck = Deck(name="test")
    if sellables:
        deck.main.append(DeckEntry(sellable, sellables))
    if size - sellables:
        deck.main.append(DeckEntry(other, size - sellables))
    return deck


@pytest.mark.parametrize(
    "raw,expected",
    [(60, 0.60), ("60", 0.60), ("60%", 0.60), (0.60, 0.60), ("62.5%", 0.625), (0, 0.0)],
)
def test_percentage_normalization(raw, expected):
    assert isclose(normalize_pct(raw), expected)


def test_percentage_rejects_out_of_range():
    with pytest.raises(ValueError):
        normalize_pct(140)
    with pytest.raises(ValueError):
        normalize_pct(-1)


@pytest.mark.parametrize(
    "sellables,expected_pct",
    [(20, 0.500), (23, 0.575), (24, 0.600), (25, 0.625), (26, 0.650), (28, 0.700)],
)
def test_exact_percentages_for_40_cards(sellables, expected_pct):
    deck = make_deck(40, sellables)
    assert isclose(deck.sellable_pct, expected_pct)


def test_status_below_minimum():
    status = sell_density.sellable_status(make_deck(40, 23))
    assert status.status == sell_density.BELOW_MINIMUM
    assert status.cards_to_minimum == 1
    assert status.cards_to_target == 2


def test_status_below_target():
    settings = SellableSettings.build(minimum="55%", target="62.5%", range_min="60%")
    status = sell_density.sellable_status(make_deck(40, 23), settings)
    assert status.status == sell_density.BELOW_TARGET
    assert status.cards_to_minimum == 0
    assert status.cards_to_target == 2


def test_status_in_range():
    status = sell_density.sellable_status(make_deck(40, 25))
    assert status.status == sell_density.IN_TARGET_RANGE
    assert status.cards_to_minimum == status.cards_to_target == 0


def test_status_above_range():
    status = sell_density.sellable_status(make_deck(40, 27))
    assert status.status == sell_density.ABOVE_TARGET_RANGE
    assert status.cards_over_range_max == 1


def test_status_for_non_40_card_decks():
    status = sell_density.sellable_status(make_deck(44, 26))
    assert isclose(status.actual_pct, 26 / 44)
    assert status.cards_to_target == 2  # 27.5 -> 28 sellables for 62.5%


def test_custom_settings_are_respected():
    settings = SellableSettings.build(minimum="55%", target=0.60, range_min=55, range_max=62)
    status = sell_density.sellable_status(make_deck(40, 23), settings)
    assert status.status == sell_density.IN_TARGET_RANGE
    assert status.minimum_pct == 0.55


def test_target_range_validation():
    with pytest.raises(ValueError):
        SellableSettings(target_range=(0.65, 0.60))


def test_effective_density_equals_mechanical_at_full_willingness():
    deck = make_deck(40, 25)
    profile = PlayabilityProfile(name="full", defaults={"legal": 1.0, "strategic": 1.0, "sell_willingness": 1.0})
    effective = sell_density.effective_sellable_density(deck, profile, 1)
    assert isclose(effective.value, deck.sellable_pct)


def test_effective_density_below_mechanical_when_pilot_holds_cards():
    deck = make_deck(40, 25)
    profile = PlayabilityProfile.from_dict(
        {"name": "held", "sell_willingness": {"Sellable": {"1": 0.5}}}
    )
    effective = sell_density.effective_sellable_density(deck, profile, 1)
    assert isclose(effective.value, 0.5 * deck.sellable_pct)
    assert effective.method.is_heuristic()


def test_non_sellable_cards_have_zero_willingness():
    profile = PlayabilityProfile.from_dict(
        {"sell_willingness": {"NonSellable": {"1": 1.0}}}
    )
    card = Card(card_id="n", name="NonSellable", sellable=False)
    assert profile.willingness(card, 1) == 0.0


def test_real_deck_effective_below_mechanical(deck, profile):
    mechanical = deck.sellable_pct
    effective = sell_density.effective_sellable_density(deck, profile, 3).value
    assert effective < mechanical


def test_counts_for_pcts_are_exact():
    counts = sell_density.counts_for_pcts(40, [0.60, 0.625, 0.65])
    assert counts == {0.60: 24, 0.625: 25, 0.65: 26}


def test_sell_report_bundles_status_and_curves(deck, config, profile):
    report = sell_density.sell_report(deck, config.sellable, config.rules, profile, 4)
    assert report.status.sellable_count == 25
    assert set(report.consecutive) == {1, 2, 3, 4}
    assert report.opening.method.is_exact()
    assert all(r.method.is_heuristic() for r in report.effective.values())
