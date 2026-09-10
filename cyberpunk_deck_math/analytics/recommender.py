"""Sellable slot recommender.

Answers "which non-sellable cards could become sellables to reach my target,
and what would that cost me?"  Being non-sellable is never on its own a reason
to cut a card: the ranking is driven by strategic contribution, and the cost of
every suggested cut is shown next to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from ..config import SellableSettings
from ..methods import Method
from ..models import Card, Deck, PlayabilityProfile
from . import dead_cards, sell_density


@dataclass
class CutCandidate:
    name: str
    copies: int
    cost: Optional[int]
    early_strategic: float
    dead_burden_share: float
    redundancy: int
    tags: list[str]
    score: float
    tradeoff: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "card": self.name,
            "copies": self.copies,
            "cost": self.cost,
            "strategic_playability_early": self.early_strategic,
            "dead_card_burden_share": self.dead_burden_share,
            "copies_in_deck": self.redundancy,
            "tags": self.tags,
            "cut_score": self.score,
            "tradeoff": self.tradeoff,
        }


@dataclass
class Recommendation:
    status: sell_density.SellableStatus
    cards_to_minimum: int
    cards_to_target: int
    candidates: list[CutCandidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    method: str = Method.PLAYTESTING_HEURISTIC.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.to_dict(),
            "cards_needed_to_reach_minimum": self.cards_to_minimum,
            "cards_needed_to_reach_target": self.cards_to_target,
            "candidates": [c.to_dict() for c in self.candidates],
            "notes": self.notes,
            "method": self.method,
        }


def recommend_sellable_swaps(
    deck: Deck,
    profile: PlayabilityProfile,
    settings: Optional[SellableSettings] = None,
    target_names: Sequence[str] = (),
    early_turn: int = 3,
    max_candidates: int = 10,
) -> Recommendation:
    """Rank the non-sellable cards whose slots are cheapest to convert."""
    settings = settings or SellableSettings()
    status = sell_density.sellable_status(deck, settings)
    burden = dead_cards.dead_card_burden(deck, profile, early_turn, tuple(target_names))

    candidates: list[CutCandidate] = []
    protected = {t.lower() for t in target_names}
    for entry in deck.main:
        card = entry.card
        if card.is_sellable:
            continue
        if card.name.lower() in protected:
            continue
        strategic = profile.strategic_playability(card, early_turn)
        deadness = 1.0 - strategic
        share = entry.copies * deadness / deck.size if deck.size else 0.0
        # Higher score = cheaper to cut. Low early impact, high deadness and
        # redundancy raise it; a unique low-cost enabler keeps it low.
        score = (
            2.0 * deadness
            + 0.5 * share * 10
            + 0.3 * max(0, entry.copies - 2)
            + (0.3 if card.has_tag("filler") else 0.0)
            - 0.5 * strategic
        )
        tradeoff = _tradeoff_note(card, strategic, entry.copies)
        candidates.append(
            CutCandidate(
                name=card.name,
                copies=entry.copies,
                cost=card.cost,
                early_strategic=strategic,
                dead_burden_share=share,
                redundancy=entry.copies,
                tags=list(card.tags),
                score=score,
                tradeoff=tradeoff,
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    notes: list[str] = []
    if status.status == sell_density.ABOVE_TARGET_RANGE:
        notes.append(
            f"The deck is {status.actual_pct:.1%} sellable, above the configured "
            f"{status.target_range[0]:.1%}–{status.target_range[1]:.1%} range. Check "
            "whether strategically valuable non-sellable effects have been cut; "
            "adding sellables here is unlikely to be the best use of a slot."
        )
    elif status.cards_to_minimum == 0 and status.cards_to_target == 0:
        notes.append(
            "The deck already meets the configured minimum and target. Judge further "
            "sellables on whether their consistency gain beats the effect being cut."
        )
    else:
        notes.append(
            f"{status.cards_to_minimum} more sellable(s) reach the "
            f"{status.minimum_pct:.1%} minimum; {status.cards_to_target} reach the "
            f"{status.target_pct:.1%} target."
        )
    notes.append(
        "Ranking is a heuristic over strategic playability, dead-card burden and "
        "redundancy — not an instruction. Non-sellable cards are never ranked "
        "for being non-sellable alone."
    )

    return Recommendation(
        status=status,
        cards_to_minimum=status.cards_to_minimum,
        cards_to_target=status.cards_to_target,
        candidates=candidates[:max_candidates],
        notes=notes,
    )


def _tradeoff_note(card: Card, strategic: float, copies: int) -> str:
    parts = []
    if strategic >= 0.5:
        parts.append(f"active in ~{strategic:.0%} of turn-3 states — a real cost to cut")
    elif strategic > 0:
        parts.append(f"only ~{strategic:.0%} strategically playable by turn 3")
    else:
        parts.append("does nothing by turn 3 under the configured profile")
    if card.has_tag("finisher"):
        parts.append("cutting it lowers your top end")
    if card.has_tag("reactive"):
        parts.append("its value depends on the opponent's board (proxy assumption)")
    if copies >= 3:
        parts.append(f"{copies} copies, so trimming one keeps access to the effect")
    return "; ".join(parts)
