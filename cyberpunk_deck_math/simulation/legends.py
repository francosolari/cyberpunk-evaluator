"""Legend handling.

Legends sit outside the main deck.  Their order is randomized each game, they
may be Called once per turn, and they can instead be spent for resources — a
real tension the simulator tracks rather than assuming away.
"""

from __future__ import annotations

import random
from typing import Optional, Sequence

from ..config import RuleConfig
from ..effects.generic import apply_effect, card_effects
from ..models import Card
from .state import GameState, LegendState


def setup_legends(cards: Sequence[Card], rng: random.Random) -> list[LegendState]:
    order = list(cards)
    rng.shuffle(order)
    return [LegendState(card=card) for card in order]


def call_legend(state: GameState, legend: LegendState) -> list[dict]:
    """Call a Legend, applying its ``on_call`` effects.

    Calling uses the Legend for the turn, so its resource value is no longer
    available — that is the conflict between drawing and paying for a big turn.
    """
    if not legend.ready or legend.spent or legend.called_this_turn:
        return []
    legend.called_this_turn = True
    legend.ready = False
    legend.face_up = True
    state.actions.append(f"T{state.turn}: called {legend.card.name}")
    effects = card_effects(legend.card, "on_call")
    if not effects:
        return []
    context = state.context()
    return [apply_effect(effect, state, context) for effect in effects]


def legend_calls_remaining(state: GameState, rules: RuleConfig) -> int:
    used = sum(1 for legend in state.legends if legend.called_this_turn)
    return max(0, rules.max_legend_calls_per_turn - used)


def best_call_candidate(state: GameState) -> Optional[LegendState]:
    """The readiest Legend with an applicable ``on_call`` effect, if any."""
    context: Optional[dict] = None
    for legend in state.legends:
        if not legend.ready or legend.spent or legend.called_this_turn:
            continue
        effects = card_effects(legend.card, "on_call")
        if not effects:
            continue
        if context is None:
            context = state.context()
        for effect in effects:
            if effect.is_active(context, unknown_is=False):
                return legend
    return None
