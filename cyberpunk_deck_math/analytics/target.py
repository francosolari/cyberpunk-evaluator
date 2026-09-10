"""Layered target playability.

The six layers are computed and reported separately, and never collapsed:

    P(SEEN)                  exact hypergeometric
    P(IN HAND)               simulated (cards leave hand)
    P(AFFORDABLE)            simulated resource accounting
    P(LEGAL)                 legal playability profile x affordability
    P(STRATEGICALLY PLAYABLE) strategic playability profile
    P(ACTUALLY PLAYED)       what the simulated pilot did
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import RuleConfig
from ..methods import Method, Result
from ..models import Deck, PlayabilityProfile
from ..probability import sells
from ..simulation.board_proxy import BoardProxy
from ..simulation.game import SimulationSummary, resource_threshold_rate, simulate
from ..simulation.gigs import GigDistribution
from ..simulation.pilot import PilotPolicy
from ..probability.mulligan import MulliganPolicy
from . import access


@dataclass
class TargetReport:
    card_name: str
    turn: int
    seen: Result
    seen_simulated: Result
    in_hand: Result
    affordable: Result
    legal: Result
    strategic: Result
    played: Result
    sells_through: Result
    resources_available: Result
    seen_and_sellables: Result
    draws_by_source: dict[str, float] = field(default_factory=dict)
    summary: Optional[SimulationSummary] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "card": self.card_name,
            "turn": self.turn,
            "layers": {
                "1_raw_card_access": self.seen.to_dict(),
                "1b_raw_card_access_with_mulligan": self.seen_simulated.to_dict(),
                "2_resource_access": self.resources_available.to_dict(),
                "3_in_hand": self.in_hand.to_dict(),
                "4_affordable": self.affordable.to_dict(),
                "5_legal_playability": self.legal.to_dict(),
                "6_strategic_playability": self.strategic.to_dict(),
                "7_actually_played": self.played.to_dict(),
            },
            "sells_through_turn": self.sells_through.to_dict(),
            "target_and_sellables": self.seen_and_sellables.to_dict(),
            "average_draws_by_source": self.draws_by_source,
        }

    def render(self) -> str:
        lines = [
            f"TARGET: {self.card_name} on turn {self.turn}",
            f"  P(seen, no mulligan)         {self.seen.formatted()}   [{self.seen.method.value}]",
            f"  P(seen, with mulligan)       {self.seen_simulated.formatted()}",
            f"  P(in hand)                   {self.in_hand.formatted()}   [{self.in_hand.method.value}]",
            f"  P(affordable)                {self.affordable.formatted()}",
            f"  P(legally playable)          {self.legal.formatted()}",
            "    (simulated affordability x the profile's legal-playability curve;"
            " a purely cost-derived curve double-counts cost — see the README)",
            f"  P(strategically playable)    {self.strategic.formatted()}",
            f"  P(actually played by T{self.turn})     {self.played.formatted()}",
            "",
            f"  P(sold every turn through T{self.turn})  {self.sells_through.formatted()}   "
            f"[{self.sells_through.method.value}]",
            f"  P(>= cost usable resources)  {self.resources_available.formatted()}",
            f"  P(target AND enough sellables seen) {self.seen_and_sellables.formatted()}",
        ]
        if self.draws_by_source:
            lines.append("  Average extra draws per game by source:")
            for name, value in sorted(
                self.draws_by_source.items(), key=lambda kv: -kv[1]
            ):
                lines.append(f"    {name:<28} {value:.3f}")
        return "\n".join(lines)


def _with_note(result: Result) -> Result:
    return Result(
        value=result.value,
        method=result.method,
        label=result.label,
        detail="Natural draws only: no mulligan and no conditional draw effects.",
        assumptions=result.assumptions,
    )


def target_report(
    deck: Deck,
    card_name: str,
    turn: int,
    profile: PlayabilityProfile,
    rules: Optional[RuleConfig] = None,
    mulligan: Optional[MulliganPolicy] = None,
    iterations: int = 50_000,
    seed: Optional[int] = 20770301,
    gig_distribution: Optional[GigDistribution] = None,
    board_proxy: Optional[BoardProxy] = None,
    summary: Optional[SimulationSummary] = None,
) -> TargetReport:
    rules = rules or RuleConfig()
    entry = deck.find(card_name)
    if entry is None:
        raise KeyError(f"{card_name} is not in this deck")
    cost = entry.card.cost or 0

    policy = PilotPolicy(
        target_names=(entry.card.name,), profile=profile, mulligan=mulligan
    )
    if summary is None:
        summary = simulate(
            deck, policy, rules, iterations, seed, max(turn, 1),
            gig_distribution, board_proxy, profile,
        )

    strategic_estimate = profile.strategic_playability(entry.card, turn)
    in_hand = summary.rate("target_in_hand", turn, f"P({entry.card.name} in hand on T{turn})")
    legal = summary.rate("target_legal", turn, f"P({entry.card.name} legally playable T{turn})")
    strategic = summary.rate(
        "target_strategic", turn, f"P({entry.card.name} strategically playable T{turn})"
    )
    strategic = Result(
        value=strategic.value,
        method=Method.SIMULATED,
        label=strategic.label,
        detail=(
            "Simulated affordability and legality, gated by the strategic "
            f"playability of the '{profile.name}' profile "
            f"({strategic_estimate:.0%} on T{turn}) — that gate is a "
            f"{profile.source} assumption, so this layer is only as good as it."
        ),
        assumptions=dict(strategic.assumptions, profile=profile.name,
                         strategic_playability=strategic_estimate),
        sample_size=strategic.sample_size,
        standard_error=strategic.standard_error,
        ci95=strategic.ci95,
    )

    return TargetReport(
        card_name=entry.card.name,
        turn=turn,
        seen=_with_note(access.raw_access(deck, entry.card.name, turn, rules)),
        seen_simulated=summary.rate(
            "target_seen", turn, f"P({entry.card.name} seen by T{turn}, with mulligans)"
        ),
        in_hand=in_hand,
        affordable=summary.rate("target_affordable", turn, f"P(affordable T{turn})"),
        legal=legal,
        strategic=strategic,
        played=summary.rate("target_played", turn, f"P(played by T{turn})"),
        sells_through=sells.consecutive_sells(deck.size, deck.sellable_count, turn, rules),
        resources_available=resource_threshold_rate(
            deck, cost, turn, policy, rules, max(5_000, iterations // 5), seed,
            gig_distribution, board_proxy,
        ),
        seen_and_sellables=access.target_and_sellables(
            deck, entry.card.name, turn, cost, rules
        ),
        draws_by_source={
            k: v / summary.iterations for k, v in summary.draws_by_source.items()
        },
        summary=summary,
    )
