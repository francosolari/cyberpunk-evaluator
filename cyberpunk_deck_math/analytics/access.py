"""Raw card access, compound access, and conditional-draw contribution.

The five layers the application refuses to collapse are kept apart here:

1. RAW CARD ACCESS       — P(seen), exact hypergeometric
2. RESOURCE ACCESS       — P(enough sellables/resources), exact
3. LEGAL PLAYABILITY     — cost/requirements met, profile-driven
4. STRATEGIC PLAYABILITY — worth playing, profile-driven
5. SIMULATED PILOT       — what the Monte Carlo pilot actually did

Layers 1-2 are exact.  Layers 3-4 are heuristics.  Layer 5 lives in
:mod:`cyberpunk_deck_math.simulation`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from ..config import RuleConfig
from ..methods import Method, Result
from ..models import Card, Deck, DrawSource, PlayabilityProfile
from ..probability import hypergeom
from ..probability.multivariate import Group, compound_result


def raw_access(deck: Deck, card_name: str, turn: int, rules: Optional[RuleConfig] = None,
               k: int = 1) -> Result:
    """P(at least ``k`` copies of ``card_name`` seen by ``turn``)."""
    rules = rules or RuleConfig()
    copies = deck.copies_of(card_name)
    seen = rules.cards_seen(turn)
    return Result(
        value=hypergeom.at_least(deck.size, copies, seen, k),
        method=Method.EXACT_HYPERGEOMETRIC,
        label=f"P(>= {k} {card_name} seen by T{turn})",
        assumptions={
            "deck_size": deck.size,
            "copies": copies,
            "cards_seen": seen,
            "turn": turn,
        },
    )


def access_curve(
    deck: Deck, card_name: str, max_turn: int = 6, rules: Optional[RuleConfig] = None
) -> dict[str, Result]:
    """Opening hand plus T1..``max_turn`` access for one card."""
    rules = rules or RuleConfig()
    curve = {"opening": raw_access(deck, card_name, 0, rules)}
    curve["opening"].assumptions["turn"] = "opening hand"
    for turn in range(1, max_turn + 1):
        curve[f"T{turn}"] = raw_access(deck, card_name, turn, rules)
    return curve


def copies_comparison(
    deck_size: int,
    copy_counts: Sequence[int] = (1, 2, 3),
    max_turn: int = 6,
    rules: Optional[RuleConfig] = None,
) -> dict[int, dict[str, Result]]:
    """The classic copies-by-turn access table."""
    rules = rules or RuleConfig()
    table: dict[int, dict[str, Result]] = {}
    for copies in copy_counts:
        row: dict[str, Result] = {
            "opening": hypergeom.access_result(
                deck_size, copies, rules.cards_seen(0), 1,
                label=f"{copies} copies, opening hand",
            )
        }
        for turn in range(1, max_turn + 1):
            row[f"T{turn}"] = hypergeom.access_result(
                deck_size, copies, rules.cards_seen(turn), 1,
                label=f"{copies} copies by T{turn}",
            )
        table[copies] = row
    return table


def exact_counts(
    deck: Deck, card_name: str, turn: int, rules: Optional[RuleConfig] = None
) -> dict[int, Result]:
    """P(exactly k copies seen) for every reachable k."""
    rules = rules or RuleConfig()
    copies = deck.copies_of(card_name)
    seen = rules.cards_seen(turn)
    out: dict[int, Result] = {}
    for k in range(0, min(copies, seen) + 1):
        out[k] = Result(
            value=hypergeom.exactly(deck.size, copies, seen, k),
            method=Method.EXACT_HYPERGEOMETRIC,
            label=f"P(exactly {k} {card_name} by T{turn})",
        )
    return out


# --------------------------------------------------------------- compound access


@dataclass
class GroupSpec:
    """A named, disjoint slice of the deck for multivariate questions."""

    name: str
    card_names: tuple[str, ...] = ()
    tag: Optional[str] = None
    sellable: Optional[bool] = None
    minimum: int = 1

    def size(self, deck: Deck, taken: set[str]) -> int:
        total = 0
        for entry in deck.main:
            if entry.card.key in taken:
                continue
            if self.matches(entry.card):
                total += entry.copies
                taken.add(entry.card.key)
        return total

    def matches(self, card: Card) -> bool:
        from ..models import normalize_name

        if self.card_names and card.key in {normalize_name(n) for n in self.card_names}:
            return True
        if self.tag and card.has_tag(self.tag):
            return True
        if self.sellable is not None and card.is_sellable == self.sellable:
            return True
        return False


def compound_access(
    deck: Deck,
    specs: Sequence[GroupSpec],
    turn: int,
    rules: Optional[RuleConfig] = None,
    forbidden: Optional[Mapping[str, int]] = None,
    label: str = "",
) -> Result:
    """Exact P(all group minimums met) in the cards seen by ``turn``.

    Groups are made disjoint in the order given: a card already claimed by an
    earlier group is not counted twice.
    """
    rules = rules or RuleConfig()
    taken: set[str] = set()
    groups = [Group(spec.name, spec.size(deck, taken)) for spec in specs]
    requirements = {spec.name: spec.minimum for spec in specs}
    result = compound_result(
        groups, deck.size, rules.cards_seen(turn), requirements,
        label=label, forbidden=forbidden,
    )
    result.assumptions["turn"] = turn
    return result


def target_and_sellables(
    deck: Deck,
    target_name: str,
    turn: int,
    sellables_needed: int,
    rules: Optional[RuleConfig] = None,
) -> Result:
    """P(target AND at least ``sellables_needed`` sellables) by ``turn``."""
    return compound_access(
        deck,
        [
            GroupSpec("target", card_names=(target_name,), minimum=1),
            GroupSpec("sellables", sellable=True, minimum=sellables_needed),
        ],
        turn,
        rules,
        label=f"P({target_name} AND >= {sellables_needed} sellables by T{turn})",
    )


# --------------------------------------------------------- conditional draw value


def draw_sources_from_deck(
    deck: Deck,
    profile: Optional[PlayabilityProfile] = None,
    draw_tag: str = "draw",
) -> list[DrawSource]:
    """Build :class:`DrawSource` records from card metadata and the profile."""
    sources: list[DrawSource] = []
    for entry in deck.main:
        card = entry.card
        draw_effects = [e for e in card.effect_metadata or [] if e.get("effect") == "draw"]
        if not draw_effects and not card.has_tag(draw_tag):
            continue
        amount = sum(int(e.get("amount", 1)) for e in draw_effects) or 1
        conditions = [c for e in draw_effects for c in e.get("conditions", [])]
        requires_opponent = any(
            c.get("type") == "opponent_state_proxy" for c in conditions
        )
        requires_board = any(
            c.get("type")
            in ("friendly_unit_count", "enemy_unit_count", "card_type_in_play")
            for c in conditions
        )
        activation = {}
        if profile is not None:
            activation = {
                t: profile.strategic_playability(card, t) for t in range(1, 7)
            }
        sources.append(
            DrawSource(
                name=card.name,
                copies=entry.copies,
                cards_drawn=amount,
                earliest_turn=max(1, card.cost or 1),
                activation_probability_by_turn=activation,
                resource_cost=card.cost or 0,
                requires_board_state=requires_board,
                requires_opponent_state=requires_opponent,
                repeatable=False,
                consumes_resource_needed_for_target=bool(card.cost),
            )
        )
    return sources


def expected_extra_draws(
    deck: Deck,
    source: DrawSource,
    turn: int,
    rules: Optional[RuleConfig] = None,
) -> Result:
    """P(seen) x P(active) x cards drawn — reported, never substituted.

    This number must NOT be fed back into a hypergeometric target-access
    formula.  For exact target access with conditional draws, use the Monte
    Carlo simulator.
    """
    rules = rules or RuleConfig()
    seen = hypergeom.at_least(deck.size, source.copies, rules.cards_seen(turn), 1)
    activation = source.activation(turn)
    value = seen * activation * source.cards_drawn
    return Result(
        value=value,
        method=Method.HEURISTIC_HUMAN,
        label=f"Expected extra draws from {source.name} by T{turn}",
        detail=(
            "EXPECTED EXTRA DRAWS. Do not substitute into hypergeometric "
            "target-access math; use simulation for exact outcomes."
        ),
        assumptions={
            "p_seen": seen,
            "p_active": activation,
            "cards_drawn": source.cards_drawn,
            "requires_opponent_state": source.requires_opponent_state,
            "resource_cost": source.resource_cost,
        },
    )


def draw_engine_report(
    deck: Deck,
    profile: Optional[PlayabilityProfile] = None,
    max_turn: int = 6,
    rules: Optional[RuleConfig] = None,
) -> dict[str, dict[str, Result]]:
    report: dict[str, dict[str, Result]] = {}
    for source in draw_sources_from_deck(deck, profile):
        report[source.name] = {
            f"T{t}": expected_extra_draws(deck, source, t, rules)
            for t in range(1, max_turn + 1)
        }
    return report
