"""Configurable analytics warnings.

These are heuristics about deckbuilding, not rules of the game, and every
threshold is editable.  The wording always names the configured threshold so
a reader can tell what would have to change for the warning to disappear.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..config import AnalysisConfig
from ..methods import Method
from ..models import Deck, PlayabilityProfile
from . import dead_cards, opportunity_density, sell_density

INFO = "info"
WARNING = "warning"


@dataclass
class Axiom:
    level: str
    message: str
    source: str = Method.PLAYTESTING_HEURISTIC.value
    threshold: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "message": self.message,
            "source": self.source,
            "threshold": self.threshold,
        }


def evaluate_axioms(
    deck: Deck,
    profile: Optional[PlayabilityProfile] = None,
    config: Optional[AnalysisConfig] = None,
) -> list[Axiom]:
    config = config or AnalysisConfig()
    settings = config.sellable
    status = sell_density.sellable_status(deck, settings)
    out: list[Axiom] = []

    if status.status == sell_density.BELOW_MINIMUM:
        out.append(
            Axiom(
                WARNING,
                f"Your deck is {status.actual_pct:.1%} sellable, below the configured "
                f"{settings.minimum_pct:.1%} minimum. You need "
                f"{status.cards_to_minimum} additional sellable card(s) to reach it, "
                f"and {status.cards_to_target} to reach the "
                f"{settings.target_pct:.1%} target.",
                threshold=settings.minimum_pct,
            )
        )
    elif status.status == sell_density.BELOW_TARGET:
        out.append(
            Axiom(
                INFO,
                f"Your deck is {status.actual_pct:.1%} sellable: above the "
                f"{settings.minimum_pct:.1%} minimum but below the "
                f"{settings.target_pct:.1%} target. "
                f"{status.cards_to_target} more sellable(s) would reach the target.",
                threshold=settings.target_pct,
            )
        )
    elif status.status == sell_density.ABOVE_TARGET_RANGE:
        out.append(
            Axiom(
                WARNING,
                f"Your deck is {status.actual_pct:.1%} sellable, above the configured "
                f"{settings.target_range[0]:.1%}–{settings.target_range[1]:.1%} "
                "preferred range. Check whether too many strategically valuable "
                "non-sellable effects have been cut.",
                threshold=settings.target_range[1],
            )
        )
    else:
        out.append(
            Axiom(
                INFO,
                f"Your deck is {status.actual_pct:.1%} sellable, inside the configured "
                f"{settings.target_range[0]:.1%}–{settings.target_range[1]:.1%} range.",
                threshold=settings.target_pct,
            )
        )

    if profile is not None:
        cutoff = config.warning_thresholds["low_playability_cutoff"]
        share = dead_cards.low_playability_share(deck, profile, 3, cutoff)
        if share >= config.warning_thresholds["low_playability_share_turn3"]:
            out.append(
                Axiom(
                    WARNING,
                    f"{share:.1%} of the deck has under {cutoff:.0%} strategic "
                    "playability by turn 3.",
                    source=profile.source,
                    threshold=config.warning_thresholds["low_playability_share_turn3"],
                )
            )
        burden = dead_cards.dead_card_burden(deck, profile, 3).total
        if burden >= config.warning_thresholds["dead_card_burden_turn3"]:
            out.append(
                Axiom(
                    WARNING,
                    f"Turn-3 dead-card burden is {burden:.1%}, at or above the "
                    f"configured {config.warning_thresholds['dead_card_burden_turn3']:.0%} "
                    "threshold.",
                    source=profile.source,
                    threshold=config.warning_thresholds["dead_card_burden_turn3"],
                )
            )
        density = opportunity_density.opportunity_density(deck, profile, 3).value
        if density < config.warning_thresholds["min_action_density_turn3"]:
            out.append(
                Axiom(
                    WARNING,
                    f"Turn-3 action density is {density:.1%}, below the configured "
                    f"{config.warning_thresholds['min_action_density_turn3']:.0%} floor.",
                    source=profile.source,
                    threshold=config.warning_thresholds["min_action_density_turn3"],
                )
            )

    placeholders = {e.card.name for e in deck.main if e.card.data_provenance != "official"}
    if placeholders:
        out.append(
            Axiom(
                WARNING,
                f"{len(placeholders)} card(s) in this deck come from a non-official "
                "data source (placeholder or manual entry). Run "
                "`python cli.py update-cards` to analyse against the official "
                "Beta card database.",
                source="data provenance",
            )
        )

    unverified = [
        e.card.name
        for e in deck.main
        if e.card.effect_metadata and e.card.interpretation_status != "human_verified"
    ]
    if unverified:
        out.append(
            Axiom(
                INFO,
                f"{len(unverified)} card interpretation(s) are not human-verified: "
                + ", ".join(sorted(unverified)[:5])
                + ("..." if len(unverified) > 5 else ""),
                source="interpretation status",
            )
        )
    return out
