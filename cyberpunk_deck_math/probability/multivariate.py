"""Exact multivariate hypergeometric probabilities.

Compound questions ("Jackie AND 3+ sellables") are answered by exact
enumeration over the joint distribution of disjoint card groups.  The groups
must partition the deck; a residual "other" group is added automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from math import comb
from typing import Callable, Iterable, Mapping, Sequence

from ..methods import Method, Result


@dataclass(frozen=True)
class Group:
    """A disjoint group of cards in the deck."""

    name: str
    size: int

    def __post_init__(self) -> None:
        if self.size < 0:
            raise ValueError(f"group {self.name} has negative size")


def _prepare(groups: Sequence[Group], N: int) -> list[Group]:
    total = sum(g.size for g in groups)
    if total > N:
        raise ValueError(
            f"group sizes total {total}, which exceeds the deck size {N}; "
            "groups must be disjoint"
        )
    names = [g.name for g in groups]
    if len(set(names)) != len(names):
        raise ValueError("group names must be unique")
    if "__other__" in names:
        raise ValueError("'__other__' is reserved")
    return list(groups) + [Group("__other__", N - total)]


def joint_distribution(
    groups: Sequence[Group], N: int, n: int
) -> Iterable[tuple[dict[str, int], Fraction]]:
    """Yield ``(counts, exact probability)`` for every reachable draw split."""
    if n > N:
        raise ValueError(f"sample size {n} exceeds deck size {N}")
    full = _prepare(groups, N)
    denominator = comb(N, n)
    ranges = [range(0, min(g.size, n) + 1) for g in full]
    for combo in product(*ranges):
        if sum(combo) != n:
            continue
        numerator = 1
        for g, k in zip(full, combo):
            numerator *= comb(g.size, k)
        if numerator == 0:
            continue
        counts = {g.name: k for g, k in zip(full, combo) if g.name != "__other__"}
        yield counts, Fraction(numerator, denominator)


def probability(
    groups: Sequence[Group],
    N: int,
    n: int,
    predicate: Callable[[Mapping[str, int]], bool],
) -> float:
    """Exact P(predicate holds) over a draw of ``n`` from ``N``."""
    total = Fraction(0)
    for counts, p in joint_distribution(groups, N, n):
        if predicate(counts):
            total += p
    return float(total)


def compound_result(
    groups: Sequence[Group],
    N: int,
    n: int,
    requirements: Mapping[str, int],
    label: str = "",
    forbidden: Mapping[str, int] | None = None,
) -> Result:
    """P(at least ``requirements[g]`` of each group, and fewer than
    ``forbidden[g]`` of each forbidden group) in ``n`` cards seen."""
    forbidden = dict(forbidden or {})

    def predicate(counts: Mapping[str, int]) -> bool:
        for name, need in requirements.items():
            if counts.get(name, 0) < need:
                return False
        for name, cap in forbidden.items():
            if counts.get(name, 0) >= cap:
                return False
        return True

    value = probability(groups, N, n, predicate)
    parts = [f"{name} >= {need}" for name, need in requirements.items()]
    parts += [f"{name} < {cap}" for name, cap in forbidden.items()]
    return Result(
        value=value,
        method=Method.EXACT_MULTIVARIATE,
        label=label or " AND ".join(parts),
        assumptions={
            "population_size": N,
            "sample_size": n,
            "groups": {g.name: g.size for g in groups},
            "requirements": dict(requirements),
            "forbidden": forbidden,
        },
    )
