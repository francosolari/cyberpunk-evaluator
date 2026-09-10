"""Decklist parsing.

Supported line shapes::

    3x Zetatech Faceplate
    3 Zetatech Faceplate
    1x 106 Alt Cunningham — Soulkiller Architect     (collector number)
    3x A027                                          (card id)
    1x MS01-131                                      (set-qualified id)
    2x Field Operator (MS01)                         (trailing set code)

Headings (``Legends``, ``Main Deck``, ``Name:``), ``#`` comments and blank
lines are understood.  Every other line becomes a *warning* — nothing is
silently ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .config import RuleConfig
from .database.cache import CardDatabase, MatchResult
from .models import Card, Deck, DeckEntry

LEGEND_HEADINGS = {"legend", "legends", "legend deck", "legends:"}
MAIN_HEADINGS = {
    "main",
    "main deck",
    "maindeck",
    "deck",
    "main deck:",
    "cards",
}
NAME_PREFIXES = ("name:", "deck:", "deck name:", "title:")

#: ``3x``/``3 x``/``3``/``x3`` followed by the card reference.
COUNT_RE = re.compile(r"^(?:(?P<count>\d+)\s*[xX*]?|[xX](?P<count2>\d+))[\s:.\-]+(?P<rest>.+)$")
#: trailing ``(MS01)`` / ``[MS01]`` set code
SET_RE = re.compile(r"[\(\[]([A-Za-z0-9]{2,8})[\)\]]\s*$")
#: leading collector number, e.g. ``106 Alt Cunningham``
LEADING_NUMBER_RE = re.compile(r"^(?P<number>\d{1,4})\s+(?P<rest>\D.*)$")
#: a bare identifier such as ``A027`` or ``MS01-131``
BARE_ID_RE = re.compile(r"^[A-Za-z]{1,6}\d{1,4}(?:-\d{1,4})?$|^[A-Za-z]{2,6}\d{2}-\d{1,4}$")


@dataclass
class ParsedLine:
    line_number: int
    raw: str
    count: int
    reference: str
    set_code: Optional[str] = None
    collector: Optional[str] = None
    section: str = "main"


@dataclass
class ParseResult:
    """The full outcome of parsing — cards, warnings, and everything unresolved."""

    deck: Deck
    warnings: list[str] = field(default_factory=list)
    unknown: list[tuple[int, str, str]] = field(default_factory=list)
    ambiguous: list[tuple[int, str, list[str]]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    matched_lines: list[tuple[int, str, Card]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.unknown and not self.ambiguous

    def render(self) -> str:
        lines = [f"Deck: {self.deck.name}  ({self.deck.size} cards, {len(self.deck.legends)} legends)"]
        for message in self.errors:
            lines.append(f"  ERROR      {message}")
        for number, text, reason in self.unknown:
            lines.append(f"  UNKNOWN    line {number}: {text!r} — {reason}")
        for number, text, candidates in self.ambiguous:
            lines.append(
                f"  AMBIGUOUS  line {number}: {text!r} — candidates: {', '.join(candidates)}"
            )
        for message in self.warnings:
            lines.append(f"  WARNING    {message}")
        return "\n".join(lines)


def _strip_comment(line: str) -> str:
    if "#" in line:
        line = line.split("#", 1)[0]
    if line.strip().startswith("//"):
        return ""
    return line.strip()


def _heading(text: str) -> Optional[str]:
    normalized = text.strip().rstrip(":").strip().lower()
    if normalized in {h.rstrip(":") for h in LEGEND_HEADINGS}:
        return "legends"
    if normalized in {h.rstrip(":") for h in MAIN_HEADINGS}:
        return "main"
    return None


def split_reference(reference: str) -> tuple[str, Optional[str], Optional[str]]:
    """Split a card reference into ``(name_or_id, set_code, collector_number)``."""
    text = reference.strip().strip("*").strip()
    set_code: Optional[str] = None
    match = SET_RE.search(text)
    if match:
        set_code = match.group(1)
        text = text[: match.start()].strip()

    collector: Optional[str] = None
    leading = LEADING_NUMBER_RE.match(text)
    if leading:
        collector = leading.group("number")
        text = leading.group("rest").strip()

    if collector is None and BARE_ID_RE.match(text):
        collector = text

    return text, set_code, collector


def parse_lines(text: str, rules: Optional[RuleConfig] = None) -> tuple[list[ParsedLine], list[str], str]:
    """Tokenize a decklist into ``(lines, warnings, deck name)``."""
    warnings: list[str] = []
    parsed: list[ParsedLine] = []
    section = "main"
    deck_name = "Untitled Deck"
    seen_legend_heading = False

    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw_line)
        if not line:
            continue

        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in NAME_PREFIXES):
            deck_name = line.split(":", 1)[1].strip() or deck_name
            continue

        heading = _heading(line)
        if heading:
            section = heading
            seen_legend_heading = seen_legend_heading or heading == "legends"
            continue

        match = COUNT_RE.match(line)
        if match:
            count = int(match.group("count") or match.group("count2"))
            reference = match.group("rest").strip()
        elif section == "legends":
            # FORMAT B lists legends one per line with no count.
            count, reference = 1, line
        else:
            warnings.append(
                f"line {number}: {line!r} has no copy count; assuming 1 copy"
            )
            count, reference = 1, line

        if count <= 0:
            warnings.append(f"line {number}: copy count {count} is not positive; skipped")
            continue

        name, set_code, collector = split_reference(reference)
        if not name:
            warnings.append(f"line {number}: {line!r} has no card reference; skipped")
            continue

        parsed.append(
            ParsedLine(
                line_number=number,
                raw=line,
                count=count,
                reference=name,
                set_code=set_code,
                collector=collector,
                section=section,
            )
        )

    return parsed, warnings, deck_name


def parse_decklist(
    text: str,
    database: CardDatabase,
    rules: Optional[RuleConfig] = None,
    deck_name: Optional[str] = None,
    ignore_legality: bool = False,
) -> ParseResult:
    """Parse a decklist and match it against the cached Beta card pool."""
    rules = rules or RuleConfig()
    lines, warnings, parsed_name = parse_lines(text, rules)
    deck = Deck(name=deck_name or parsed_name)
    result = ParseResult(deck=deck, warnings=warnings)

    for line in lines:
        match: MatchResult = database.match(
            line.reference, set_code=line.set_code, collector=line.collector
        )
        if match.ambiguous:
            result.ambiguous.append(
                (
                    line.line_number,
                    line.raw,
                    [f"{c.name} [{c.card_id}]" for c in match.candidates],
                )
            )
            continue
        if not match.matched:
            result.unknown.append((line.line_number, line.raw, match.reason))
            continue

        card = match.card
        assert card is not None
        if match.reason:
            result.warnings.append(f"line {line.line_number}: {match.reason}")
        result.matched_lines.append((line.line_number, line.raw, card))

        is_legend_section = line.section == "legends"
        if card.is_legend or is_legend_section:
            if not card.is_legend and is_legend_section:
                result.warnings.append(
                    f"line {line.line_number}: {card.name} is listed under Legends but the "
                    "card database does not mark it as a Legend"
                )
            for _ in range(line.count):
                deck.legends.append(card)
        else:
            entry = deck.find(card.name)
            if entry is None:
                deck.main.append(DeckEntry(card=card, copies=line.count))
            else:
                entry.copies += line.count

    result.errors.extend(validate_deck(deck, rules, ignore_legality))
    return result


def validate_deck(
    deck: Deck, rules: Optional[RuleConfig] = None, ignore_legality: bool = False
) -> list[str]:
    """Legality checks.  Returns messages; empty means legal."""
    rules = rules or RuleConfig()
    errors: list[str] = []
    if len(deck.legends) != rules.legend_count:
        errors.append(
            f"deck has {len(deck.legends)} Legends; exactly {rules.legend_count} are required"
        )
    if deck.size < rules.main_deck_min:
        errors.append(
            f"main deck has {deck.size} cards; the minimum is {rules.main_deck_min}"
        )
    if deck.size > rules.main_deck_max:
        errors.append(
            f"main deck has {deck.size} cards; the maximum is {rules.main_deck_max}"
        )
    for entry in deck.main:
        if entry.copies > rules.max_card_copies:
            errors.append(
                f"{entry.name}: {entry.copies} copies exceeds the maximum of "
                f"{rules.max_card_copies}"
            )
    duplicate_legends = {c.key for c in deck.legends}
    if len(duplicate_legends) != len(deck.legends):
        errors.append("Legends must be three different cards")
    return [] if ignore_legality else errors


def format_deck(deck: Deck) -> str:
    """Render a deck back to FORMAT A text."""
    lines = [f"Name: {deck.name}", "", "Legends", ""]
    lines += [f"1x {card.name}" for card in deck.legends]
    lines += ["", "Main Deck", ""]
    lines += [f"{entry.copies}x {entry.name}" for entry in deck.main]
    return "\n".join(lines)
