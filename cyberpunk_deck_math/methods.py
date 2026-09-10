"""Method provenance labels.

Every number this application produces must be attributable to a method.
Nothing in the codebase is allowed to present a heuristic as exact, so all
public analytics return values carry one of these labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Method(str, Enum):
    """How a reported number was produced."""

    EXACT_HYPERGEOMETRIC = "EXACT — Hypergeometric"
    EXACT_MULTIVARIATE = "EXACT — Multivariate Hypergeometric"
    EXACT_ENUMERATION = "EXACT — Combinatorial Enumeration"
    SIMULATED = "SIMULATED — Monte Carlo"
    HEURISTIC_HUMAN = "HEURISTIC — Human Estimate"
    HEURISTIC_LLM = "HEURISTIC — LLM Estimate"
    HEURISTIC_PROXY = "HEURISTIC — Board-State Proxy"
    PLAYTESTING_HEURISTIC = "USER / PLAYTESTING HEURISTIC"
    DERIVED = "DERIVED — Deterministic Deck Arithmetic"

    def is_exact(self) -> bool:
        return self.name.startswith("EXACT")

    def is_heuristic(self) -> bool:
        return self.name.startswith("HEURISTIC") or self is Method.PLAYTESTING_HEURISTIC


@dataclass(frozen=True)
class Result:
    """A single labelled number.

    ``value`` is usually a probability but may be any scalar (a count, a
    density, a delta).  ``assumptions`` records anything the caller needed to
    assume; it is exported verbatim so a reader can reproduce the number.
    """

    value: float
    method: Method
    label: str = ""
    detail: str = ""
    assumptions: dict[str, Any] = field(default_factory=dict)
    sample_size: Optional[int] = None
    standard_error: Optional[float] = None
    ci95: Optional[tuple[float, float]] = None

    @property
    def pct(self) -> float:
        return 100.0 * self.value

    def formatted(self, digits: int = 2) -> str:
        """Render the value, refusing false precision on heuristics."""
        if self.method.is_heuristic():
            digits = min(digits, 1)
        text = f"{self.value * 100:.{digits}f}%"
        if self.ci95 is not None:
            lo, hi = self.ci95
            text += f" (95% CI {lo * 100:.{digits}f}%–{hi * 100:.{digits}f}%"
            if self.sample_size:
                text += f", n={self.sample_size:,}"
            text += ")"
        return text

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "label": self.label,
            "value": self.value,
            "method": self.method.value,
        }
        if self.detail:
            out["detail"] = self.detail
        if self.assumptions:
            out["assumptions"] = self.assumptions
        if self.sample_size is not None:
            out["sample_size"] = self.sample_size
        if self.standard_error is not None:
            out["standard_error"] = self.standard_error
        if self.ci95 is not None:
            out["ci95"] = list(self.ci95)
        return out
