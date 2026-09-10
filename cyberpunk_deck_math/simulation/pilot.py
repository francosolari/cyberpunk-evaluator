"""The simulated pilot.

The pilot makes the decisions the exact math cannot: which sellable to give
up, whether to Call a Legend or hold it for resources, and whether a legal
play is actually the right play.  Every knob is configurable, and the pilot
consults the same playability and sell-willingness profiles the analytics use,
so simulation and heuristics stay consistent with one another.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from ..config import RuleConfig
from ..effects.generic import apply_effect, card_effects
from ..models import Card, PlayabilityProfile, normalize_name
from ..probability.mulligan import HandContext, MulliganPolicy
from .legends import best_call_candidate, call_legend, legend_calls_remaining
from .state import GameState


@dataclass
class PilotPolicy:
    """How the simulated pilot plays."""

    target_names: tuple[str, ...] = ()
    profile: Optional[PlayabilityProfile] = None
    mulligan: Optional[MulliganPolicy] = None
    min_sell_willingness: float = 0.25
    hold_resources_for_target: bool = True
    call_legend_for_draw: bool = True
    play_non_target_cards: bool = True
    early_turn: int = 2

    def __post_init__(self) -> None:
        self._target_keys = {normalize_name(n) for n in self.target_names}

    def hand_context(self) -> HandContext:
        return HandContext(
            target_names=self.target_names,
            profile=self.profile,
            early_turn=self.early_turn,
            score_config=self.mulligan.score_config if self.mulligan else None,
        )

    def is_target(self, card: Card) -> bool:
        return card.key in self._target_keys

    # ------------------------------------------------------------------ mulligan
    def decide_mulligan(self, state: GameState) -> int:
        """Redraw while the policy says mulligan, up to its limit.

        Returns the number of mulligans taken.
        """
        if self.mulligan is None:
            return 0
        context = self.hand_context()
        taken = 0
        while taken < self.mulligan.max_mulligans:
            if self.mulligan.decide(state.hand, context):
                break
            state.redraw_hand()
            taken += 1
        return taken

    # ---------------------------------------------------------------------- sell
    def sell_candidate(self, state: GameState) -> Optional[Card]:
        """Pick the card the pilot is most willing to sell, if any qualifies."""
        best: Optional[Card] = None
        best_score = -1.0
        for card in state.hand:
            if not card.is_sellable:
                continue
            willingness = (
                self.profile.willingness(card, state.turn) if self.profile else 0.75
            )
            if self.is_target(card):
                willingness = min(willingness, 0.05)
            if willingness < self.min_sell_willingness:
                continue
            # Prefer selling redundant copies over singletons in hand.
            duplicates = sum(1 for c in state.hand if c.key == card.key)
            score = willingness + 0.05 * (duplicates - 1)
            if score > best_score:
                best, best_score = card, score
        return best

    def take_sell(self, state: GameState, rules: RuleConfig) -> bool:
        sells_done = state.sells_by_turn.get(state.turn, 0)
        if sells_done >= rules.max_sells_per_turn:
            return False
        card = self.sell_candidate(state)
        if card is None:
            state.missed_sell_turns.append(state.turn)
            return False
        return state.sell(card)

    # -------------------------------------------------------------------- legend
    def target_in_hand(self, state: GameState) -> Optional[Card]:
        for card in state.hand:
            if self.is_target(card):
                return card
        return None

    def take_legend_action(self, state: GameState, rules: RuleConfig) -> None:
        if not self.call_legend_for_draw:
            return
        if legend_calls_remaining(state, rules) <= 0:
            return
        candidate = best_call_candidate(state)
        if candidate is None:
            return
        if self.hold_resources_for_target:
            target = self.target_in_hand(state)
            if target is not None and target.cost is not None:
                without_legend = state.ready_eddies
                with_legend = state.available_resources
                # Calling consumes this Legend's resource value; skip the call
                # when doing so is what makes the target unaffordable.
                after_call = with_legend - rules.legend_resource_value
                if with_legend >= target.cost > max(after_call, without_legend):
                    state.actions.append(
                        f"T{state.turn}: held {candidate.card.name} for resources"
                    )
                    return
        call_legend(state, candidate)

    # --------------------------------------------------------------------- plays
    def strategic_roll(self, card: Card, turn: int, rng: random.Random) -> bool:
        if self.profile is None:
            return True
        return rng.random() < self.profile.strategic_playability(card, turn)

    def legal_roll(self, card: Card, turn: int, rng: random.Random) -> bool:
        if self.profile is None:
            return True
        return rng.random() < self.profile.legal_playability(card, turn)

    def play_card(self, state: GameState, card: Card) -> bool:
        if not state.play(card):
            return False
        effects = card_effects(card, "on_play")
        if effects:
            context = state.context()
            for effect in effects:
                apply_effect(effect, state, context)
        return True

    def take_plays(self, state: GameState, rules: RuleConfig, rng: random.Random) -> None:
        # Targets first: they are why the deck exists.
        for card in list(state.hand):
            if not self.is_target(card):
                continue
            if not state.can_afford(card.cost or 0):
                continue
            if not self.legal_roll(card, state.turn, rng):
                continue
            if not self.strategic_roll(card, state.turn, rng):
                continue
            self.play_card(state, card)

        if not self.play_non_target_cards:
            return

        # Then everything else, most-playable first.
        def rank(card: Card) -> float:
            if self.profile is None:
                return float(card.cost or 0)
            return self.profile.strategic_playability(card, state.turn)

        for card in sorted(list(state.hand), key=rank, reverse=True):
            if self.is_target(card):
                continue
            if not state.can_afford(card.cost or 0):
                continue
            if self.hold_resources_for_target:
                target = self.target_in_hand(state)
                if target is not None and target.cost is not None:
                    remaining = state.available_resources - max(0, (card.cost or 0))
                    if remaining < target.cost:
                        continue
            if not self.legal_roll(card, state.turn, rng):
                continue
            if not self.strategic_roll(card, state.turn, rng):
                continue
            self.play_card(state, card)
