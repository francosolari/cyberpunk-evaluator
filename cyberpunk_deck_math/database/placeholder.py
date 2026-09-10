"""A clearly-labelled placeholder card pool.

This is **not** official card data.  The official Cyberpunk TCG database at
https://cyberpunktcg.com/cards is the authoritative source, and
``python cli.py update-cards`` is how you get it.  This module exists so the
application, its tests and its demo can run before that command has been used
— for example inside a sandbox with no network access.

Every card produced here carries ``data_provenance = "placeholder"``, empty
``rules_text`` where the real text is unknown, and ``interpretation_status =
"raw"``.  The analytics layer surfaces that provenance in every report, so a
placeholder number can never be mistaken for one grounded in official data.

Costs, sellable flags and effects below are *assumptions for demonstration*,
chosen to exercise the model — not claims about the real cards.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import Card
from .cache import CardDatabase

PROVENANCE = "placeholder"
DISCLAIMER = (
    "PLACEHOLDER DATA — not the official card database. Card names of real "
    "Beta cards are used for demonstration; costs, sellable flags and effects "
    "are assumptions. Run `python cli.py update-cards` to replace this with "
    "official data from https://cyberpunktcg.com/cards."
)


def _card(
    card_id: str,
    name: str,
    *,
    cost: int | None,
    sellable: bool | None,
    type_: str,
    tags: list[str] | None = None,
    effects: list[dict[str, Any]] | None = None,
    is_legend: bool = False,
    starter_exclusive: bool | None = None,
    note: str = "",
) -> Card:
    return Card(
        card_id=card_id,
        name=name,
        collector_number=card_id.split("-")[-1],
        set_code="MS01",
        set_name="Welcome to Night City (Beta)",
        starter_exclusive=starter_exclusive,
        type=type_,
        subtype=None,
        color=None,
        cost=cost,
        ram=None,
        sellable=sellable,
        rules_text=None,  # unknown until the official database is ingested
        flavor_text=None,
        tags=tags or [],
        effect_metadata=effects or [],
        interpretation_status="raw",
        interpretation_notes=note or DISCLAIMER,
        source_url="https://cyberpunktcg.com/cards",
        database_updated_at=None,
        data_provenance=PROVENANCE,
        is_legend=is_legend,
    )


def build_placeholder_pool() -> CardDatabase:
    """The demonstration pool: four named Beta cards, three Legends, filler."""
    cards: list[Card] = [
        _card(
            "MS01-001",
            "Jackie Welles — Ride or Die Choom",
            cost=6,
            sellable=False,
            type_="Unit",
            tags=["target", "finisher"],
            note="Assumed cost 6 and non-sellable for demonstration. " + DISCLAIMER,
        ),
        _card(
            "MS01-002",
            "Field Operator",
            cost=2,
            sellable=True,
            type_="Unit",
            tags=["draw", "early"],
            effects=[
                {
                    "trigger": "on_play",
                    "effect": "draw",
                    "amount": 1,
                    "conditions": [{"type": "turn", "operator": ">=", "value": 2}],
                }
            ],
            note="Assumed conditional draw for demonstration. " + DISCLAIMER,
        ),
        _card(
            "MS01-003",
            "Zetatech Faceplate",
            cost=1,
            sellable=True,
            type_="Gear",
            tags=["early", "setup"],
        ),
        _card(
            "MS01-004",
            "Memory Relapse",
            cost=4,
            sellable=False,
            type_="Program",
            tags=["draw", "reactive"],
            effects=[
                {
                    "trigger": "on_play",
                    "effect": "draw",
                    "amount": 1,
                    "conditions": [
                        {"type": "opponent_state_proxy", "value": "valid_target"}
                    ],
                }
            ],
            note="Assumed reactive draw requiring an opposing target. " + DISCLAIMER,
        ),
        _card(
            "MS01-100",
            "Muamar Reyes — El Capitán",
            cost=0,
            sellable=False,
            type_="Legend",
            tags=["draw", "legend"],
            is_legend=True,
            starter_exclusive=True,
            effects=[
                {
                    "trigger": "on_call",
                    "effect": "draw",
                    "amount": 1,
                    "conditions": [
                        {"type": "distinct_gigs", "operator": ">=", "value": 3}
                    ],
                }
            ],
            note=(
                "Assumed conditional draw on Legend Call for demonstration. "
                + DISCLAIMER
            ),
        ),
        _card(
            "MS01-101",
            "Placeholder Legend Two",
            cost=0,
            sellable=False,
            type_="Legend",
            is_legend=True,
        ),
        _card(
            "MS01-102",
            "Placeholder Legend Three",
            cost=0,
            sellable=False,
            type_="Legend",
            is_legend=True,
        ),
    ]

    sellable_filler = [
        ("Placeholder Sellable Gig A", 1),
        ("Placeholder Sellable Gig B", 2),
        ("Placeholder Sellable Gig C", 2),
        ("Placeholder Sellable Gig D", 3),
        ("Placeholder Sellable Gig E", 1),
        ("Placeholder Sellable Gig F", 2),
        ("Placeholder Sellable Gig G", 3),
    ]
    for index, (name, cost) in enumerate(sellable_filler, start=200):
        cards.append(
            _card(
                f"MS01-{index}",
                name,
                cost=cost,
                sellable=True,
                type_="Gig",
                tags=["filler", "sellable"],
            )
        )

    nonsellable_filler = [
        ("Placeholder Reactive Program", 4, ["filler", "reactive"]),
        ("Placeholder Expensive Finisher", 5, ["filler", "finisher"]),
        ("Placeholder Utility Program", 3, ["filler"]),
        ("Placeholder Combat Unit", 3, ["filler"]),
    ]
    for index, (name, cost, tags) in enumerate(nonsellable_filler, start=300):
        cards.append(
            _card(f"MS01-{index}", name, cost=cost, sellable=False, type_="Program", tags=tags)
        )

    return CardDatabase(
        cards=cards,
        source_url="https://cyberpunktcg.com/cards",
        updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        data_provenance=PROVENANCE,
        notes=[DISCLAIMER],
    )


SAMPLE_DECK_TEXT = """# Sample constructed deck — placeholder card pool
# 40 cards, 25 mechanical sellables = 62.5%
Name: YYG Jackie (Sample)

Legends

1x Muamar Reyes — El Capitán
1x Placeholder Legend Two
1x Placeholder Legend Three

Main Deck

2x Jackie Welles — Ride or Die Choom
2x Field Operator
3x Zetatech Faceplate
3x Memory Relapse
3x Placeholder Sellable Gig A
3x Placeholder Sellable Gig B
3x Placeholder Sellable Gig C
3x Placeholder Sellable Gig D
3x Placeholder Sellable Gig E
3x Placeholder Sellable Gig F
2x Placeholder Sellable Gig G
3x Placeholder Reactive Program
3x Placeholder Expensive Finisher
2x Placeholder Utility Program
2x Placeholder Combat Unit
"""
