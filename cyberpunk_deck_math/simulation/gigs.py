"""Gig value generation.

Dice distributions are configurable and are never assumed uniform unless the
configuration says so.  Real observed distributions can be entered directly.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class GigDistribution:
    """A discrete distribution over Gig values."""

    weights: dict[int, float] = field(default_factory=lambda: {1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1})
    name: str = "uniform d6"

    def __post_init__(self) -> None:
        if not self.weights:
            raise ValueError("a Gig distribution needs at least one outcome")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("Gig weights may not be negative")
        if sum(self.weights.values()) <= 0:
            raise ValueError("Gig weights must sum to a positive number")

    @classmethod
    def uniform(cls, sides: int = 6) -> "GigDistribution":
        return cls(weights={i: 1.0 for i in range(1, sides + 1)}, name=f"uniform d{sides}")

    @classmethod
    def from_observations(cls, observations: Sequence[int], name: str = "observed") -> "GigDistribution":
        weights: dict[int, float] = {}
        for value in observations:
            weights[int(value)] = weights.get(int(value), 0.0) + 1.0
        return cls(weights=weights, name=name)

    @classmethod
    def from_mapping(cls, mapping: Mapping[Any, float], name: str = "configured") -> "GigDistribution":
        return cls(weights={int(k): float(v) for k, v in mapping.items()}, name=name)

    @property
    def values(self) -> list[int]:
        return sorted(self.weights)

    def probabilities(self) -> dict[int, float]:
        total = sum(self.weights.values())
        return {k: v / total for k, v in sorted(self.weights.items())}

    def mean(self) -> float:
        return sum(k * p for k, p in self.probabilities().items())

    def roll(self, rng: random.Random) -> int:
        values = self.values
        weights = [self.weights[v] for v in values]
        return rng.choices(values, weights=weights, k=1)[0]

    def to_dict(self) -> dict:
        return {"name": self.name, "weights": dict(self.weights), "mean": self.mean()}
