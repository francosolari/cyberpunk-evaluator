"""Generic trigger vocabulary."""

from __future__ import annotations

TRIGGERS: tuple[str, ...] = (
    "on_play",
    "on_call",
    "on_spend",
    "on_reveal",
    "on_trash",
    "on_score",
    "on_attack",
    "on_damage",
    "start_phase",
    "main_phase",
    "conditional",
)


def validate_trigger(trigger: str) -> str:
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown trigger {trigger!r}; expected one of {TRIGGERS}")
    return trigger
