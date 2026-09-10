"""Normalization of raw official card records.

The official database's exact JSON field names are not guaranteed to be
stable, so normalization is driven by an alias table rather than one hard-coded
shape.  Anything the source does not provide stays ``None`` — the application
never invents a value.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional

from ..models import Card

#: Normalized field -> candidate keys in the raw record, in priority order.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "card_id": ("card_id", "id", "cardId", "uuid", "slug", "code"),
    "name": ("name", "title", "card_name", "cardName"),
    "collector_number": (
        "collector_number",
        "collectorNumber",
        "number",
        "card_number",
        "cardNumber",
    ),
    "set_code": ("set_code", "setCode", "set", "expansion_code", "setId"),
    "set_name": ("set_name", "setName", "expansion", "set_title"),
    "starter_exclusive": (
        "starter_exclusive",
        "starterExclusive",
        "is_starter_exclusive",
        "starter_deck_exclusive",
    ),
    "type": ("type", "card_type", "cardType"),
    "subtype": ("subtype", "sub_type", "subType", "subtypes"),
    "color": ("color", "colour", "faction"),
    "cost": ("cost", "eddies_cost", "play_cost", "eddieCost"),
    "ram": ("ram", "ram_cost", "ramCost"),
    "sellable": ("sellable", "is_sellable", "can_sell", "sell"),
    "rules_text": ("rules_text", "text", "effect", "ability", "oracle_text", "rulesText"),
    "flavor_text": ("flavor_text", "flavour_text", "flavor", "flavorText"),
    "tags": ("tags", "keywords", "traits", "labels"),
    "source_url": ("source_url", "url", "permalink", "link"),
    "rarity": ("rarity",),
}

BOOL_TRUE = {"true", "yes", "y", "1", "sellable"}
BOOL_FALSE = {"false", "no", "n", "0", "non-sellable", "not sellable"}

LEGEND_TYPES = {"legend", "legends"}


def _first(record: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _as_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in BOOL_TRUE:
        return True
    if text in BOOL_FALSE:
        return False
    return None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"-?\d+", str(value))
    return int(match.group()) if match else None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;|/]", value)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]


def normalize_record(
    record: Mapping[str, Any],
    source_url: Optional[str] = None,
    updated_at: Optional[str] = None,
    provenance: str = "official",
) -> Card:
    """Convert one raw record into a :class:`Card`."""
    name = _first(record, FIELD_ALIASES["name"])
    if not name:
        raise ValueError(f"record has no recognizable name field: {sorted(record)[:8]}")
    card_id = _first(record, FIELD_ALIASES["card_id"])
    collector = _first(record, FIELD_ALIASES["collector_number"])
    set_code = _first(record, FIELD_ALIASES["set_code"])
    if not card_id:
        card_id = "-".join(str(p) for p in (set_code, collector) if p) or str(name)
    card_type = _first(record, FIELD_ALIASES["type"])
    tags = _as_list(_first(record, FIELD_ALIASES["tags"]))
    rarity = _first(record, FIELD_ALIASES["rarity"])
    if rarity:
        tags = tags + [f"rarity:{rarity}"]

    return Card(
        card_id=str(card_id),
        name=str(name),
        collector_number=str(collector) if collector is not None else None,
        set_code=str(set_code) if set_code else None,
        set_name=(lambda v: str(v) if v else None)(_first(record, FIELD_ALIASES["set_name"])),
        starter_exclusive=_as_bool(_first(record, FIELD_ALIASES["starter_exclusive"])),
        type=str(card_type) if card_type else None,
        subtype=(lambda v: ", ".join(_as_list(v)) or None)(
            _first(record, FIELD_ALIASES["subtype"])
        ),
        color=(lambda v: str(v) if v else None)(_first(record, FIELD_ALIASES["color"])),
        cost=_as_int(_first(record, FIELD_ALIASES["cost"])),
        ram=_as_int(_first(record, FIELD_ALIASES["ram"])),
        sellable=_as_bool(_first(record, FIELD_ALIASES["sellable"])),
        rules_text=(lambda v: str(v) if v else None)(
            _first(record, FIELD_ALIASES["rules_text"])
        ),
        flavor_text=(lambda v: str(v) if v else None)(
            _first(record, FIELD_ALIASES["flavor_text"])
        ),
        tags=tags,
        effect_metadata=[],
        interpretation_status="raw",
        source_url=(lambda v: str(v) if v else source_url)(
            _first(record, FIELD_ALIASES["source_url"])
        ),
        database_updated_at=updated_at,
        data_provenance=provenance,
        is_legend=bool(card_type and str(card_type).strip().lower() in LEGEND_TYPES),
    )


def normalize_records(
    records: Iterable[Mapping[str, Any]],
    source_url: Optional[str] = None,
    updated_at: Optional[str] = None,
    provenance: str = "official",
) -> tuple[list[Card], list[str]]:
    """Normalize many records, collecting per-record problems as warnings."""
    cards: list[Card] = []
    warnings: list[str] = []
    for index, record in enumerate(records):
        try:
            cards.append(normalize_record(record, source_url, updated_at, provenance))
        except ValueError as exc:
            warnings.append(f"record {index}: {exc}")
    return cards, warnings


def unwrap_payload(payload: Any) -> list[Mapping[str, Any]]:
    """Find the list of card records inside an arbitrary JSON payload."""
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("cards", "data", "results", "items", "records"):
            if isinstance(payload.get(key), list):
                return [p for p in payload[key] if isinstance(p, Mapping)]
        # A dict keyed by card id also occurs in community exports.
        values = list(payload.values())
        if values and all(isinstance(v, Mapping) for v in values):
            return values  # type: ignore[return-value]
    raise ValueError(
        "could not find a list of card records in the payload; pass --json-path "
        "to point at the right key"
    )
