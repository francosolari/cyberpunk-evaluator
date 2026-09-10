"""Mutable game state for the Monte Carlo simulator."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import RuleConfig
from ..models import Card


@dataclass
class LegendState:
    card: Card
    ready: bool = True
    face_up: bool = False
    called_this_turn: bool = False
    spent: bool = False


@dataclass
class GameState:
    """One game in progress.

    Only the player's own board is modelled in detail; opponent-dependent
    conditions are resolved through :mod:`board_proxy`.
    """

    rules: RuleConfig
    rng: random.Random
    deck: list[Card] = field(default_factory=list)
    hand: list[Card] = field(default_factory=list)
    trash: list[Card] = field(default_factory=list)
    legends: list[LegendState] = field(default_factory=list)

    turn: int = 0
    eddies: int = 0
    ready_eddies: int = 0
    discount: int = 0

    gigs: int = 0
    gig_values: list[int] = field(default_factory=list)
    street_cred: int = 0

    units: list[Card] = field(default_factory=list)
    gear: list[Card] = field(default_factory=list)
    programs: list[Card] = field(default_factory=list)

    cards_seen: list[Card] = field(default_factory=list)
    cards_drawn: int = 0
    cards_sold: list[Card] = field(default_factory=list)
    resources_spent: int = 0
    actions: list[str] = field(default_factory=list)

    draws_by_source: dict[str, int] = field(default_factory=dict)
    sells_by_turn: dict[int, int] = field(default_factory=dict)
    missed_sell_turns: list[int] = field(default_factory=list)
    plays_by_turn: dict[int, list[str]] = field(default_factory=dict)
    opponent_proxy: dict[str, bool] = field(default_factory=dict)

    # ------------------------------------------------------------------ deck ops
    def shuffle(self) -> None:
        self.rng.shuffle(self.deck)

    def draw(self, count: int = 1, source: Optional[str] = None) -> int:
        """Draw up to ``count`` cards; returns how many were actually drawn."""
        drawn = 0
        for _ in range(count):
            if not self.deck:
                break
            card = self.deck.pop()
            self.hand.append(card)
            self.cards_seen.append(card)
            self.cards_drawn += 1
            drawn += 1
        if drawn and source:
            self.draws_by_source[source] = self.draws_by_source.get(source, 0) + drawn
        return drawn

    def deal_opening_hand(self) -> None:
        self.hand = []
        self.cards_seen = []
        self.draw(self.rules.opening_hand_size, source="opening hand")

    def redraw_hand(self) -> None:
        """Mulligan: shuffle the hand back and draw a fresh one."""
        self.deck.extend(self.hand)
        self.hand = []
        self.cards_seen = []
        self.cards_drawn = 0
        self.draws_by_source.pop("opening hand", None)
        self.shuffle()
        self.draw(self.rules.opening_hand_size, source="opening hand")

    # -------------------------------------------------------------- resource ops
    @property
    def available_resources(self) -> int:
        """Eddies ready to spend plus Legends that could be spent for value."""
        return self.ready_eddies + self.spendable_legend_value()

    def spendable_legend_value(self) -> int:
        return sum(
            self.rules.legend_resource_value
            for legend in self.legends
            if legend.ready and not legend.spent
        )

    def spend(self, amount: int) -> int:
        """Spend ``amount``, using ready eddies first, then Legends."""
        remaining = amount
        used = min(self.ready_eddies, remaining)
        self.ready_eddies -= used
        remaining -= used
        for legend in self.legends:
            if remaining <= 0:
                break
            if legend.ready and not legend.spent:
                legend.ready = False
                legend.spent = True
                remaining -= self.rules.legend_resource_value
        spent = amount - max(0, remaining)
        self.resources_spent += spent
        return spent

    def can_afford(self, cost: int) -> bool:
        return self.available_resources >= max(0, cost - self.discount)

    def sell(self, card: Card) -> bool:
        """Sell a card from hand for eddies."""
        if card not in self.hand:
            return False
        self.hand.remove(card)
        self.trash.append(card)
        self.cards_sold.append(card)
        self.eddies += self.rules.eddie_value
        self.ready_eddies += self.rules.eddie_value
        self.sells_by_turn[self.turn] = self.sells_by_turn.get(self.turn, 0) + 1
        self.actions.append(f"T{self.turn}: sold {card.name}")
        return True

    def trash_from_hand(self, count: int) -> int:
        removed = 0
        for _ in range(count):
            if not self.hand:
                break
            self.trash.append(self.hand.pop())
            removed += 1
        return removed

    def play(self, card: Card, cost: Optional[int] = None) -> bool:
        if card not in self.hand:
            return False
        price = max(0, (cost if cost is not None else (card.cost or 0)) - self.discount)
        if self.available_resources < price:
            return False
        self.spend(price)
        self.hand.remove(card)
        zone = {
            "unit": self.units,
            "gear": self.gear,
            "program": self.programs,
        }.get((card.type or "").strip().lower())
        (zone if zone is not None else self.units).append(card)
        self.plays_by_turn.setdefault(self.turn, []).append(card.name)
        self.actions.append(f"T{self.turn}: played {card.name}")
        return True

    # ---------------------------------------------------------------- turn ops
    def ready_all(self) -> None:
        self.ready_eddies = self.eddies
        self.discount = 0
        for legend in self.legends:
            legend.called_this_turn = False
            if not legend.spent:
                legend.ready = True

    def add_gig(self, value: int) -> None:
        self.gigs += 1
        self.gig_values.append(value)
        self.street_cred = sum(self.gig_values)

    @property
    def distinct_gigs(self) -> int:
        return len(set(self.gig_values))

    def context(self) -> dict[str, Any]:
        """The evaluation context for generic effect conditions."""
        return {
            "turn": self.turn,
            "street_cred": self.street_cred,
            "distinct_gigs": self.distinct_gigs,
            "gig_count": self.gigs,
            "resource_available": self.available_resources,
            "friendly_unit_count": len(self.units),
            "enemy_unit_count": self.opponent_proxy.get("enemy_unit_count"),
            "card_types_in_play": [
                (c.type or "").lower() for c in self.units + self.gear + self.programs
            ],
            "hand_names": [c.name for c in self.hand],
            "legend_face_up": any(l.face_up for l in self.legends),
            "opponent_state_proxy": self.opponent_proxy,
        }
