"""Dead-card burden.

``deadness(card, turn) = 1 - strategic_playability(card, turn)``

Weighted burden is the copy-weighted average deadness across the deck.  The
burden is also broken into categories so "30% dead on turn 2" can be read as
"mostly expensive cards" rather than "mostly reactive cards".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..methods import Method, Result
from ..models import Card, Deck, PlayabilityProfile

CATEGORIES = (
    "expensive",
    "reactive",
    "redundant",
    "setup_without_payoff",
    "payoff_without_setup",
    "currently_unplayable",
    "target_held",
    "resource_conflict",
)


@dataclass
class BurdenBreakdown:
    turn: int
    total: float
    by_category: dict[str, float] = field(default_factory=dict)
    by_card: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "dead_card_burden": self.total,
            "by_category": self.by_category,
            "by_card": self.by_card,
        }


def categorize(
    card: Card,
    turn: int,
    profile: PlayabilityProfile,
    deck: Deck,
    target_names: tuple[str, ...] = (),
    expensive_cost: int = 4,
) -> str:
    """Best-fit reason this card is dead on this turn."""
    from ..models import normalize_name

    if card.key in {normalize_name(n) for n in target_names}:
        return "target_held"
    if profile.legal_playability(card, turn) <= 0.0:
        if card.cost is not None and card.cost >= expensive_cost:
            return "expensive"
        return "currently_unplayable"
    if card.has_tag("reactive"):
        return "reactive"
    if card.has_tag("setup"):
        return "setup_without_payoff"
    if card.has_tag("finisher") or card.has_tag("payoff"):
        return "payoff_without_setup"
    if deck.copies_of(card.name) >= 3:
        return "redundant"
    if card.cost is not None and card.cost > turn:
        return "resource_conflict"
    return "currently_unplayable"


def dead_card_burden(
    deck: Deck,
    profile: PlayabilityProfile,
    turn: int,
    target_names: tuple[str, ...] = (),
) -> BurdenBreakdown:
    if deck.size == 0:
        return BurdenBreakdown(turn=turn, total=0.0)
    total = 0.0
    by_category: dict[str, float] = {}
    by_card: dict[str, float] = {}
    for entry in deck.main:
        deadness = 1.0 - profile.strategic_playability(entry.card, turn)
        weighted = entry.copies * deadness / deck.size
        total += weighted
        by_card[entry.card.name] = deadness
        if deadness > 0:
            category = categorize(entry.card, turn, profile, deck, target_names)
            by_category[category] = by_category.get(category, 0.0) + weighted
    return BurdenBreakdown(turn=turn, total=total, by_category=by_category, by_card=by_card)


def burden_curve(
    deck: Deck,
    profile: PlayabilityProfile,
    max_turn: int = 6,
    target_names: tuple[str, ...] = (),
) -> dict[int, Result]:
    out: dict[int, Result] = {}
    for turn in range(1, max_turn + 1):
        breakdown = dead_card_burden(deck, profile, turn, target_names)
        out[turn] = Result(
            value=breakdown.total,
            method=Method.HEURISTIC_HUMAN
            if profile.source.startswith("HEURISTIC — Human")
            else Method.HEURISTIC_LLM,
            label=f"Dead-card burden T{turn}",
            detail="1 - strategic playability, copy-weighted.",
            assumptions={"profile": profile.name, "categories": breakdown.by_category},
        )
    return out


def low_playability_share(
    deck: Deck, profile: PlayabilityProfile, turn: int, cutoff: float = 0.10
) -> float:
    """Share of the deck whose strategic playability is below ``cutoff``."""
    if deck.size == 0:
        return 0.0
    return (
        sum(
            entry.copies
            for entry in deck.main
            if profile.strategic_playability(entry.card, turn) < cutoff
        )
        / deck.size
    )
