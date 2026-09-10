"""Sensitivity analysis over uncertain assumptions.

Any proxy value the model is not sure about can be swept over a range.  When
a conclusion changes materially across that range, the assumption is flagged:
the honest answer is then "it depends on X", not a single number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from ..config import RuleConfig
from ..methods import Method
from ..models import Card, Deck, PlayabilityProfile
from ..probability import sells
from . import access, dead_cards, opportunity_density

MATERIAL_IMPACT = 0.05  # 5 percentage points


@dataclass
class SensitivityRun:
    assumption: str
    values: list[float]
    outcomes: list[float]
    metric: str
    method: Method = Method.HEURISTIC_HUMAN

    @property
    def spread(self) -> float:
        return max(self.outcomes) - min(self.outcomes) if self.outcomes else 0.0

    @property
    def material(self) -> bool:
        return self.spread >= MATERIAL_IMPACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption": self.assumption,
            "metric": self.metric,
            "values": self.values,
            "outcomes": self.outcomes,
            "spread": self.spread,
            "material_impact": self.material,
            "method": self.method.value,
            "verdict": (
                f"Conclusions move {self.spread:.1%} across the tested range — "
                "state this assumption alongside the result."
                if self.material
                else "Conclusions are stable across the tested range."
            ),
        }


def sweep(
    assumption: str,
    values: Sequence[float],
    metric_name: str,
    evaluate: Callable[[float], float],
    method: Method = Method.HEURISTIC_HUMAN,
) -> SensitivityRun:
    """Generic sweep: evaluate ``metric`` once per assumption value."""
    return SensitivityRun(
        assumption=assumption,
        values=list(values),
        outcomes=[float(evaluate(v)) for v in values],
        metric=metric_name,
        method=method,
    )


def sweep_strategic_playability(
    deck: Deck,
    profile: PlayabilityProfile,
    card_name: str,
    turn: int,
    values: Sequence[float] = (0.0, 0.05, 0.10, 0.20, 0.30),
    metric: str = "action_density",
) -> SensitivityRun:
    """Sweep one card's strategic playability and watch a deck-level metric."""
    from copy import deepcopy

    def evaluate(value: float) -> float:
        trial = deepcopy(profile)
        trial.strategic.setdefault(_key(card_name), {})[turn] = value
        trial.invalidate()
        if metric == "dead_burden":
            return dead_cards.dead_card_burden(deck, trial, turn).total
        return opportunity_density.opportunity_density(deck, trial, turn).value

    return sweep(
        f"{card_name} strategic playability T{turn}",
        values,
        f"{metric} T{turn}",
        evaluate,
    )


def _key(name: str) -> str:
    from ..models import normalize_name

    return normalize_name(name)


def sweep_sellable_target(
    deck: Deck,
    pcts: Sequence[float] = (0.55, 0.575, 0.60, 0.625, 0.65, 0.675),
    through_turn: int = 3,
    rules: Optional[RuleConfig] = None,
) -> SensitivityRun:
    """Sweep sellable density and watch consecutive-sell reliability."""
    rules = rules or RuleConfig()
    N = deck.size

    def evaluate(pct: float) -> float:
        count = min(N, round(pct * N))
        return sells.consecutive_sells(N, count, through_turn, rules).value

    run = sweep(
        "sellable density",
        list(pcts),
        f"P(sell every turn through T{through_turn})",
        evaluate,
        method=Method.EXACT_HYPERGEOMETRIC,
    )
    return run


def sweep_copies(
    deck: Deck,
    card_name: str,
    filler: Card,
    counts: Sequence[int] = (1, 2, 3),
    turn: int = 3,
    rules: Optional[RuleConfig] = None,
) -> SensitivityRun:
    """Sweep copy count and watch raw target access at ``turn``."""
    rules = rules or RuleConfig()

    def evaluate(count: float) -> float:
        variant = deck.with_copies(card_name, int(count), filler)
        return access.raw_access(variant, card_name, turn, rules).value

    return sweep(
        f"{card_name} copies",
        [float(c) for c in counts],
        f"P({card_name} seen by T{turn})",
        evaluate,
        method=Method.EXACT_HYPERGEOMETRIC,
    )


def sweep_board_proxy(
    probabilities: Sequence[float],
    evaluate: Callable[[float], float],
    label: str = "opponent has a valid target",
    metric: str = "target playability",
) -> SensitivityRun:
    return sweep(label, list(probabilities), metric, evaluate, Method.HEURISTIC_PROXY)


def flag_material(runs: Sequence[SensitivityRun]) -> list[str]:
    return [
        f"{run.assumption}: {run.metric} moves {run.spread:.1%} across the tested range"
        for run in runs
        if run.material
    ]
