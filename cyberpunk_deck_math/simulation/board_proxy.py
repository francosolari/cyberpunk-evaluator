"""Opponent / board-state proxies.

Cards that depend on the opponent's board cannot be evaluated exactly without
an opponent model.  Rather than guess, the application makes the assumption
explicit and configurable, and labels every result that used it HEURISTIC.

MODE A — PROXY:     sample the condition from a configured probability.
MODE B — SIMULATED: derive it from a simplified generated board state.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Mapping

from ..methods import Method

MODE_PROXY = "proxy"
MODE_SIMULATED = "simulated"


@dataclass
class BoardProxy:
    """Probabilities that an opponent-dependent condition holds, by turn."""

    name: str = "default"
    mode: str = MODE_PROXY
    probabilities: dict[str, dict[int, float]] = field(
        default_factory=lambda: {
            "valid_target": {1: 0.05, 2: 0.10, 3: 0.20, 4: 0.50, 5: 0.65, 6: 0.75},
        }
    )
    opponent_units_by_turn: dict[int, float] = field(
        default_factory=lambda: {1: 0.4, 2: 1.0, 3: 1.6, 4: 2.2, 5: 2.8, 6: 3.2}
    )
    method: Method = Method.HEURISTIC_PROXY

    def probability(self, key: str, turn: int) -> float:
        table = self.probabilities.get(key)
        if not table:
            return 0.0
        eligible = [t for t in table if t <= turn]
        if not eligible:
            return 0.0
        return float(table[max(eligible)])

    def resolve(self, turn: int, rng: random.Random) -> dict[str, object]:
        """Sample every proxy condition for one turn."""
        resolved: dict[str, object] = {
            key: rng.random() < self.probability(key, turn) for key in self.probabilities
        }
        expected_units = self.opponent_units_by_turn.get(
            turn, max(self.opponent_units_by_turn.values(), default=0.0)
        )
        whole = int(expected_units)
        resolved["enemy_unit_count"] = whole + (
            1 if rng.random() < (expected_units - whole) else 0
        )
        return resolved

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mode": self.mode,
            "method": self.method.value,
            "probabilities": {
                k: {str(t): v for t, v in table.items()}
                for k, table in self.probabilities.items()
            },
            "opponent_units_by_turn": {
                str(t): v for t, v in self.opponent_units_by_turn.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "BoardProxy":
        probabilities = {
            k: {int(t): float(v) for t, v in table.items()}  # type: ignore[union-attr]
            for k, table in (data.get("probabilities") or {}).items()  # type: ignore[union-attr]
        }
        units = {
            int(t): float(v)
            for t, v in (data.get("opponent_units_by_turn") or {}).items()  # type: ignore[union-attr]
        }
        proxy = cls(
            name=str(data.get("name", "default")),
            mode=str(data.get("mode", MODE_PROXY)),
        )
        if probabilities:
            proxy.probabilities = probabilities
        if units:
            proxy.opponent_units_by_turn = units
        return proxy
