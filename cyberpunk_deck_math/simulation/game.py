"""Monte Carlo game simulator.

Deterministic given a seed.  Every reported probability carries its sample
size, standard error and 95% confidence interval, so simulation noise is never
mistaken for a real difference between two builds.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from math import sqrt
from typing import Any, Optional

from ..config import RuleConfig
from ..methods import Method, Result
from ..models import Deck, PlayabilityProfile, normalize_name
from .board_proxy import BoardProxy
from .gigs import GigDistribution
from .legends import setup_legends
from .pilot import PilotPolicy
from .state import GameState

DEFAULT_ITERATIONS = 500_000
ITERATION_CHOICES = (10_000, 50_000, 100_000, 500_000, 1_000_000)


@dataclass
class TurnRecord:
    seen_target: bool = False
    target_in_hand: bool = False
    target_affordable: bool = False
    target_played: bool = False
    sold: bool = False
    consecutive_sells: bool = False
    resources: int = 0
    playable_in_hand: int = 0


@dataclass
class SimulationSummary:
    """Aggregated counters over all iterations."""

    iterations: int
    max_turn: int
    counts: dict[str, list[int]] = field(default_factory=dict)
    totals: dict[str, list[float]] = field(default_factory=dict)
    mulligans: int = 0
    draws_by_source: dict[str, int] = field(default_factory=dict)
    seed: Optional[int] = None
    assumptions: dict[str, Any] = field(default_factory=dict)

    def rate(self, key: str, turn: int, label: str = "") -> Result:
        successes = self.counts[key][turn - 1]
        return proportion_result(
            successes, self.iterations, label or f"{key} T{turn}", self.seed, self.assumptions
        )

    def average(self, key: str, turn: int, label: str = "") -> Result:
        total = self.totals[key][turn - 1]
        value = total / self.iterations if self.iterations else 0.0
        return Result(
            value=value,
            method=Method.SIMULATED,
            label=label or f"{key} T{turn}",
            sample_size=self.iterations,
            assumptions=self.assumptions,
        )

    def curve(self, key: str, label: str = "") -> dict[int, Result]:
        return {
            t: self.rate(key, t, f"{label or key} T{t}") for t in range(1, self.max_turn + 1)
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "seed": self.seed,
            "max_turn": self.max_turn,
            "mulligan_rate": self.mulligans / self.iterations if self.iterations else 0.0,
            "rates": {
                key: [c / self.iterations for c in values]
                for key, values in self.counts.items()
            },
            "averages": {
                key: [v / self.iterations for v in values]
                for key, values in self.totals.items()
            },
            "draws_by_source": {
                k: v / self.iterations for k, v in self.draws_by_source.items()
            },
            "assumptions": self.assumptions,
        }


def proportion_result(
    successes: int,
    n: int,
    label: str,
    seed: Optional[int] = None,
    assumptions: Optional[dict[str, Any]] = None,
) -> Result:
    """A simulated proportion with its standard error and 95% CI."""
    p = successes / n if n else 0.0
    se = sqrt(max(p * (1 - p), 0.0) / n) if n else 0.0
    return Result(
        value=p,
        method=Method.SIMULATED,
        label=label,
        sample_size=n,
        standard_error=se,
        ci95=(max(0.0, p - 1.96 * se), min(1.0, p + 1.96 * se)),
        assumptions=dict(assumptions or {}, seed=seed),
    )


TRACKED = (
    "target_seen",
    "target_in_hand",
    "target_affordable",
    "target_legal",
    "target_strategic",
    "target_played",
    "sold_this_turn",
    "sells_through",
    "legend_called",
)
AVERAGED = ("resources", "hand_size", "playable_in_hand", "sellables_in_hand", "street_cred")


def simulate(
    deck: Deck,
    policy: Optional[PilotPolicy] = None,
    rules: Optional[RuleConfig] = None,
    iterations: int = DEFAULT_ITERATIONS,
    seed: Optional[int] = 20770301,
    max_turn: int = 6,
    gig_distribution: Optional[GigDistribution] = None,
    board_proxy: Optional[BoardProxy] = None,
    profile: Optional[PlayabilityProfile] = None,
) -> SimulationSummary:
    """Run ``iterations`` games and aggregate the results."""
    rules = rules or RuleConfig()
    policy = policy or PilotPolicy(profile=profile)
    if policy.profile is None:
        policy.profile = profile
    gigs = gig_distribution or GigDistribution.uniform(6)
    proxy = board_proxy or BoardProxy()

    if deck.size == 0:
        raise ValueError("cannot simulate an empty deck")
    if rules.opening_hand_size + max_turn > deck.size:
        raise ValueError(
            f"deck of {deck.size} cards cannot support {max_turn} turns from a "
            f"{rules.opening_hand_size}-card opening hand"
        )

    summary = SimulationSummary(
        iterations=iterations,
        max_turn=max_turn,
        counts={key: [0] * max_turn for key in TRACKED},
        totals={key: [0.0] * max_turn for key in AVERAGED},
        seed=seed,
        assumptions={
            "deck_size": deck.size,
            "sellables": deck.sellable_count,
            "targets": list(policy.target_names),
            "mulligan_policy": policy.mulligan.name if policy.mulligan else "none",
            "playability_profile": policy.profile.name if policy.profile else "none",
            "board_proxy": proxy.name,
            "board_proxy_mode": proxy.mode,
            "gig_distribution": gigs.name,
            "rule_overrides": rules.overrides(),
        },
    )

    rng = random.Random(seed)
    target_keys = {normalize_name(n) for n in policy.target_names}
    library = list(deck.cards())
    legend_cards = list(deck.legends)

    for _ in range(iterations):
        state = GameState(rules=rules, rng=rng, deck=list(library))
        state.legends = setup_legends(legend_cards, rng)
        state.shuffle()
        state.deal_opening_hand()
        summary.mulligans += 1 if policy.decide_mulligan(state) else 0

        seen_target = any(c.key in target_keys for c in state.cards_seen)
        played_target = False
        sells_streak = True

        for turn in range(1, max_turn + 1):
            state.turn = turn
            state.ready_all()
            state.opponent_proxy = proxy.resolve(turn, rng)

            if turn > 1 or rules.draw_on_first_turn:
                state.draw(rules.natural_draws_per_turn, source="natural draw")
            state.add_gig(gigs.roll(rng))

            seen_target = seen_target or any(c.key in target_keys for c in state.hand)
            in_hand = any(c.key in target_keys for c in state.hand)

            sold = policy.take_sell(state, rules)
            policy.take_legend_action(state, rules)

            # Evaluate every copy in hand: any one of them being playable is
            # what matters, and the pilot gets a chance with each.
            copies_in_hand = [c for c in state.hand if c.key in target_keys]
            affordable = any(state.can_afford(c.cost or 0) for c in copies_in_hand)
            legal = False
            strategic = False
            for card in copies_in_hand:
                if not state.can_afford(card.cost or 0):
                    continue
                if policy.profile is None:
                    legal = strategic = True
                    break
                # Affordability is simulated exactly; the profile's legal curve
                # carries the requirements the simulator does not model.
                if rng.random() >= policy.profile.legal_playability(card, turn):
                    continue
                legal = True
                if rng.random() < policy.profile.strategic_playability(card, turn):
                    strategic = True
                    break

            before = set(state.plays_by_turn.get(turn, []))
            policy.take_plays(state, rules, rng)
            after = state.plays_by_turn.get(turn, [])
            played_now = any(
                normalize_name(name) in target_keys for name in after if name not in before
            )
            played_target = played_target or played_now

            index = turn - 1
            summary.counts["target_seen"][index] += int(seen_target)
            summary.counts["target_in_hand"][index] += int(in_hand)
            summary.counts["target_affordable"][index] += int(affordable)
            summary.counts["target_legal"][index] += int(legal)
            summary.counts["target_strategic"][index] += int(strategic)
            summary.counts["target_played"][index] += int(played_target)
            summary.counts["sold_this_turn"][index] += int(sold)
            sells_streak = sells_streak and sold
            summary.counts["sells_through"][index] += int(sells_streak)
            summary.counts["legend_called"][index] += int(
                any(l.called_this_turn for l in state.legends)
            )

            summary.totals["resources"][index] += state.available_resources
            summary.totals["hand_size"][index] += len(state.hand)
            summary.totals["street_cred"][index] += state.street_cred
            summary.totals["sellables_in_hand"][index] += sum(
                1 for c in state.hand if c.is_sellable
            )
            if policy.profile is not None:
                summary.totals["playable_in_hand"][index] += sum(
                    policy.profile.strategic_playability(c, turn) for c in state.hand
                )
            else:
                summary.totals["playable_in_hand"][index] += len(state.hand)

        for source, count in state.draws_by_source.items():
            summary.draws_by_source[source] = summary.draws_by_source.get(source, 0) + count

    return summary


def resource_threshold_rate(
    deck: Deck,
    threshold: int,
    turn: int,
    policy: Optional[PilotPolicy] = None,
    rules: Optional[RuleConfig] = None,
    iterations: int = 50_000,
    seed: Optional[int] = 20770301,
    gig_distribution: Optional[GigDistribution] = None,
    board_proxy: Optional[BoardProxy] = None,
) -> Result:
    """P(at least ``threshold`` usable resources on ``turn``), by simulation."""
    rules = rules or RuleConfig()
    policy = policy or PilotPolicy()
    gigs = gig_distribution or GigDistribution.uniform(6)
    proxy = board_proxy or BoardProxy()
    rng = random.Random(seed)
    library = list(deck.cards())
    successes = 0

    for _ in range(iterations):
        state = GameState(rules=rules, rng=rng, deck=list(library))
        state.legends = setup_legends(list(deck.legends), rng)
        state.shuffle()
        state.deal_opening_hand()
        policy.decide_mulligan(state)
        for t in range(1, turn + 1):
            state.turn = t
            state.ready_all()
            state.opponent_proxy = proxy.resolve(t, rng)
            if t > 1 or rules.draw_on_first_turn:
                state.draw(rules.natural_draws_per_turn, source="natural draw")
            state.add_gig(gigs.roll(rng))
            policy.take_sell(state, rules)
            policy.take_legend_action(state, rules)
        successes += int(state.available_resources >= threshold)

    return proportion_result(
        successes,
        iterations,
        f"P(>= {threshold} usable resources on T{turn})",
        seed,
        {"deck_size": deck.size, "sellables": deck.sellable_count},
    )
