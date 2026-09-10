"""The deck dashboard: composition, sellables, consistency, burden, density."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Optional, Sequence

from ..config import AnalysisConfig
from ..methods import Result
from ..models import Deck, PlayabilityProfile
from . import access, axioms, dead_cards, opportunity_density, sell_density


@dataclass
class Composition:
    deck_size: int
    legends: list[str]
    average_cost: Optional[float]
    cost_curve: dict[str, int]
    card_types: dict[str, int]
    draw_sources: dict[str, int]
    conditional_draw_sources: dict[str, int]
    reactive_cards: dict[str, int]
    finishers: dict[str, int]
    early_dead_cards: dict[str, int]
    provenance: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def composition(
    deck: Deck, profile: Optional[PlayabilityProfile] = None, early_turn: int = 2
) -> Composition:
    costs = [e.card.cost for e in deck.main for _ in range(e.copies) if e.card.cost is not None]
    curve: dict[str, int] = {}
    for entry in deck.main:
        key = str(entry.card.cost) if entry.card.cost is not None else "unknown"
        curve[key] = curve.get(key, 0) + entry.copies

    types: dict[str, int] = {}
    draws: dict[str, int] = {}
    conditional: dict[str, int] = {}
    reactive: dict[str, int] = {}
    finishers: dict[str, int] = {}
    dead: dict[str, int] = {}
    provenance: dict[str, int] = {}

    for entry in deck.main:
        card = entry.card
        types[card.type or "unknown"] = types.get(card.type or "unknown", 0) + entry.copies
        provenance[card.data_provenance] = provenance.get(card.data_provenance, 0) + entry.copies
        draw_effects = [e for e in card.effect_metadata or [] if e.get("effect") == "draw"]
        if draw_effects or card.has_tag("draw"):
            draws[card.name] = entry.copies
            if any(e.get("conditions") for e in draw_effects) or not draw_effects:
                conditional[card.name] = entry.copies
        if card.has_tag("reactive"):
            reactive[card.name] = entry.copies
        if card.has_tag("finisher"):
            finishers[card.name] = entry.copies
        if profile is not None and profile.strategic_playability(card, early_turn) <= 0.0:
            dead[card.name] = entry.copies

    return Composition(
        deck_size=deck.size,
        legends=[c.name for c in deck.legends],
        average_cost=(mean(costs) if costs else None),
        cost_curve=dict(sorted(curve.items(), key=lambda kv: (kv[0] == "unknown", kv[0]))),
        card_types=types,
        draw_sources=draws,
        conditional_draw_sources=conditional,
        reactive_cards=reactive,
        finishers=finishers,
        early_dead_cards=dead,
        provenance=provenance,
    )


@dataclass
class DeckSummary:
    deck_name: str
    composition: Composition
    sell: sell_density.SellReport
    action_density: dict[int, Result]
    dead_burden: dict[int, Result]
    target_access: dict[str, dict[str, Result]] = field(default_factory=dict)
    warnings: list[axioms.Axiom] = field(default_factory=list)
    config: Optional[AnalysisConfig] = None
    profile_name: str = ""
    profile_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "deck_name": self.deck_name,
            "composition": self.composition.to_dict(),
            "sell": self.sell.to_dict(),
            "action_density": {f"T{t}": r.to_dict() for t, r in self.action_density.items()},
            "dead_card_burden": {f"T{t}": r.to_dict() for t, r in self.dead_burden.items()},
            "target_access": {
                name: {turn: r.to_dict() for turn, r in curve.items()}
                for name, curve in self.target_access.items()
            },
            "warnings": [w.to_dict() for w in self.warnings],
            "playability_profile": {"name": self.profile_name, "source": self.profile_source},
            "config": self.config.to_dict() if self.config else None,
        }


def summarize(
    deck: Deck,
    profile: Optional[PlayabilityProfile] = None,
    config: Optional[AnalysisConfig] = None,
    targets: Sequence[str] = (),
) -> DeckSummary:
    config = config or AnalysisConfig()
    max_turn = config.max_turn
    return DeckSummary(
        deck_name=deck.name,
        composition=composition(deck, profile),
        sell=sell_density.sell_report(
            deck, config.sellable, config.rules, profile, max_turn
        ),
        action_density=(
            opportunity_density.density_curve(deck, profile, max_turn) if profile else {}
        ),
        dead_burden=(
            dead_cards.burden_curve(deck, profile, max_turn, tuple(targets)) if profile else {}
        ),
        target_access={
            name: access.access_curve(deck, name, max_turn, config.rules) for name in targets
        },
        warnings=axioms.evaluate_axioms(deck, profile, config),
        config=config,
        profile_name=profile.name if profile else "",
        profile_source=profile.source if profile else "",
    )


def render_summary(summary: DeckSummary) -> str:
    """A terminal-friendly rendering of the dashboard."""
    comp = summary.composition
    status = summary.sell.status
    lines = [
        f"DECK: {summary.deck_name}",
        f"  Deck size:                 {comp.deck_size}",
        f"  Legends:                   {', '.join(comp.legends) or '(none)'}",
        f"  Average cost:              "
        + (f"{comp.average_cost:.2f}" if comp.average_cost is not None else "unknown"),
        "",
        "SELLABLE STATUS                                   [USER / PLAYTESTING HEURISTIC targets]",
        f"  Mechanical sellables:      {status.sellable_count}/{status.deck_size} = {status.actual_pct:.1%}",
    ]
    if summary.sell.effective:
        for turn in sorted(summary.sell.effective)[:3]:
            lines.append(
                f"  Effective sellable T{turn}:     {summary.sell.effective[turn].value:.1%}"
            )
    lines += [
        f"  Minimum:                   {status.minimum_pct:.1%}",
        f"  Target:                    {status.target_pct:.1%}",
        f"  Target range:              {status.target_range[0]:.1%}–{status.target_range[1]:.1%}",
        f"  Status:                    {status.status}",
        f"  Cards to reach minimum:    {status.cards_to_minimum}",
        f"  Cards to reach target:     {status.cards_to_target}",
        "",
        "COST CURVE",
        "  " + "  ".join(f"{k}:{v}" for k, v in comp.cost_curve.items()),
        "CARD TYPES",
        "  " + "  ".join(f"{k}:{v}" for k, v in comp.card_types.items()),
    ]
    if comp.draw_sources:
        lines.append("DRAW SOURCES")
        for name, copies in comp.draw_sources.items():
            flag = " (conditional)" if name in comp.conditional_draw_sources else ""
            lines.append(f"  {copies}x {name}{flag}")
    if comp.reactive_cards:
        lines.append("REACTIVE CARDS")
        lines += [f"  {c}x {n}" for n, c in comp.reactive_cards.items()]
    if comp.finishers:
        lines.append("FINISHERS")
        lines += [f"  {c}x {n}" for n, c in comp.finishers.items()]

    lines += ["", "SELL CONSISTENCY                                  [EXACT — Hypergeometric]"]
    for turn, result in summary.sell.consecutive.items():
        lines.append(f"  Sell every turn through T{turn}: {result.value:.2%}")

    if summary.action_density:
        lines += ["", f"ACTION DENSITY                                    [{summary.profile_source}]"]
        lines += [
            f"  T{t}: {r.value:.1%}" for t, r in summary.action_density.items()
        ]
    if summary.dead_burden:
        lines += ["", f"DEAD-CARD BURDEN                                  [{summary.profile_source}]"]
        lines += [f"  T{t}: {r.value:.1%}" for t, r in summary.dead_burden.items()]

    for name, curve in summary.target_access.items():
        lines += ["", f"TARGET ACCESS: {name}                [EXACT — Hypergeometric]"]
        lines.append(
            "  " + "  ".join(f"{k}:{r.value:.1%}" for k, r in curve.items())
        )

    if summary.warnings:
        lines += ["", "AXIOMS / WARNINGS"]
        for warning in summary.warnings:
            lines.append(f"  [{warning.level.upper()}] {warning.message}")
    return "\n".join(lines)
