"""Sell-consistency mathematics.

``P(sell every turn through T)`` is deliberately *not* the same thing as
``P(draw at least T sellables by turn T)``: selling is sequential, so a hand
that finds three sellables on turn 3 cannot retroactively sell on turn 1.
This module computes the sequential version exactly with a small dynamic
program over the draw order, and reports the weaker "at least k" version
separately so the difference is visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Optional, Sequence

from ..config import RuleConfig
from ..methods import Method, Result
from . import hypergeom


def opening_sellables(N: int, S: int, hand: int, k: int = 1) -> Result:
    """P(at least ``k`` sellables in the opening hand)."""
    return Result(
        value=hypergeom.at_least(N, S, hand, k),
        method=Method.EXACT_HYPERGEOMETRIC,
        label=f"P(>= {k} sellable in opening hand)",
        assumptions={"deck_size": N, "sellables": S, "hand_size": hand},
    )


def at_least_k_sellables_by_turn(
    N: int, S: int, turn: int, rules: Optional[RuleConfig] = None, k: Optional[int] = None
) -> Result:
    """P(at least ``k`` sellables among all cards seen by ``turn``).

    This is the *weak* form.  It ignores draw order, so it over-states real
    sell consistency; :func:`consecutive_sells` is the honest number.
    """
    rules = rules or RuleConfig()
    seen = rules.cards_seen(turn)
    k = turn if k is None else k
    return Result(
        value=hypergeom.at_least(N, S, seen, k),
        method=Method.EXACT_HYPERGEOMETRIC,
        label=f"P(>= {k} sellables seen by T{turn})",
        detail="Ignores draw order; not a sell-consistency guarantee.",
        assumptions={"deck_size": N, "sellables": S, "cards_seen": seen},
    )


def _sequential_success(
    N: int, S: int, hand: int, turns: int, sells_per_turn: int, draws_per_turn: int,
    draw_on_first_turn: bool,
) -> Fraction:
    """Exact P(a sellable is available for every scheduled sell through ``turns``).

    Dynamic program over ``(cards drawn, sellables drawn)``.  Cards are
    exchangeable, so drawing one at a time and tracking the running counts is
    exact.  ``sold`` is implied by the turn index: by the end of turn ``t`` the
    pilot has sold ``t * sells_per_turn`` cards, which requires that many
    sellables to have been seen.
    """
    if N <= 0 or turns <= 0:
        return Fraction(1)
    if hand + turns * draws_per_turn > N:
        raise ValueError("deck runs out of cards before the requested turn")

    # states: {sellables_seen: probability}, after `drawn` cards.
    states: dict[int, Fraction] = {0: Fraction(1)}
    drawn = 0

    def draw_one(states: dict[int, Fraction], drawn: int) -> dict[int, Fraction]:
        nxt: dict[int, Fraction] = {}
        remaining = N - drawn
        for s, p in states.items():
            good = Fraction(S - s, remaining)
            if good > 0:
                nxt[s + 1] = nxt.get(s + 1, Fraction(0)) + p * good
            bad = 1 - good
            if bad > 0:
                nxt[s] = nxt.get(s, Fraction(0)) + p * bad
        return nxt

    for _ in range(hand):
        states = draw_one(states, drawn)
        drawn += 1

    for turn in range(1, turns + 1):
        n_draws = draws_per_turn
        if turn == 1 and not draw_on_first_turn:
            n_draws = 0
        for _ in range(n_draws):
            states = draw_one(states, drawn)
            drawn += 1
        needed = turn * sells_per_turn
        states = {s: p for s, p in states.items() if s >= needed}
        if not states:
            return Fraction(0)
    return sum(states.values(), Fraction(0))


def consecutive_sells(
    N: int,
    S: int,
    through_turn: int,
    rules: Optional[RuleConfig] = None,
    sells_per_turn: Optional[int] = None,
) -> Result:
    """P(the pilot can sell on every turn 1..``through_turn``).

    Raw-access only: it assumes every sellable card drawn is one the pilot is
    willing to sell.  Sell *willingness*, cards already played, and cards
    consumed by other effects are modelled in the Monte Carlo simulator, not
    here.
    """
    rules = rules or RuleConfig()
    sells = sells_per_turn if sells_per_turn is not None else rules.max_sells_per_turn
    value = float(
        _sequential_success(
            N,
            S,
            rules.opening_hand_size,
            through_turn,
            sells,
            rules.natural_draws_per_turn,
            rules.draw_on_first_turn,
        )
    )
    return Result(
        value=value,
        method=Method.EXACT_HYPERGEOMETRIC,
        label=f"P(sell every turn through T{through_turn})",
        detail=(
            "Sequential: requires a sellable to be in hand at each sell. "
            "Assumes full willingness to sell; see effective sellable density."
        ),
        assumptions={
            "deck_size": N,
            "sellables": S,
            "opening_hand_size": rules.opening_hand_size,
            "sells_per_turn": sells,
            "draws_per_turn": rules.natural_draws_per_turn,
        },
    )


def sell_curve(
    N: int, S: int, max_turn: int = 6, rules: Optional[RuleConfig] = None
) -> dict[int, Result]:
    """Consecutive-sell probability for turns 1..``max_turn``."""
    rules = rules or RuleConfig()
    return {t: consecutive_sells(N, S, t, rules) for t in range(1, max_turn + 1)}


def miss_curve(
    N: int, S: int, max_turn: int = 6, rules: Optional[RuleConfig] = None
) -> dict[int, Result]:
    """P(at least one missed sell by turn T) = 1 - consecutive-sell."""
    out: dict[int, Result] = {}
    for turn, res in sell_curve(N, S, max_turn, rules).items():
        out[turn] = Result(
            value=1.0 - res.value,
            method=res.method,
            label=f"P(miss at least one sell through T{turn})",
            assumptions=res.assumptions,
        )
    return out


@dataclass
class DensityRow:
    sellables: int
    pct: float
    by_turn: dict[int, Result]


def density_table(
    N: int,
    sellable_counts: Optional[Sequence[int]] = None,
    max_turn: int = 6,
    rules: Optional[RuleConfig] = None,
) -> list[DensityRow]:
    """The sell-consistency reference table for a deck of size ``N``.

    Defaults to the 50%–70% band, which for a 40-card deck is 20–28
    sellables.  For other legal deck sizes the equivalent band is computed
    dynamically.
    """
    rules = rules or RuleConfig()
    if sellable_counts is None:
        lo = int(round(0.50 * N))
        hi = int(round(0.70 * N))
        sellable_counts = list(range(lo, hi + 1))
    rows: list[DensityRow] = []
    for S in sellable_counts:
        if S > N:
            continue
        rows.append(
            DensityRow(
                sellables=S,
                pct=S / N if N else 0.0,
                by_turn=sell_curve(N, S, max_turn, rules),
            )
        )
    return rows


def sensitivity(
    N: int,
    sellable_counts: Sequence[int],
    max_turn: int = 6,
    rules: Optional[RuleConfig] = None,
) -> dict[int, dict[int, Result]]:
    """Sell curves for a set of candidate sellable counts, for comparison."""
    rules = rules or RuleConfig()
    return {S: sell_curve(N, S, max_turn, rules) for S in sellable_counts}


def cards_needed(N: int, S: int, pct: float) -> int:
    """Additional sellables required to reach ``pct`` at fixed deck size.

    Swapping a non-sellable for a sellable keeps ``N`` constant, so the answer
    is ``ceil(pct * N) - S`` clamped at zero.
    """
    from math import ceil

    need = ceil(pct * N - 1e-9) - S
    return max(0, min(need, N - S))
