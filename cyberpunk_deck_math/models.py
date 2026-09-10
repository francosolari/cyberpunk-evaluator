"""Core data model.

Cards are data, not code.  Card behaviour is expressed as generic effect
dictionaries (see :mod:`cyberpunk_deck_math.effects`) plus user-editable
playability profiles.  Bespoke Python per card is a last resort.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any, Iterable, Iterator, Mapping, Optional

DASHES = "—–‒‐‑-"
_DASH_RE = re.compile(f"[{DASHES}]")
_WS_RE = re.compile(r"\s+")


@lru_cache(maxsize=8192)
def normalize_name(name: str) -> str:
    """Fold a printed card name into a stable match key.

    Unicode em/en dashes, hyphens, curly apostrophes, case and spacing are all
    normalized away so ``Jackie Welles — Ride or Die Choom`` and
    ``jackie welles - ride or die choom`` match.
    """
    text = unicodedata.normalize("NFKC", name or "").strip().lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = _DASH_RE.sub("-", text)
    text = text.replace("-", " ")
    text = _WS_RE.sub(" ", text)
    return text.strip()


class InterpretationStatus(str):
    RAW = "raw"
    LLM_PROPOSED = "llm_proposed"
    HUMAN_VERIFIED = "human_verified"


VALID_INTERPRETATION_STATUS = {"raw", "llm_proposed", "human_verified"}


@dataclass
class Card:
    """A normalized card record.

    Fields sourced from the official database are stored verbatim.  Anything
    the source does not provide stays ``None`` — never a guess.
    """

    card_id: str
    name: str
    collector_number: Optional[str] = None
    set_code: Optional[str] = None
    set_name: Optional[str] = None
    starter_exclusive: Optional[bool] = None
    type: Optional[str] = None
    subtype: Optional[str] = None
    color: Optional[str] = None
    cost: Optional[int] = None
    ram: Optional[int] = None
    sellable: Optional[bool] = None
    rules_text: Optional[str] = None
    flavor_text: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    effect_metadata: list[dict[str, Any]] = field(default_factory=list)
    interpretation_status: str = "raw"
    interpretation_notes: Optional[str] = None
    source_url: Optional[str] = None
    database_updated_at: Optional[str] = None
    data_provenance: str = "official"
    is_legend: bool = False
    _key: Optional[str] = field(default=None, repr=False, compare=False)
    _key_for: Optional[str] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.interpretation_status not in VALID_INTERPRETATION_STATUS:
            raise ValueError(
                f"invalid interpretation_status {self.interpretation_status!r}"
            )

    @property
    def key(self) -> str:
        """The match key for this card's name (cached; the simulator is hot)."""
        if self._key is None or self._key_for != self.name:
            object.__setattr__(self, "_key_for", self.name)
            object.__setattr__(self, "_key", normalize_name(self.name))
        return self._key  # type: ignore[return-value]

    @property
    def is_sellable(self) -> bool:
        """Mechanically sellable.  Unknown (``None``) counts as not sellable."""
        return bool(self.sellable)

    def has_tag(self, tag: str) -> bool:
        return tag.lower() in {t.lower() for t in self.tags}

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if not k.startswith("_")}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Card":
        known = {f for f in cls.__dataclass_fields__ if not f.startswith("_")}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class DeckEntry:
    card: Card
    copies: int

    @property
    def name(self) -> str:
        return self.card.name


@dataclass
class Deck:
    """A constructed deck: 3 Legends plus a main deck."""

    name: str = "Untitled Deck"
    main: list[DeckEntry] = field(default_factory=list)
    legends: list[Card] = field(default_factory=list)
    strategy_profile: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    # ---------------------------------------------------------------- sizes
    @property
    def size(self) -> int:
        return sum(e.copies for e in self.main)

    @property
    def sellable_count(self) -> int:
        return sum(e.copies for e in self.main if e.card.is_sellable)

    @property
    def sellable_pct(self) -> float:
        return self.sellable_count / self.size if self.size else 0.0

    # -------------------------------------------------------------- lookups
    def entries(self) -> Iterator[DeckEntry]:
        return iter(self.main)

    def cards(self) -> Iterator[Card]:
        """Yield one Card object per physical copy."""
        for entry in self.main:
            for _ in range(entry.copies):
                yield entry.card

    def find(self, name_or_id: str) -> Optional[DeckEntry]:
        """Resolve a name, card id, collector number or unique name prefix."""
        key = normalize_name(name_or_id)
        for entry in self.main:
            if entry.card.key == key:
                return entry
            if entry.card.card_id and entry.card.card_id.lower() == name_or_id.lower():
                return entry
            if (
                entry.card.collector_number
                and entry.card.collector_number.lower() == name_or_id.lower()
            ):
                return entry
        prefix = [e for e in self.main if e.card.key.startswith(key + " ")]
        return prefix[0] if len(prefix) == 1 else None

    def copies_of(self, name_or_id: str) -> int:
        entry = self.find(name_or_id)
        return entry.copies if entry else 0

    def count_where(self, predicate) -> int:
        return sum(e.copies for e in self.main if predicate(e.card))

    # ------------------------------------------------------------ mutation
    def clone(self) -> "Deck":
        return Deck(
            name=self.name,
            main=[DeckEntry(card=e.card, copies=e.copies) for e in self.main],
            legends=list(self.legends),
            strategy_profile=self.strategy_profile,
            notes=list(self.notes),
        )

    def with_swap(
        self, remove: str, add: Card, count: int = 1, name: Optional[str] = None
    ) -> "Deck":
        """Return a copy with ``count`` copies of ``remove`` replaced by ``add``."""
        deck = self.clone()
        entry = deck.find(remove)
        if entry is None:
            raise KeyError(f"card not in deck: {remove}")
        if entry.copies < count:
            raise ValueError(
                f"cannot remove {count} copies of {entry.name}; deck has {entry.copies}"
            )
        entry.copies -= count
        if entry.copies == 0:
            deck.main.remove(entry)
        target = deck.find(add.name)
        if target is None:
            deck.main.append(DeckEntry(card=add, copies=count))
        else:
            target.copies += count
        deck.name = name or f"{self.name} (-{count} {remove} / +{count} {add.name})"
        return deck

    def with_copies(self, name: str, copies: int, filler: Card) -> "Deck":
        """Set ``name`` to ``copies``, absorbing the difference into ``filler``.

        Used by the 2-vs-3 shortcut so that deck size stays constant.
        """
        deck = self.clone()
        entry = deck.find(name)
        current = entry.copies if entry else 0
        delta = copies - current
        if delta == 0:
            return deck
        if entry is None:
            raise KeyError(f"card not in deck: {name}")
        filler_entry = deck.find(filler.name)
        if delta > 0:
            if filler_entry is None or filler_entry.copies < delta:
                raise ValueError(
                    f"not enough copies of {filler.name} to trade for {name}"
                )
            filler_entry.copies -= delta
            if filler_entry.copies == 0:
                deck.main.remove(filler_entry)
            entry.copies += delta
        else:
            entry.copies += delta  # delta negative
            if entry.copies == 0:
                deck.main.remove(entry)
            if filler_entry is None:
                deck.main.append(DeckEntry(card=filler, copies=-delta))
            else:
                filler_entry.copies += -delta
        deck.name = f"{self.name} [{name} x{copies}]"
        return deck

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "legends": [c.name for c in self.legends],
            "main": [{"name": e.card.name, "copies": e.copies} for e in self.main],
            "size": self.size,
            "sellable_count": self.sellable_count,
            "sellable_pct": self.sellable_pct,
        }


@dataclass
class PlayabilityProfile:
    """Per-strategy, per-card playability estimates.

    ``legal`` answers: given the card is in hand on turn T, in what fraction of
    realistic game states is playing it *legal* (cost and requirements met)?

    ``strategic`` answers: in what fraction is playing it actually *correct*?

    ``sell_willingness`` is independent of both: how happy the pilot is to sell
    the card on that turn.  Sell willingness is not the same as ``sellable``.
    """

    name: str = "default"
    description: str = ""
    source: str = "HEURISTIC — Human Estimate"
    legal: dict[str, dict[int, float]] = field(default_factory=dict)
    strategic: dict[str, dict[int, float]] = field(default_factory=dict)
    sell_willingness: dict[str, dict[int, float]] = field(default_factory=dict)
    confidence: dict[str, str] = field(default_factory=dict)
    rationale: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, float] = field(
        default_factory=lambda: {
            "legal": 1.0,
            "strategic": 1.0,
            "sell_willingness": 0.75,
        }
    )
    #: Memoized lookups. Simulation queries these millions of times.
    _cache: dict[tuple[str, str, int], float] = field(
        default_factory=dict, repr=False, compare=False
    )

    def invalidate(self) -> None:
        self._cache.clear()

    # --------------------------------------------------------------- lookups
    @staticmethod
    def _lookup(
        table: Mapping[str, Mapping[int, float]],
        card: Card,
        turn: int,
        default: float,
    ) -> float:
        entry = table.get(card.key) or table.get(normalize_name(card.card_id or ""))
        if entry is None:
            return default
        # Turn keys may arrive as ints or JSON string keys.
        best: Optional[float] = None
        for raw_turn, value in entry.items():
            t = int(raw_turn)
            if t <= turn and (best is None or t > best[0]):  # type: ignore[index]
                best = (t, value)  # type: ignore[assignment]
        if best is None:
            # Only later turns are specified: use the earliest listed value.
            earliest = min(int(t) for t in entry)
            return float(entry[earliest] if earliest in entry else entry[str(earliest)])
        return float(best[1])  # type: ignore[index]

    def legal_playability(self, card: Card, turn: int) -> float:
        cached = self._cache.get(("legal", card.key, turn))
        if cached is None:
            cached = self._lookup(self.legal, card, turn, self.defaults["legal"])
            self._cache[("legal", card.key, turn)] = cached
        return cached

    def strategic_playability(self, card: Card, turn: int) -> float:
        cached = self._cache.get(("strategic", card.key, turn))
        if cached is None:
            strategic = self._lookup(
                self.strategic, card, turn, self.defaults["strategic"]
            )
            cached = min(strategic, self.legal_playability(card, turn))
            self._cache[("strategic", card.key, turn)] = cached
        return cached

    def willingness(self, card: Card, turn: int) -> float:
        if not card.is_sellable:
            return 0.0
        cached = self._cache.get(("willingness", card.key, turn))
        if cached is None:
            cached = self._lookup(
                self.sell_willingness, card, turn, self.defaults["sell_willingness"]
            )
            self._cache[("willingness", card.key, turn)] = cached
        return cached

    def method_for(self, card: Card) -> str:
        return self.source

    # ------------------------------------------------------------ (de)serial
    def to_dict(self) -> dict[str, Any]:  # noqa: D102
        def dump(table: Mapping[str, Mapping[int, float]]) -> dict[str, Any]:
            return {k: {str(t): v for t, v in sorted(inner.items())} for k, inner in table.items()}

        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "defaults": dict(self.defaults),
            "legal": dump(self.legal),
            "strategic": dump(self.strategic),
            "sell_willingness": dump(self.sell_willingness),
            "confidence": dict(self.confidence),
            "rationale": dict(self.rationale),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlayabilityProfile":
        def load(table: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[int, float]]:
            return {
                normalize_name(k): {int(t): float(v) for t, v in inner.items()}
                for k, inner in (table or {}).items()
            }

        profile = cls(
            name=data.get("name", "default"),
            description=data.get("description", ""),
            source=data.get("source", "HEURISTIC — Human Estimate"),
            legal=load(data.get("legal", {})),
            strategic=load(data.get("strategic", {})),
            sell_willingness=load(data.get("sell_willingness", {})),
            confidence={normalize_name(k): v for k, v in (data.get("confidence") or {}).items()},
            rationale={normalize_name(k): v for k, v in (data.get("rationale") or {}).items()},
        )
        if "defaults" in data:
            profile.defaults.update(data["defaults"])
        return profile


@dataclass
class DrawSource:
    """A conditional draw effect, described honestly.

    Expected extra draws are *reported*, never substituted into an exact
    hypergeometric target-access formula.
    """

    name: str
    copies: int
    cards_drawn: int = 1
    earliest_turn: int = 1
    activation_probability_by_turn: dict[int, float] = field(default_factory=dict)
    resource_cost: int = 0
    requires_board_state: bool = False
    requires_opponent_state: bool = False
    repeatable: bool = False
    consumes_resource_needed_for_target: bool = False

    def activation(self, turn: int) -> float:
        if turn < self.earliest_turn:
            return 0.0
        if not self.activation_probability_by_turn:
            return 1.0
        eligible = [t for t in self.activation_probability_by_turn if t <= turn]
        if not eligible:
            return 0.0
        return float(self.activation_probability_by_turn[max(eligible)])

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["activation_probability_by_turn"] = {
            str(k): v for k, v in self.activation_probability_by_turn.items()
        }
        return data


def unique_cards(deck: Deck) -> Iterable[Card]:
    seen: set[str] = set()
    for entry in deck.main:
        if entry.card.key not in seen:
            seen.add(entry.card.key)
            yield entry.card
