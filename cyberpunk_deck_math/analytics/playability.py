"""Playability profiles: loading, LLM-assisted estimation, human feedback.

Playability is per strategy, not per card: the same card is a different card
in a different deck.  Profiles therefore live under ``profiles/playability/``
keyed by archetype, and every value carries the method that produced it —
human estimate, LLM estimate, or observed simulation frequency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from ..config import PROFILES_DIR
from ..llm import LLMUnavailable, structured_call
from ..methods import Method
from ..models import Card, Deck, PlayabilityProfile, normalize_name

PLAYABILITY_DIR = PROFILES_DIR / "playability"

SOURCE_HUMAN = Method.HEURISTIC_HUMAN.value
SOURCE_LLM = Method.HEURISTIC_LLM.value
SOURCE_SIMULATED = Method.SIMULATED.value


def load_profile(name_or_path: str | Path) -> PlayabilityProfile:
    path = Path(name_or_path)
    if not path.exists():
        path = PLAYABILITY_DIR / f"{name_or_path}.json"
    if not path.exists():
        raise FileNotFoundError(f"no playability profile at {name_or_path}")
    return PlayabilityProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_profile(profile: PlayabilityProfile, path: Optional[str | Path] = None) -> Path:
    target = Path(path) if path else PLAYABILITY_DIR / f"{profile.name}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(profile.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return target


def list_profiles() -> list[str]:
    if not PLAYABILITY_DIR.exists():
        return []
    return sorted(p.stem for p in PLAYABILITY_DIR.glob("*.json"))


def default_profile(deck: Optional[Deck] = None, name: str = "default") -> PlayabilityProfile:
    """A neutral profile: cost-gated legality, no strategic discount.

    Explicitly a starting point, not a claim: legal playability assumes a card
    costing ``c`` becomes castable around turn ``c``.  Override per deck.
    """
    profile = PlayabilityProfile(
        name=name,
        description=(
            "Cost-gated default. Legal playability assumes roughly one resource "
            "per turn; strategic playability is assumed equal to legal until a "
            "human or simulation says otherwise."
        ),
        source=SOURCE_HUMAN,
    )
    if deck is None:
        return profile
    for entry in deck.main:
        card = entry.card
        if card.cost is None:
            continue
        legal: dict[int, float] = {}
        for turn in range(1, 7):
            if turn < card.cost:
                legal[turn] = 0.0
            elif turn == card.cost:
                legal[turn] = 0.6
            else:
                legal[turn] = 1.0
        profile.legal[card.key] = legal
        profile.strategic[card.key] = dict(legal)
        profile.confidence[card.key] = "low"
        profile.rationale[card.key] = "Cost-gated default; not playtested."
    return profile


def set_estimate(
    profile: PlayabilityProfile,
    card: Card | str,
    table: Mapping[int, float],
    kind: str = "strategic",
    confidence: str = "",
    rationale: str = "",
    source: Optional[str] = None,
) -> PlayabilityProfile:
    """Record a human, LLM or simulation-derived estimate."""
    key = card.key if isinstance(card, Card) else normalize_name(card)
    target = {
        "strategic": profile.strategic,
        "legal": profile.legal,
        "sell_willingness": profile.sell_willingness,
    }[kind]
    target[key] = {int(t): float(v) for t, v in table.items()}
    if confidence:
        profile.confidence[key] = confidence
    if rationale:
        profile.rationale[key] = rationale
    if source:
        profile.source = source
    profile.invalidate()
    return profile


# ------------------------------------------------------------------- LLM assist

ESTIMATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "legal": {
            "type": "object",
            "properties": {str(t): {"type": "number"} for t in range(1, 7)},
            "required": [str(t) for t in range(1, 7)],
            "additionalProperties": False,
        },
        "strategic": {
            "type": "object",
            "properties": {str(t): {"type": "number"} for t in range(1, 7)},
            "required": [str(t) for t in range(1, 7)],
            "additionalProperties": False,
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "rationale": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["legal", "strategic", "confidence", "rationale", "assumptions"],
    "additionalProperties": False,
}

ESTIMATE_SYSTEM = """You estimate how playable a trading-card-game card is by turn.

Return two probability curves for turns 1-6, each value in [0, 1]:
- "legal": given the card is in hand on that turn, the fraction of realistic
  game states in which playing it is LEGAL (cost and requirements satisfied).
- "strategic": the fraction in which playing it is also the RIGHT play.
  strategic <= legal on every turn.

Be conservative. State every assumption you relied on. If the card text is
missing or ambiguous, set confidence to "low" and say why.
"""


@dataclass
class EstimateProposal:
    card_name: str
    legal: dict[int, float]
    strategic: dict[int, float]
    confidence: str
    rationale: str
    assumptions: list[str]
    method: str = SOURCE_LLM

    def to_dict(self) -> dict[str, Any]:
        return {
            "card": self.card_name,
            "legal": {str(k): v for k, v in self.legal.items()},
            "strategic": {str(k): v for k, v in self.strategic.items()},
            "confidence": self.confidence,
            "rationale": self.rationale,
            "assumptions": self.assumptions,
            "method": self.method,
        }


def propose_playability(
    card: Card,
    deck: Deck,
    strategy: str = "",
    resources_by_turn: Optional[Mapping[int, float]] = None,
    board_state_notes: str = "",
    model: Optional[str] = None,
) -> EstimateProposal:
    """MODE B — ask Claude for playability curves.  Labelled HEURISTIC — LLM ESTIMATE."""
    payload = {
        "card": {
            "name": card.name,
            "type": card.type,
            "cost": card.cost,
            "ram": card.ram,
            "sellable": card.sellable,
            "rules_text": card.rules_text,
            "tags": card.tags,
            "data_provenance": card.data_provenance,
        },
        "deck": {
            "name": deck.name,
            "size": deck.size,
            "sellable_pct": round(deck.sellable_pct, 4),
            "composition": [
                {"name": e.card.name, "copies": e.copies, "cost": e.card.cost}
                for e in deck.main
            ],
            "legends": [c.name for c in deck.legends],
        },
        "strategy": strategy,
        "typical_resources_by_turn": dict(resources_by_turn or {}),
        "board_state_notes": board_state_notes,
    }
    kwargs = {"model": model} if model else {}
    response = structured_call(
        ESTIMATE_SYSTEM, json.dumps(payload, indent=2, ensure_ascii=False),
        ESTIMATE_SCHEMA, **kwargs
    )
    if response.refused:
        raise LLMUnavailable(
            f"the model declined this request ({response.refusal_reason}); "
            "enter the estimate by hand"
        )
    data = response.data
    return EstimateProposal(
        card_name=card.name,
        legal={int(k): float(v) for k, v in data["legal"].items()},
        strategic={int(k): float(v) for k, v in data["strategic"].items()},
        confidence=data["confidence"],
        rationale=data["rationale"],
        assumptions=list(data["assumptions"]),
    )


def apply_proposal(
    profile: PlayabilityProfile, proposal: EstimateProposal
) -> PlayabilityProfile:
    set_estimate(profile, proposal.card_name, proposal.legal, "legal",
                 proposal.confidence, proposal.rationale)
    set_estimate(profile, proposal.card_name, proposal.strategic, "strategic",
                 proposal.confidence, proposal.rationale)
    profile.source = SOURCE_LLM
    return profile


def apply_simulation_feedback(
    profile: PlayabilityProfile,
    card: Card | str,
    observed: Mapping[int, float],
    kind: str = "strategic",
) -> PlayabilityProfile:
    """MODE C — replace an estimate with an observed simulation frequency."""
    return set_estimate(
        profile, card, observed, kind,
        confidence="observed",
        rationale="Frequency observed in Monte Carlo simulation.",
    )


def record_playtest_feedback(
    profile: PlayabilityProfile,
    card: Card | str,
    turn: int,
    value: float,
    kind: str = "strategic",
    note: str = "",
) -> PlayabilityProfile:
    """Human feedback loop: update a single turn after real playtesting."""
    key = card.key if isinstance(card, Card) else normalize_name(card)
    table = dict(
        {"strategic": profile.strategic, "legal": profile.legal,
         "sell_willingness": profile.sell_willingness}[kind].get(key, {})
    )
    table[int(turn)] = float(value)
    return set_estimate(
        profile, card, table, kind,
        confidence="playtested",
        rationale=note or f"Updated from playtesting on T{turn}.",
    )
