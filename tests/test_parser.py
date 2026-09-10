"""Decklist parsing across the supported formats."""

from __future__ import annotations

import pytest

from cyberpunk_deck_math.config import RuleConfig
from cyberpunk_deck_math.parser import (
    format_deck,
    parse_decklist,
    parse_lines,
    split_reference,
    validate_deck,
)

FORMAT_A = """Name: YYG Jackie

Legends

1x Muamar Reyes — El Capitán
1x Placeholder Legend Two
1x Placeholder Legend Three

Main Deck

2x Jackie Welles — Ride or Die Choom
2x Field Operator
3x Zetatech Faceplate
"""

FORMAT_B = """Legends:
Muamar Reyes — El Capitán
Placeholder Legend Two
Placeholder Legend Three

Main Deck:
2 Jackie Welles — Ride or Die Choom
2 Field Operator
3 Zetatech Faceplate
"""

FORMAT_C = """Main Deck
1x 001 Jackie Welles — Ride or Die Choom
3x 003 Zetatech Faceplate
"""

FORMAT_D = """Main Deck
3x MS01-003
1x MS01-001
"""


def test_format_a(database):
    result = parse_decklist(FORMAT_A, database, ignore_legality=True)
    assert result.deck.name == "YYG Jackie"
    assert len(result.deck.legends) == 3
    assert result.deck.size == 7
    assert result.deck.copies_of("Zetatech Faceplate") == 3
    assert not result.unknown


def test_format_b_legends_without_counts(database):
    result = parse_decklist(FORMAT_B, database, ignore_legality=True)
    assert [c.name for c in result.deck.legends][0] == "Muamar Reyes — El Capitán"
    assert result.deck.size == 7


def test_format_c_collector_numbers(database):
    result = parse_decklist(FORMAT_C, database, ignore_legality=True)
    assert result.deck.copies_of("Jackie Welles — Ride or Die Choom") == 1
    assert result.deck.copies_of("Zetatech Faceplate") == 3
    assert not result.unknown


def test_format_d_card_ids(database):
    result = parse_decklist(FORMAT_D, database, ignore_legality=True)
    assert result.deck.copies_of("Zetatech Faceplate") == 3
    assert not result.unknown


@pytest.mark.parametrize(
    "dash", ["—", "–", "-", "‑"]
)
def test_unicode_dashes_match(database, dash):
    text = f"Main Deck\n2x Jackie Welles {dash} Ride or Die Choom\n"
    result = parse_decklist(text, database, ignore_legality=True)
    assert result.deck.copies_of("Jackie Welles — Ride or Die Choom") == 2


def test_comments_and_blank_lines_ignored(database):
    text = "# a comment\n\nMain Deck\n\n2x Field Operator  # trailing comment\n"
    result = parse_decklist(text, database, ignore_legality=True)
    assert result.deck.size == 2
    assert not result.unknown


def test_unknown_lines_are_reported_not_ignored(database):
    text = "Main Deck\n3x Totally Fake Card\n"
    result = parse_decklist(text, database, ignore_legality=True)
    assert result.deck.size == 0
    assert result.unknown and "Totally Fake Card" in result.unknown[0][1]
    assert not result.ok


def test_missing_count_warns(database):
    text = "Main Deck\nField Operator\n"
    result = parse_decklist(text, database, ignore_legality=True)
    assert result.deck.size == 1
    assert any("no copy count" in w for w in result.warnings)


def test_set_code_suffix():
    name, set_code, collector = split_reference("Field Operator (MS01)")
    assert name == "Field Operator"
    assert set_code == "MS01"
    assert collector is None


def test_leading_collector_number():
    name, _, collector = split_reference("106 Alt Cunningham — Soulkiller Architect")
    assert collector == "106"
    assert name.startswith("Alt Cunningham")


def test_bare_card_id_detected():
    _, _, collector = split_reference("A027")
    assert collector == "A027"


def test_validation_legend_count(database):
    result = parse_decklist(FORMAT_A, database, ignore_legality=True)
    errors = validate_deck(result.deck, RuleConfig())
    assert any("40" in e for e in errors)  # deck too small
    assert not any("Legends" in e for e in errors)


def test_validation_max_copies(database):
    text = "Main Deck\n4x Field Operator\n"
    result = parse_decklist(text, database, ignore_legality=True)
    errors = validate_deck(result.deck, RuleConfig())
    assert any("exceeds the maximum" in e for e in errors)


def test_ignore_legality_toggle(database):
    text = "Main Deck\n4x Field Operator\n"
    result = parse_decklist(text, database, ignore_legality=True)
    assert result.errors == []


def test_sample_deck_is_legal(parse_result):
    assert parse_result.errors == []
    assert parse_result.deck.size == 40
    assert parse_result.deck.sellable_count == 25


def test_round_trip_format(deck, database):
    text = format_deck(deck)
    again = parse_decklist(text, database)
    assert again.deck.size == deck.size
    assert again.deck.sellable_count == deck.sellable_count
