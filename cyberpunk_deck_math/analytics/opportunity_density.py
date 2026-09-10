"""Action / opportunity density.

``OpportunityDensity(turn) = sum(copies * strategic_playability) / deck_size``

It is the complement of dead-card burden, but reported separately because the
two answer different questions: burden asks "how much of my deck is doing
nothing", density asks "how much of my deck is doing something".
"""

from __future__ import annotations

from typing import Optional

from ..methods import Method, Result
from ..models import Deck, PlayabilityProfile


def opportunity_density(deck: Deck, profile: PlayabilityProfile, turn: int) -> Result:
    if deck.size == 0:
        return Result(0.0, Method.HEURISTIC_HUMAN, label=f"Action density T{turn}")
    total = sum(
        entry.copies * profile.strategic_playability(entry.card, turn)
        for entry in deck.main
    )
    return Result(
        value=total / deck.size,
        method=Method.HEURISTIC_HUMAN
        if profile.source.startswith("HEURISTIC — Human")
        else Method.HEURISTIC_LLM,
        label=f"Action density T{turn}",
        detail="Copy-weighted strategic playability.",
        assumptions={"profile": profile.name},
    )


def density_curve(
    deck: Deck, profile: PlayabilityProfile, max_turn: int = 6
) -> dict[int, Result]:
    return {t: opportunity_density(deck, profile, t) for t in range(1, max_turn + 1)}


def expected_playables_in_hand(
    deck: Deck, profile: PlayabilityProfile, turn: int, hand_size: Optional[int] = None,
    rules=None,
) -> Result:
    """Expected count of strategically playable cards in hand.

    A deterministic expectation from density x hand size; the simulator
    reports the observed distribution.
    """
    from ..config import RuleConfig

    rules = rules or RuleConfig()
    hand = hand_size if hand_size is not None else rules.cards_seen(turn)
    density = opportunity_density(deck, profile, turn)
    return Result(
        value=density.value * hand,
        method=density.method,
        label=f"Expected strategically playable cards among {hand} cards seen (T{turn})",
        assumptions={"hand_size": hand, "density": density.value},
    )
