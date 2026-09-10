"""Plain-English conclusions.

Numbers alone do not answer "what is the most valuable use of the next deck
slot".  These helpers turn the computed metrics into sentences that name the
tradeoff, the method behind the number, and the assumption it rests on.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..probability import sells
from .deck_summary import DeckSummary
from .marginal_value import Comparison
from .mulligan_analytics import PolicyComparisonRow
from .sell_density import (
    ABOVE_TARGET_RANGE,
    BELOW_MINIMUM,
    BELOW_TARGET,
    IN_TARGET_RANGE,
    SellableStatus,
)


def sellable_sentence(status: SellableStatus) -> str:
    base = (
        f"Your deck contains {status.sellable_count} sellables out of "
        f"{status.deck_size}, {status.actual_pct:.1%}."
    )
    if status.status == BELOW_MINIMUM:
        return (
            base
            + f" That is below the configured {status.minimum_pct:.1%} minimum: "
            f"{status.cards_to_minimum} more sellable(s) reach the minimum and "
            f"{status.cards_to_target} reach the {status.target_pct:.1%} target."
        )
    if status.status == BELOW_TARGET:
        return (
            base
            + f" This meets the configured {status.minimum_pct:.1%} minimum but is "
            f"below the {status.target_pct:.1%} target; "
            f"{status.cards_to_target} more sellable(s) would reach it."
        )
    if status.status == ABOVE_TARGET_RANGE:
        return (
            base
            + f" That is above the configured {status.target_range[0]:.1%}–"
            f"{status.target_range[1]:.1%} range, so additional sellables are "
            "unlikely to be the best use of a slot; check whether strong "
            "non-sellable effects were cut to get here."
        )
    return (
        base
        + f" The deck is already within the configured {status.target_range[0]:.1%}–"
        f"{status.target_range[1]:.1%} range, so additional sellables should be "
        "judged on whether their consistency gain offsets the loss of stronger "
        "non-sellable effects."
    )


def sell_step_sentence(
    deck_size: int, from_count: int, to_count: int, through_turn: int = 3, rules=None
) -> str:
    a = sells.consecutive_sells(deck_size, from_count, through_turn, rules).value
    b = sells.consecutive_sells(deck_size, to_count, through_turn, rules).value
    return (
        f"Moving from {from_count} to {to_count} sellables changes the probability of "
        f"completing every sell through turn {through_turn} from {a:.2%} to {b:.2%} "
        f"({(b - a) * 100:+.2f} percentage points, EXACT — Hypergeometric)."
    )


def copies_sentence(comparison: Comparison, card_name: str, turn: int = 3) -> str:
    delta_access = comparison.deltas["target_access"][turn] * 100
    delta_sell = comparison.deltas["sell_consistency"][turn] * 100
    a, b = comparison.a, comparison.b
    text = (
        f"The extra copy of {card_name} improves turn-{turn} access by "
        f"{delta_access:+.1f} percentage points"
    )
    if a.sellable_pct != b.sellable_pct:
        text += (
            f" but moves mechanical sellable density from {a.sellable_pct:.1%} to "
            f"{b.sellable_pct:.1%}, changing sell consistency through T{turn} by "
            f"{delta_sell:+.2f} points, because the replaced card was sellable"
        )
    else:
        text += (
            f" while leaving mechanical sellable density unchanged at "
            f"{b.sellable_pct:.1%} (the replaced card was not sellable)"
        )
    burden = comparison.deltas["dead_burden"][turn] * 100
    text += f". Turn-{turn} dead-card burden moves {burden:+.1f} points."
    return text


def comparison_sentence(comparison: Comparison, turn: int = 3) -> str:
    """A generic two-deck verdict for the COMPARE view."""
    a, b = comparison.a, comparison.b
    access = comparison.deltas["target_access"][turn] * 100
    sell = comparison.deltas["sell_consistency"][turn] * 100
    burden = comparison.deltas["dead_burden"][turn] * 100
    if abs(access) < 1e-9 and abs(sell) < 1e-9 and abs(burden) < 1e-9:
        return (
            f"'{b.name}' and '{a.name}' are identical on every turn-{turn} metric "
            "measured here."
        )
    return (
        f"Against '{a.name}', '{b.name}' moves turn-{turn} target access by "
        f"{access:+.1f} points, sell consistency by {sell:+.2f} points and "
        f"dead-card burden by {burden:+.1f} points, with mechanical sellable "
        f"density at {b.sellable_pct:.1%} versus {a.sellable_pct:.1%}."
    )


def mulligan_sentence(rows: Sequence[PolicyComparisonRow], turn: int = 3) -> str:
    if len(rows) < 2:
        return ""
    best_target = max(rows, key=lambda r: r.target_by_turn[turn].value)
    best_sells = max(rows, key=lambda r: r.sells_through[turn].value)
    if best_target.policy == best_sells.policy:
        return (
            f"'{best_target.policy}' leads on both axes at turn {turn}: "
            f"{best_target.target_by_turn[turn].value:.1%} target access and "
            f"{best_sells.sells_through[turn].value:.1%} sell consistency."
        )
    return (
        f"'{best_target.policy}' produces the highest turn-{turn} target rate "
        f"({best_target.target_by_turn[turn].value:.1%} vs "
        f"{best_sells.target_by_turn[turn].value:.1%} for '{best_sells.policy}'), but "
        f"'{best_sells.policy}' preserves better sell consistency "
        f"({best_sells.sells_through[turn].value:.1%} vs "
        f"{best_target.sells_through[turn].value:.1%}). Pick the axis your deck "
        "actually needs."
    )


def draw_source_sentence(
    card_name: str, expected_draws: float, target_delta_points: Optional[float] = None
) -> str:
    text = (
        f"{card_name} is technically a draw source but contributes about "
        f"{expected_draws:.2f} extra cards per game under the configured early "
        "playability profile"
    )
    if target_delta_points is not None:
        text += f", worth roughly {target_delta_points:+.1f} points of target access"
    return text + " (HEURISTIC — depends on the playability assumptions)."


def resource_sentence(card_name: str, cost: int, turn: int, probability: float) -> str:
    return (
        f"{card_name} requires {cost} usable resources by turn {turn}, and the "
        f"simulated probability of reaching {cost} usable resources is "
        f"{probability:.1%} (SIMULATED — Monte Carlo)."
    )


def summary_conclusions(
    summary: DeckSummary, targets: Sequence[str] = (), turn: int = 3
) -> list[str]:
    """The standard set of conclusions for a deck dashboard."""
    lines = [sellable_sentence(summary.sell.status)]
    status = summary.sell.status
    if status.cards_to_target:
        lines.append(
            sell_step_sentence(
                status.deck_size,
                status.sellable_count,
                min(status.deck_size, status.sellable_count + status.cards_to_target),
                turn,
            )
        )
    if summary.sell.effective:
        effective = summary.sell.effective.get(turn)
        if effective is not None:
            lines.append(
                f"Mechanically the deck is {status.actual_pct:.1%} sellable, but "
                f"effective turn-{turn} sellable density is only "
                f"{effective.value:.1%} once sell willingness is applied — that gap "
                "is the part of your sellable count you cannot comfortably give up."
            )
    if summary.dead_burden.get(turn):
        lines.append(
            f"By turn {turn}, {summary.dead_burden[turn].value:.1%} of the deck is "
            f"dead weight and {summary.action_density[turn].value:.1%} is doing "
            f"something ({summary.profile_source})."
        )
    for name in targets:
        curve = summary.target_access.get(name)
        if curve:
            key = f"T{turn}"
            if key in curve:
                lines.append(
                    f"Raw access to {name} by turn {turn} is {curve[key].value:.1%} "
                    "(EXACT — Hypergeometric); playing it is a strictly smaller number."
                )
    return lines
