"""Restrict an ingested card pool to the released Beta environment.

The initial version supports only:

* the Cyberpunk TCG Beta set, and
* Beta starter-deck-exclusive cards available in starter products.

Preview-only, unreleased, future-set, fan-made and speculative cards are
dropped, and every drop is reported so nothing disappears silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from ..models import Card

#: Set codes accepted as "released Beta".  Configurable because the official
#: database's code for the Beta set is verified at ingestion time, not guessed.
DEFAULT_BETA_SET_CODES: tuple[str, ...] = ("MS01", "BETA")

#: Substrings in a set name that identify the Beta environment.
DEFAULT_BETA_SET_NAME_HINTS: tuple[str, ...] = ("beta", "welcome to night city")

#: Markers that indicate a card is not yet released.
UNRELEASED_MARKERS: tuple[str, ...] = (
    "preview",
    "unreleased",
    "upcoming",
    "spoiler",
    "promo-preview",
    "fan",
    "custom",
    "proxy",
    "speculative",
)


@dataclass
class PoolFilterResult:
    kept: list[Card] = field(default_factory=list)
    dropped: list[tuple[Card, str]] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return f"{len(self.kept)} cards kept, {len(self.dropped)} dropped"

    def dropped_reasons(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, reason in self.dropped:
            counts[reason] = counts.get(reason, 0) + 1
        return counts


def is_beta(
    card: Card,
    set_codes: Sequence[str] = DEFAULT_BETA_SET_CODES,
    name_hints: Sequence[str] = DEFAULT_BETA_SET_NAME_HINTS,
) -> bool:
    code = (card.set_code or "").strip().upper()
    if code and code in {c.upper() for c in set_codes}:
        return True
    name = (card.set_name or "").strip().lower()
    return any(hint in name for hint in name_hints) if name else False


def is_unreleased(card: Card) -> bool:
    haystack = " ".join(
        filter(None, [card.set_name, " ".join(card.tags), card.interpretation_notes])
    ).lower()
    return any(marker in haystack for marker in UNRELEASED_MARKERS)


def filter_pool(
    cards: Iterable[Card],
    set_codes: Sequence[str] = DEFAULT_BETA_SET_CODES,
    name_hints: Sequence[str] = DEFAULT_BETA_SET_NAME_HINTS,
    allow_starter_exclusive: bool = True,
    extra_set_codes: Optional[Sequence[str]] = None,
) -> PoolFilterResult:
    """Keep released Beta cards (and Beta starter exclusives); drop the rest."""
    codes = list(set_codes) + list(extra_set_codes or [])
    result = PoolFilterResult()
    for card in cards:
        if is_unreleased(card):
            result.dropped.append((card, "not released (preview/unreleased/fan-made)"))
            continue
        if is_beta(card, codes, name_hints):
            result.kept.append(card)
            continue
        if allow_starter_exclusive and card.starter_exclusive:
            result.kept.append(card)
            continue
        result.dropped.append(
            (card, f"outside the Beta pool (set={card.set_code or card.set_name or '?'})")
        )
    return result
