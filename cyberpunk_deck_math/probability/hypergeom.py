"""Exact univariate hypergeometric probabilities.

Pure Python with :func:`math.comb`, so results are exact rationals converted
to float at the last step — no scipy dependency and no floating-point
accumulation across the tail sum.
"""

from __future__ import annotations

from fractions import Fraction
from functools import lru_cache
from math import comb

from ..methods import Method, Result


def _validate(N: int, K: int, n: int) -> None:
    if N < 0 or K < 0 or n < 0:
        raise ValueError("population, successes and sample size must be >= 0")
    if K > N:
        raise ValueError(f"success count {K} exceeds population {N}")
    if n > N:
        raise ValueError(f"sample size {n} exceeds population {N}")


@lru_cache(maxsize=None)
def pmf_exact(N: int, K: int, n: int, k: int) -> Fraction:
    """P(X = k) as an exact Fraction for X ~ Hypergeometric(N, K, n)."""
    _validate(N, K, n)
    if k < 0 or k > K or k > n or (n - k) > (N - K):
        return Fraction(0)
    return Fraction(comb(K, k) * comb(N - K, n - k), comb(N, n))


def pmf(N: int, K: int, n: int, k: int) -> float:
    """P(X = k)."""
    return float(pmf_exact(N, K, n, k))


def sf_at_least_exact(N: int, K: int, n: int, k: int) -> Fraction:
    """P(X >= k) as an exact Fraction."""
    _validate(N, K, n)
    if k <= 0:
        return Fraction(1)
    upper = min(K, n)
    if k > upper:
        return Fraction(0)
    return sum((pmf_exact(N, K, n, i) for i in range(k, upper + 1)), Fraction(0))


def at_least(N: int, K: int, n: int, k: int = 1) -> float:
    """P(X >= k)."""
    return float(sf_at_least_exact(N, K, n, k))


def at_most(N: int, K: int, n: int, k: int) -> float:
    """P(X <= k)."""
    return float(1 - sf_at_least_exact(N, K, n, k + 1))


def exactly(N: int, K: int, n: int, k: int) -> float:
    """P(X = k)."""
    return pmf(N, K, n, k)


def none(N: int, K: int, n: int) -> float:
    """P(X = 0), i.e. the classic ``1 - C(N-K, n) / C(N, n)`` complement."""
    return pmf(N, K, n, 0)


def mean(N: int, K: int, n: int) -> float:
    _validate(N, K, n)
    if N == 0:
        return 0.0
    return n * K / N


def distribution(N: int, K: int, n: int) -> dict[int, float]:
    """Full pmf keyed by k."""
    _validate(N, K, n)
    return {k: pmf(N, K, n, k) for k in range(0, min(K, n) + 1)}


def access_result(N: int, K: int, n: int, k: int = 1, label: str = "") -> Result:
    """``P(X >= k)`` wrapped with its EXACT — Hypergeometric label."""
    value = at_least(N, K, n, k)
    return Result(
        value=value,
        method=Method.EXACT_HYPERGEOMETRIC,
        label=label or f"P(at least {k} of {K} in {n} cards seen)",
        assumptions={
            "population_size": N,
            "success_count": K,
            "sample_size": n,
            "threshold_k": k,
        },
    )
