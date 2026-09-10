"""Marginal slot value: what one deck slot is actually worth.

Every comparison holds deck size constant — the question is never "should I
add a card", it is "what should this slot be".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from ..config import RuleConfig
from ..models import Card, Deck, PlayabilityProfile
from ..probability import sells
from . import access, dead_cards, opportunity_density, sell_density


@dataclass
class DeckMetrics:
    """The metric bundle compared between two builds."""

    name: str
    deck_size: int
    sellable_count: int
    sellable_pct: float
    effective_sellable: dict[int, float]
    target_access: dict[int, float]
    sell_consistency: dict[int, float]
    dead_burden: dict[int, float]
    action_density: dict[int, float]
    target_and_resources: dict[int, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "deck_size": self.deck_size,
            "sellable_count": self.sellable_count,
            "mechanical_sellable_pct": self.sellable_pct,
            "effective_sellable_pct": {f"T{t}": v for t, v in self.effective_sellable.items()},
            "target_access": {f"T{t}": v for t, v in self.target_access.items()},
            "sell_consistency": {f"T{t}": v for t, v in self.sell_consistency.items()},
            "dead_card_burden": {f"T{t}": v for t, v in self.dead_burden.items()},
            "action_density": {f"T{t}": v for t, v in self.action_density.items()},
            "target_and_sellables": {f"T{t}": v for t, v in self.target_and_resources.items()},
        }


def deck_metrics(
    deck: Deck,
    target_name: str,
    profile: PlayabilityProfile,
    rules: Optional[RuleConfig] = None,
    max_turn: int = 6,
    sellables_needed_for_target: Optional[int] = None,
) -> DeckMetrics:
    rules = rules or RuleConfig()
    turns = range(1, max_turn + 1)
    entry = deck.find(target_name)
    if entry is None:
        raise KeyError(f"{target_name} is not in {deck.name}")
    # Canonicalize: callers may pass a prefix, an id or a collector number.
    target_name = entry.card.name
    cost = entry.card.cost if entry.card.cost is not None else 0
    needed = (
        sellables_needed_for_target
        if sellables_needed_for_target is not None
        else cost
    )
    return DeckMetrics(
        name=deck.name,
        deck_size=deck.size,
        sellable_count=deck.sellable_count,
        sellable_pct=deck.sellable_pct,
        effective_sellable={
            t: sell_density.effective_sellable_density(deck, profile, t).value for t in turns
        },
        target_access={
            t: access.raw_access(deck, target_name, t, rules).value for t in turns
        },
        sell_consistency={
            t: sells.consecutive_sells(deck.size, deck.sellable_count, t, rules).value
            for t in turns
        },
        dead_burden={
            t: dead_cards.dead_card_burden(deck, profile, t, (target_name,)).total
            for t in turns
        },
        action_density={
            t: opportunity_density.opportunity_density(deck, profile, t).value for t in turns
        },
        target_and_resources={
            t: access.target_and_sellables(deck, target_name, t, needed, rules).value
            for t in turns
        },
    )


@dataclass
class Comparison:
    a: DeckMetrics
    b: DeckMetrics
    deltas: dict[str, dict[int, float]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant_a": self.a.to_dict(),
            "variant_b": self.b.to_dict(),
            "deltas": {k: {f"T{t}": v for t, v in inner.items()} for k, inner in self.deltas.items()},
            "notes": self.notes,
            "method": "EXACT for access/sell consistency; HEURISTIC for playability-derived metrics",
        }


def compare_metrics(a: DeckMetrics, b: DeckMetrics) -> Comparison:
    keys = (
        "effective_sellable",
        "target_access",
        "sell_consistency",
        "dead_burden",
        "action_density",
        "target_and_resources",
    )
    deltas = {
        key: {
            turn: getattr(b, key)[turn] - getattr(a, key)[turn]
            for turn in getattr(a, key)
        }
        for key in keys
    }
    notes = []
    if a.sellable_pct != b.sellable_pct:
        notes.append(
            f"Mechanical sellable density moves from {a.sellable_pct:.1%} to "
            f"{b.sellable_pct:.1%} ({a.sellable_count} -> {b.sellable_count} sellables)."
        )
    if a.deck_size != b.deck_size:
        notes.append(
            f"WARNING: deck sizes differ ({a.deck_size} vs {b.deck_size}); "
            "slot comparisons assume a constant deck size."
        )
    return Comparison(a=a, b=b, deltas=deltas, notes=notes)


def compare_decks(
    deck_a: Deck,
    deck_b: Deck,
    target_name: str,
    profile: PlayabilityProfile,
    rules: Optional[RuleConfig] = None,
    max_turn: int = 6,
) -> Comparison:
    return compare_metrics(
        deck_metrics(deck_a, target_name, profile, rules, max_turn),
        deck_metrics(deck_b, target_name, profile, rules, max_turn),
    )


def swap_slot(
    deck: Deck,
    remove: str,
    add: Card,
    target_name: str,
    profile: PlayabilityProfile,
    rules: Optional[RuleConfig] = None,
    max_turn: int = 6,
    count: int = 1,
) -> Comparison:
    """Remove ``count`` copies of one card, add the same number of another."""
    variant = deck.with_swap(remove, add, count)
    return compare_decks(deck, variant, target_name, profile, rules, max_turn)


def compare_copies(
    deck: Deck,
    card_name: str,
    filler: Card,
    profile: PlayabilityProfile,
    counts: Sequence[int] = (2, 3),
    rules: Optional[RuleConfig] = None,
    max_turn: int = 6,
) -> Comparison:
    """The "2 vs 3 copies" shortcut, trading against a filler card."""
    a = deck.with_copies(card_name, counts[0], filler)
    b = deck.with_copies(card_name, counts[1], filler)
    return compare_decks(a, b, card_name, profile, rules, max_turn)
