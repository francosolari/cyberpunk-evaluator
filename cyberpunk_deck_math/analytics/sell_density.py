"""Mechanical and effective sellable density, and target status."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Optional

from ..config import RuleConfig, SellableSettings
from ..methods import Method, Result
from ..models import Deck, PlayabilityProfile
from ..probability import sells

BELOW_MINIMUM = "BELOW MINIMUM"
BELOW_TARGET = "BELOW TARGET"
IN_TARGET_RANGE = "IN TARGET RANGE"
ABOVE_TARGET_RANGE = "ABOVE TARGET RANGE"


@dataclass
class SellableStatus:
    deck_size: int
    sellable_count: int
    actual_pct: float
    minimum_pct: float
    target_pct: float
    target_range: tuple[float, float]
    status: str
    cards_to_minimum: int
    cards_to_target: int
    cards_to_range_min: int
    cards_over_range_max: int
    method: Method = Method.PLAYTESTING_HEURISTIC

    def to_dict(self) -> dict:
        return {
            "deck_size": self.deck_size,
            "sellable_count": self.sellable_count,
            "actual_sellable_pct": self.actual_pct,
            "minimum_sellable_pct": self.minimum_pct,
            "target_sellable_pct": self.target_pct,
            "target_sellable_range": list(self.target_range),
            "status": self.status,
            "cards_needed_to_reach_minimum": self.cards_to_minimum,
            "cards_needed_to_reach_target": self.cards_to_target,
            "cards_needed_to_reach_range_min": self.cards_to_range_min,
            "cards_over_range_max": self.cards_over_range_max,
            "targets_method": self.method.value,
        }


def sellable_status(deck: Deck, settings: Optional[SellableSettings] = None) -> SellableStatus:
    """Compare the deck's mechanical sellable density against the configured targets."""
    settings = settings or SellableSettings()
    N = deck.size
    S = deck.sellable_count
    actual = deck.sellable_pct
    lo, hi = settings.target_range

    if actual < settings.minimum_pct:
        status = BELOW_MINIMUM
    elif actual > hi:
        status = ABOVE_TARGET_RANGE
    elif actual >= lo:
        status = IN_TARGET_RANGE
    else:
        status = BELOW_TARGET

    over = max(0, S - int(hi * N + 1e-9))
    return SellableStatus(
        deck_size=N,
        sellable_count=S,
        actual_pct=actual,
        minimum_pct=settings.minimum_pct,
        target_pct=settings.target_pct,
        target_range=settings.target_range,
        status=status,
        cards_to_minimum=sells.cards_needed(N, S, settings.minimum_pct),
        cards_to_target=sells.cards_needed(N, S, settings.target_pct),
        cards_to_range_min=sells.cards_needed(N, S, lo),
        cards_over_range_max=over,
    )


def effective_sellable_density(
    deck: Deck, profile: PlayabilityProfile, turn: int
) -> Result:
    """Sellables weighted by how willing the pilot is to sell them on ``turn``.

    ``sum(sellable(card) * sell_willingness(card, turn) * copies) / deck_size``
    """
    if deck.size == 0:
        return Result(0.0, Method.HEURISTIC_HUMAN, label=f"Effective sellable density T{turn}")
    total = sum(
        entry.copies * profile.willingness(entry.card, turn)
        for entry in deck.main
        if entry.card.is_sellable
    )
    return Result(
        value=total / deck.size,
        method=Method.HEURISTIC_HUMAN
        if profile.source.startswith("HEURISTIC — Human")
        else Method.HEURISTIC_LLM,
        label=f"Effective sellable density T{turn}",
        detail="Mechanical sellables weighted by configured sell willingness.",
        assumptions={"profile": profile.name, "turn": turn},
    )


def effective_curve(
    deck: Deck, profile: PlayabilityProfile, max_turn: int = 6
) -> dict[int, Result]:
    return {t: effective_sellable_density(deck, profile, t) for t in range(1, max_turn + 1)}


@dataclass
class SellReport:
    status: SellableStatus
    consecutive: dict[int, Result]
    misses: dict[int, Result]
    opening: Result
    effective: dict[int, Result] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status.to_dict(),
            "opening_hand_sellable": self.opening.to_dict(),
            "consecutive_sells": {f"T{t}": r.to_dict() for t, r in self.consecutive.items()},
            "missed_sell": {f"T{t}": r.to_dict() for t, r in self.misses.items()},
            "effective_sellable_density": {
                f"T{t}": r.to_dict() for t, r in self.effective.items()
            },
        }


def sell_report(
    deck: Deck,
    settings: Optional[SellableSettings] = None,
    rules: Optional[RuleConfig] = None,
    profile: Optional[PlayabilityProfile] = None,
    max_turn: int = 6,
) -> SellReport:
    rules = rules or RuleConfig()
    N, S = deck.size, deck.sellable_count
    return SellReport(
        status=sellable_status(deck, settings),
        consecutive=sells.sell_curve(N, S, max_turn, rules),
        misses=sells.miss_curve(N, S, max_turn, rules),
        opening=sells.opening_sellables(N, S, rules.opening_hand_size, 1),
        effective=effective_curve(deck, profile, max_turn) if profile else {},
    )


def target_sensitivity(
    deck: Deck,
    candidate_counts: Optional[list[int]] = None,
    max_turn: int = 6,
    rules: Optional[RuleConfig] = None,
) -> dict[int, dict[int, Result]]:
    """Sell curves for alternative sellable counts at the same deck size."""
    rules = rules or RuleConfig()
    N = deck.size
    if candidate_counts is None:
        base = deck.sellable_count
        candidate_counts = [c for c in range(base - 2, base + 4) if 0 <= c <= N]
    return sells.sensitivity(N, candidate_counts, max_turn, rules)


def pct_for_counts(deck_size: int, counts: list[int]) -> dict[int, float]:
    return {c: (c / deck_size if deck_size else 0.0) for c in counts}


def counts_for_pcts(deck_size: int, pcts: list[float]) -> dict[float, int]:
    """Exact sellable counts required to hit each percentage at this deck size."""
    return {p: min(deck_size, ceil(p * deck_size - 1e-9)) for p in pcts}
