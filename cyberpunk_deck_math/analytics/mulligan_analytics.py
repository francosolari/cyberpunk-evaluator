"""Mulligan analytics: what a mulligan rule actually costs and buys.

A policy that raises target-card access while wrecking resource consistency
must be *visible* as a tradeoff, so every policy is reported on both axes at
once rather than on target access alone.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from ..config import RuleConfig
from ..methods import Result
from ..models import Deck, PlayabilityProfile
from ..probability.mulligan import HandContext, MulliganPolicy, hand_features
from ..simulation.board_proxy import BoardProxy
from ..simulation.game import proportion_result, simulate
from ..simulation.gigs import GigDistribution
from ..simulation.pilot import PilotPolicy
from ..simulation.state import GameState


@dataclass
class HandQualityRule:
    """What counts as a "good hand" when reporting hand quality."""

    min_sellables: int = 2
    min_early_playables: int = 1
    require_target_or_draw: bool = True

    def is_good(self, features: dict[str, float]) -> bool:
        if features["sellables"] < self.min_sellables:
            return False
        if features["early_playables"] < self.min_early_playables:
            return False
        if self.require_target_or_draw:
            return (features["target"] >= 1) or (features["early_draw_sources"] >= 1)
        return True


@dataclass
class OpeningHandStats:
    policy: str
    iterations: int
    mulligan_rate: Result
    keep_rate: Result
    target_in_opening: Result
    draw_source_in_opening: Result
    good_hand_rate: Result
    average_sellables: float
    average_effective_sellables: float
    average_dead_cards: float
    average_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "iterations": self.iterations,
            "mulligan_rate": self.mulligan_rate.to_dict(),
            "keep_rate": self.keep_rate.to_dict(),
            "target_in_opening_hand": self.target_in_opening.to_dict(),
            "draw_source_in_opening_hand": self.draw_source_in_opening.to_dict(),
            "good_hand_rate": self.good_hand_rate.to_dict(),
            "average_sellables_after_mulligan": self.average_sellables,
            "average_effective_sellables_after_mulligan": self.average_effective_sellables,
            "average_dead_cards_after_mulligan": self.average_dead_cards,
            "average_hand_score": self.average_score,
        }


def opening_hand_stats(
    deck: Deck,
    policy: MulliganPolicy,
    target_names: Sequence[str] = (),
    profile: Optional[PlayabilityProfile] = None,
    rules: Optional[RuleConfig] = None,
    iterations: int = 50_000,
    seed: Optional[int] = 20770301,
    quality: Optional[HandQualityRule] = None,
) -> OpeningHandStats:
    """Deal opening hands, apply the policy, and measure the kept hands."""
    rules = rules or RuleConfig()
    quality = quality or HandQualityRule()
    context = HandContext(
        target_names=tuple(target_names),
        profile=profile,
        score_config=policy.score_config,
    )
    rng = random.Random(seed)
    library = list(deck.cards())

    mulligans = 0
    targets = 0
    draw_sources = 0
    good = 0
    sellables = 0.0
    effective = 0.0
    dead = 0.0
    score = 0.0

    for _ in range(iterations):
        state = GameState(rules=rules, rng=rng, deck=list(library))
        state.shuffle()
        state.deal_opening_hand()
        taken = 0
        while taken < policy.max_mulligans and not policy.should_keep(
            hand_features(state.hand, context)
        ):
            state.redraw_hand()
            taken += 1
        mulligans += 1 if taken else 0
        features = hand_features(state.hand, context)
        targets += int(features["target"] >= 1)
        draw_sources += int(features["draw_sources"] >= 1)
        good += int(quality.is_good(features))
        sellables += features["sellables"]
        effective += features["effective_sellables"]
        dead += features["dead_cards"]
        score += features["score"]

    assumptions = {"deck_size": deck.size, "policy": policy.name}
    return OpeningHandStats(
        policy=policy.name,
        iterations=iterations,
        mulligan_rate=proportion_result(mulligans, iterations, f"P(mulligan) [{policy.name}]", seed, assumptions),
        keep_rate=proportion_result(iterations - mulligans, iterations, f"P(keep) [{policy.name}]", seed, assumptions),
        target_in_opening=proportion_result(targets, iterations, "P(target in kept hand)", seed, assumptions),
        draw_source_in_opening=proportion_result(draw_sources, iterations, "P(draw source in kept hand)", seed, assumptions),
        good_hand_rate=proportion_result(good, iterations, "P(good hand)", seed, assumptions),
        average_sellables=sellables / iterations if iterations else 0.0,
        average_effective_sellables=effective / iterations if iterations else 0.0,
        average_dead_cards=dead / iterations if iterations else 0.0,
        average_score=score / iterations if iterations else 0.0,
    )


@dataclass
class PolicyComparisonRow:
    policy: str
    description: str
    mulligan_rate: float
    target_by_turn: dict[int, Result]
    sells_through: dict[int, Result]
    target_played: dict[int, Result]
    good_hand_rate: float
    average_sellables: float
    opening: OpeningHandStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "description": self.description,
            "mulligan_rate": self.mulligan_rate,
            "good_hand_rate": self.good_hand_rate,
            "average_sellables_after_mulligan": self.average_sellables,
            "target_seen_by_turn": {f"T{t}": r.to_dict() for t, r in self.target_by_turn.items()},
            "sells_through_turn": {f"T{t}": r.to_dict() for t, r in self.sells_through.items()},
            "target_played_by_turn": {f"T{t}": r.to_dict() for t, r in self.target_played.items()},
        }


def compare_policies(
    deck: Deck,
    policies: Sequence[MulliganPolicy],
    target_names: Sequence[str],
    profile: Optional[PlayabilityProfile] = None,
    rules: Optional[RuleConfig] = None,
    iterations: int = 20_000,
    opening_iterations: Optional[int] = None,
    seed: Optional[int] = 20770301,
    max_turn: int = 3,
    gig_distribution: Optional[GigDistribution] = None,
    board_proxy: Optional[BoardProxy] = None,
    quality: Optional[HandQualityRule] = None,
) -> list[PolicyComparisonRow]:
    """Run each policy through the simulator and report both axes."""
    rules = rules or RuleConfig()
    rows: list[PolicyComparisonRow] = []
    for policy in policies:
        opening = opening_hand_stats(
            deck, policy, target_names, profile, rules,
            opening_iterations or max(5_000, iterations // 2), seed, quality,
        )
        pilot = PilotPolicy(
            target_names=tuple(target_names), profile=profile, mulligan=policy
        )
        summary = simulate(
            deck, pilot, rules, iterations, seed, max_turn,
            gig_distribution, board_proxy, profile,
        )
        rows.append(
            PolicyComparisonRow(
                policy=policy.name,
                description=policy.description or policy.describe(),
                mulligan_rate=summary.mulligans / summary.iterations,
                target_by_turn=summary.curve("target_seen", "target seen"),
                sells_through=summary.curve("sells_through", "sold every turn through"),
                target_played=summary.curve("target_played", "target played by"),
                good_hand_rate=opening.good_hand_rate.value,
                average_sellables=opening.average_sellables,
                opening=opening,
            )
        )
    return rows


def render_comparison(rows: Sequence[PolicyComparisonRow], turn: int = 3) -> str:
    header = (
        f"{'Strategy':<24}{'Mull %':>8}{'Target T' + str(turn):>12}"
        f"{'Sell thru T' + str(turn):>15}{'Played T' + str(turn):>11}{'Good hand':>11}{'Avg sell':>10}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{row.policy[:23]:<24}{row.mulligan_rate:>7.1%}"
            f"{row.target_by_turn[turn].value:>12.1%}"
            f"{row.sells_through[turn].value:>15.1%}"
            f"{row.target_played[turn].value:>11.1%}"
            f"{row.good_hand_rate:>11.1%}"
            f"{row.average_sellables:>10.2f}"
        )
    lines.append("")
    lines.append("SIMULATED — Monte Carlo. Differences smaller than the 95% CI are noise.")
    return "\n".join(lines)
