"""Local normalized card cache.

Analysis never touches the network: it reads this cache.  ``cli.py
update-cards`` (or the Streamlit "Update Card Database" button) is the only
thing that fetches.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from ..config import DEFAULT_CARD_CACHE
from ..models import Card, normalize_name

CACHE_FORMAT_VERSION = 1


@dataclass
class MatchResult:
    """The outcome of looking a decklist line up in the database."""

    query: str
    card: Optional[Card] = None
    candidates: list[Card] = field(default_factory=list)
    reason: str = ""

    @property
    def matched(self) -> bool:
        return self.card is not None

    @property
    def ambiguous(self) -> bool:
        return self.card is None and len(self.candidates) > 1


@dataclass
class CardDatabase:
    """An indexed collection of normalized cards."""

    cards: list[Card] = field(default_factory=list)
    source_url: Optional[str] = None
    updated_at: Optional[str] = None
    version: int = CACHE_FORMAT_VERSION
    data_provenance: str = "official"
    notes: list[str] = field(default_factory=list)

    _by_name: dict[str, list[Card]] = field(default_factory=dict, repr=False)
    _by_id: dict[str, Card] = field(default_factory=dict, repr=False)
    _by_collector: dict[str, list[Card]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.reindex()

    # ---------------------------------------------------------------- indexing
    def reindex(self) -> None:
        self._by_name = {}
        self._by_id = {}
        self._by_collector = {}
        for card in self.cards:
            self._by_name.setdefault(card.key, []).append(card)
            if card.card_id:
                self._by_id[card.card_id.strip().lower()] = card
            if card.collector_number:
                num = card.collector_number.strip().lower()
                self._by_collector.setdefault(num, []).append(card)
                self._by_collector.setdefault(num.lstrip("0") or "0", []).append(card)
                if card.set_code:
                    combo = f"{card.set_code.strip().lower()}-{num}"
                    self._by_collector.setdefault(combo, []).append(card)

    def __len__(self) -> int:
        return len(self.cards)

    def __iter__(self) -> Iterator[Card]:
        return iter(self.cards)

    # ---------------------------------------------------------------- matching
    def match(
        self, query: str, set_code: Optional[str] = None, collector: Optional[str] = None
    ) -> MatchResult:
        """Resolve a decklist reference to exactly one card, or explain why not."""
        raw = (query or "").strip()
        if not raw:
            return MatchResult(query=query, reason="empty reference")

        # 1. exact card id
        card = self._by_id.get(raw.lower())
        if card is not None:
            return MatchResult(query=query, card=card)

        # 2. collector number (optionally with a set code)
        for key in filter(
            None,
            [
                f"{set_code.strip().lower()}-{collector.strip().lower()}"
                if set_code and collector
                else None,
                collector.strip().lower() if collector else None,
                raw.lower(),
            ],
        ):
            hits = self._unique(self._by_collector.get(key, []), set_code)
            if len(hits) == 1:
                return MatchResult(query=query, card=hits[0])
            if len(hits) > 1:
                return MatchResult(
                    query=query,
                    candidates=hits,
                    reason=f"collector number {key!r} matches {len(hits)} cards",
                )

        # 3. exact normalized name
        hits = self._unique(self._by_name.get(normalize_name(raw), []), set_code)
        if len(hits) == 1:
            return MatchResult(query=query, card=hits[0])
        if len(hits) > 1:
            return MatchResult(
                query=query,
                candidates=hits,
                reason=f"name matches {len(hits)} printings; add a set code or card id",
            )

        # 4. prefix match on the name before a subtitle dash
        key = normalize_name(raw)
        prefix_hits = [
            c
            for c in self.cards
            if c.key == key or c.key.startswith(key + " ") or key.startswith(c.key + " ")
        ]
        prefix_hits = self._unique(prefix_hits, set_code)
        if len(prefix_hits) == 1:
            return MatchResult(
                query=query,
                card=prefix_hits[0],
                reason="matched on name prefix",
            )
        if len(prefix_hits) > 1:
            return MatchResult(
                query=query,
                candidates=prefix_hits,
                reason=f"{len(prefix_hits)} cards start with {raw!r}",
            )

        return MatchResult(query=query, reason="not found in the cached Beta card pool")

    @staticmethod
    def _unique(cards: Iterable[Card], set_code: Optional[str]) -> list[Card]:
        seen: dict[str, Card] = {}
        for card in cards:
            if set_code and (card.set_code or "").lower() != set_code.lower():
                continue
            seen[card.card_id] = card
        return list(seen.values())

    def get(self, name_or_id: str) -> Optional[Card]:
        result = self.match(name_or_id)
        return result.card

    def require(self, name_or_id: str) -> Card:
        card = self.get(name_or_id)
        if card is None:
            raise KeyError(f"card not in database: {name_or_id}")
        return card

    def legends(self) -> list[Card]:
        return [c for c in self.cards if c.is_legend]

    # -------------------------------------------------------------- (de)serial
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source_url": self.source_url,
            "updated_at": self.updated_at,
            "data_provenance": self.data_provenance,
            "notes": self.notes,
            "card_count": len(self.cards),
            "cards": [c.to_dict() for c in self.cards],
        }

    def save(self, path: str | Path = DEFAULT_CARD_CACHE) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".csv":
            self._save_csv(path)
        else:
            path.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return path

    def _save_csv(self, path: Path) -> None:
        fields = [f for f in Card.__dataclass_fields__ if not f.startswith("_")]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for card in self.cards:
                row = card.to_dict()
                row["tags"] = "|".join(row["tags"] or [])
                row["effect_metadata"] = json.dumps(row["effect_metadata"] or [])
                writer.writerow(row)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CARD_CACHE) -> "CardDatabase":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"no card cache at {path}. Run `python cli.py update-cards` to build "
                "one from the official Cyberpunk TCG card database."
            )
        if path.suffix.lower() == ".csv":
            return cls._load_csv(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            cards=[Card.from_dict(c) for c in data.get("cards", [])],
            source_url=data.get("source_url"),
            updated_at=data.get("updated_at"),
            version=int(data.get("version", CACHE_FORMAT_VERSION)),
            data_provenance=data.get("data_provenance", "official"),
            notes=list(data.get("notes", [])),
        )

    @classmethod
    def _load_csv(cls, path: Path) -> "CardDatabase":
        cards: list[Card] = []
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                clean: dict[str, Any] = dict(row)
                clean["tags"] = [t for t in (row.get("tags") or "").split("|") if t]
                clean["effect_metadata"] = json.loads(row.get("effect_metadata") or "[]")
                for key in ("cost", "ram"):
                    clean[key] = int(row[key]) if row.get(key) not in (None, "") else None
                for key in ("sellable", "starter_exclusive", "is_legend"):
                    value = row.get(key)
                    clean[key] = None if value in (None, "") else value == "True"
                for key, value in list(clean.items()):
                    if value == "":
                        clean[key] = None
                clean["is_legend"] = bool(clean.get("is_legend"))
                clean["interpretation_status"] = row.get("interpretation_status") or "raw"
                cards.append(Card.from_dict(clean))
        return cls(cards=cards, data_provenance="unknown")

    def merge_interpretations(self, other: "CardDatabase") -> int:
        """Carry human-verified interpretations across a database refresh."""
        carried = 0
        index = {c.card_id: c for c in other.cards}
        for card in self.cards:
            previous = index.get(card.card_id)
            if previous is None:
                continue
            if previous.interpretation_status == "human_verified" and previous.effect_metadata:
                card.effect_metadata = previous.effect_metadata
                card.interpretation_status = previous.interpretation_status
                card.interpretation_notes = previous.interpretation_notes
                carried += 1
        return carried


def load_database(path: str | Path | None = None) -> CardDatabase:
    return CardDatabase.load(path or DEFAULT_CARD_CACHE)
