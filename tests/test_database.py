"""Card database: normalization, pool filtering, caching and matching."""

from __future__ import annotations

import json

import pytest

from cyberpunk_deck_math.database.cache import CardDatabase
from cyberpunk_deck_math.database.fetch_official import FetchError, fetch_payload, update_cards
from cyberpunk_deck_math.database.normalize import (
    normalize_record,
    normalize_records,
    unwrap_payload,
)
from cyberpunk_deck_math.database.validate_pool import filter_pool, is_beta, is_unreleased
from cyberpunk_deck_math.models import Card


def test_normalize_uses_field_aliases():
    card = normalize_record(
        {"id": "MS01-131", "title": "Test Card", "play_cost": 3, "can_sell": "yes",
         "oracle_text": "Draw 1.", "setCode": "MS01"}
    )
    assert card.card_id == "MS01-131"
    assert card.name == "Test Card"
    assert card.cost == 3
    assert card.sellable is True
    assert card.rules_text == "Draw 1."


def test_missing_fields_stay_none_not_guessed():
    card = normalize_record({"name": "Sparse"})
    assert card.cost is None
    assert card.sellable is None
    assert card.rules_text is None
    assert card.starter_exclusive is None


def test_unparseable_boolean_is_none():
    card = normalize_record({"name": "X", "sellable": "maybe"})
    assert card.sellable is None


def test_legend_detection_from_type():
    assert normalize_record({"name": "L", "type": "Legend"}).is_legend is True
    assert normalize_record({"name": "U", "type": "Unit"}).is_legend is False


def test_records_without_names_become_warnings():
    cards, warnings = normalize_records([{"name": "ok"}, {"cost": 3}])
    assert len(cards) == 1 and len(warnings) == 1


def test_unwrap_payload_finds_the_card_list():
    assert len(unwrap_payload({"cards": [{"name": "a"}]})) == 1
    assert len(unwrap_payload([{"name": "a"}])) == 1
    assert len(unwrap_payload({"x": {"name": "a"}})) == 1
    with pytest.raises(ValueError):
        unwrap_payload({"total": 5})


def test_pool_filter_keeps_beta_and_starter_exclusives():
    beta = Card(card_id="1", name="Beta", set_code="MS01")
    starter = Card(card_id="2", name="Starter", set_code="SD01", starter_exclusive=True)
    future = Card(card_id="3", name="Future", set_code="MS02", set_name="Second Set")
    preview = Card(card_id="4", name="Preview", set_code="MS01", tags=["preview"])
    result = filter_pool([beta, starter, future, preview])
    kept = {c.name for c in result.kept}
    assert kept == {"Beta", "Starter"}
    assert len(result.dropped) == 2
    assert any("not released" in reason for _, reason in result.dropped)


def test_beta_detection_by_set_name():
    assert is_beta(Card(card_id="1", name="x", set_name="Welcome to Night City Beta"))
    assert not is_beta(Card(card_id="1", name="x", set_name="Some Other Set"))


def test_unreleased_markers():
    assert is_unreleased(Card(card_id="1", name="x", tags=["spoiler"]))
    assert not is_unreleased(Card(card_id="1", name="x", tags=["gig"]))


def test_cache_json_round_trip(tmp_path, database):
    path = tmp_path / "cards.json"
    database.save(path)
    again = CardDatabase.load(path)
    assert len(again) == len(database)
    assert again.get("Field Operator").cost == database.get("Field Operator").cost
    assert again.data_provenance == database.data_provenance


def test_cache_csv_round_trip(tmp_path, database):
    path = tmp_path / "cards.csv"
    database.save(path)
    again = CardDatabase.load(path)
    assert len(again) == len(database)
    card = again.get("Muamar Reyes — El Capitán")
    assert card.is_legend is True
    assert card.effect_metadata and card.effect_metadata[0]["effect"] == "draw"


def test_missing_cache_message_points_at_the_update_command(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        CardDatabase.load(tmp_path / "nope.json")
    assert "update-cards" in str(exc.value)


def test_match_by_name_id_and_collector(database):
    assert database.match("Field Operator").card is not None
    assert database.match("MS01-002").card.name == "Field Operator"
    assert database.match("Zetatech Faceplate", collector="003").card is not None


def test_match_reports_unknown_reason(database):
    result = database.match("Not A Real Card")
    assert result.card is None and "not found" in result.reason


def test_ambiguous_match_is_reported(tmp_path):
    cards = [
        Card(card_id="a", name="Twin Card", set_code="MS01"),
        Card(card_id="b", name="Twin Card", set_code="SD01", starter_exclusive=True),
    ]
    database = CardDatabase(cards=cards)
    result = database.match("Twin Card")
    assert result.ambiguous
    assert len(result.candidates) == 2
    assert database.match("Twin Card", set_code="SD01").card.card_id == "b"


def test_prefix_match_resolves_subtitled_names(database):
    result = database.match("Jackie Welles")
    assert result.card is not None
    assert "prefix" in result.reason


def test_interpretations_survive_a_database_refresh(database):
    fresh = CardDatabase(cards=[Card.from_dict(c.to_dict()) for c in database.cards])
    previous = CardDatabase(cards=[Card.from_dict(c.to_dict()) for c in database.cards])
    card = previous.get("Field Operator")
    card.effect_metadata = [{"trigger": "on_play", "effect": "draw", "amount": 2}]
    card.interpretation_status = "human_verified"
    carried = fresh.merge_interpretations(previous)
    assert carried == 1
    assert fresh.get("Field Operator").effect_metadata[0]["amount"] == 2


def test_update_cards_from_a_local_file(tmp_path):
    payload = {
        "cards": [
            {"id": "MS01-900", "name": "Local Beta Card", "set_code": "MS01",
             "cost": 2, "sellable": True, "text": "Draw 1."},
            {"id": "MS02-1", "name": "Future Card", "set_code": "MS02"},
        ]
    }
    source = tmp_path / "payload.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    cache = tmp_path / "cards_beta.json"
    database, report = update_cards(cache_path=cache, source_file=source)
    assert len(database) == 1
    assert database.get("Local Beta Card").rules_text == "Draw 1."
    assert report.kept == 1 and report.raw_records == 2
    assert cache.exists()
    assert database.data_provenance == "official"


def test_fetch_failure_explains_how_to_fix(tmp_path):
    with pytest.raises(FetchError) as exc:
        fetch_payload(source_url="http://127.0.0.1:9/none.json", timeout=0.2)
    message = str(exc.value)
    assert "--source-file" in message and "CYBERPUNK_TCG_CARDS_URL" in message


def test_placeholder_pool_is_labelled(database):
    assert database.data_provenance == "placeholder"
    assert all(card.data_provenance == "placeholder" for card in database)
    assert all(card.rules_text is None for card in database)
