"""Generic effect representation and application.

An effect is a plain dictionary::

    {"trigger": "on_play", "effect": "draw", "amount": 1,
     "conditions": [{"type": "street_cred_parity", "value": "even"}]}

The simulator applies effects through :func:`apply_effect`; anything the
engine cannot represent is reported rather than silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .conditions import evaluate_all, validate_condition
from .triggers import validate_trigger

EFFECTS: tuple[str, ...] = (
    "draw",
    "gain_resource",
    "adjust_gig",
    "gain_street_cred",
    "trash",
    "return_to_hand",
    "search",
    "reveal",
    "discount",
    "ready",
    "spend",
)


@dataclass
class Effect:
    trigger: str
    effect: str
    amount: int = 1
    conditions: list[dict[str, Any]] = field(default_factory=list)
    target: Optional[str] = None
    notes: Optional[str] = None
    source_card: Optional[str] = None

    def __post_init__(self) -> None:
        validate_trigger(self.trigger)
        if self.effect not in EFFECTS:
            raise ValueError(f"unknown effect {self.effect!r}; expected one of {EFFECTS}")
        for condition in self.conditions:
            validate_condition(condition)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], source_card: str | None = None) -> "Effect":
        return cls(
            trigger=data["trigger"],
            effect=data["effect"],
            amount=int(data.get("amount", 1)),
            conditions=[dict(c) for c in data.get("conditions", [])],
            target=data.get("target"),
            notes=data.get("notes"),
            source_card=source_card,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "trigger": self.trigger,
            "effect": self.effect,
            "amount": self.amount,
        }
        if self.conditions:
            data["conditions"] = self.conditions
        if self.target:
            data["target"] = self.target
        if self.notes:
            data["notes"] = self.notes
        return data

    def is_active(
        self, context: Mapping[str, Any], unknown_is: Optional[bool] = None
    ) -> Optional[bool]:
        return evaluate_all(self.conditions, context, unknown_is=unknown_is)


def parse_effects(metadata: list[Mapping[str, Any]], source_card: str | None = None) -> list[Effect]:
    effects: list[Effect] = []
    for entry in metadata or []:
        effects.append(Effect.from_dict(entry, source_card=source_card))
    return effects


def effects_for_trigger(effects: list[Effect], trigger: str) -> list[Effect]:
    return [e for e in effects if e.trigger == trigger]


_EFFECT_CACHE: dict[tuple[str, int, str], dict[str, list[Effect]]] = {}


def card_effects(card, trigger: str) -> list[Effect]:
    """Parsed effects for one card and trigger, cached.

    The simulator asks for these millions of times, so parsing (and the
    validation it performs) happens once per card revision.
    """
    key = (card.card_id, len(card.effect_metadata or []), card.interpretation_status)
    table = _EFFECT_CACHE.get(key)
    if table is None:
        parsed = parse_effects(card.effect_metadata, source_card=card.name)
        table = {}
        for effect in parsed:
            table.setdefault(effect.trigger, []).append(effect)
        _EFFECT_CACHE[key] = table
    return table.get(trigger, [])


def apply_effect(effect: Effect, state, context: Mapping[str, Any]) -> dict[str, Any]:
    """Apply an effect to a :class:`~cyberpunk_deck_math.simulation.state.GameState`.

    Returns a small record of what happened so the simulator can attribute
    outcomes (for example, "how many extra draws came from Muamar").
    """
    record = {"effect": effect.effect, "amount": effect.amount, "applied": 0,
              "source": effect.source_card}
    active = effect.is_active(context, unknown_is=False)
    if not active:
        return record

    if effect.effect == "draw":
        record["applied"] = state.draw(effect.amount, source=effect.source_card)
    elif effect.effect == "gain_resource":
        state.eddies += effect.amount
        state.ready_eddies += effect.amount
        record["applied"] = effect.amount
    elif effect.effect == "gain_street_cred":
        state.street_cred += effect.amount
        record["applied"] = effect.amount
    elif effect.effect == "adjust_gig":
        if state.gig_values:
            state.gig_values[-1] = max(0, state.gig_values[-1] + effect.amount)
            state.street_cred = sum(state.gig_values)
            record["applied"] = effect.amount
    elif effect.effect == "ready":
        state.ready_eddies = min(state.eddies, state.ready_eddies + effect.amount)
        record["applied"] = effect.amount
    elif effect.effect == "discount":
        state.discount += effect.amount
        record["applied"] = effect.amount
    elif effect.effect == "trash":
        record["applied"] = state.trash_from_hand(effect.amount)
    elif effect.effect == "spend":
        record["applied"] = state.spend(effect.amount)
    elif effect.effect in ("search", "reveal", "return_to_hand"):
        # Modelled as information/tempo only; no state change is claimed
        # rather than inventing one.
        record["applied"] = 0
        record["unmodelled"] = True
    return record
