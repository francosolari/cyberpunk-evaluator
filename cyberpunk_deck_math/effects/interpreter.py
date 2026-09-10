"""Card-text -> structured-effect interpretation workflow.

Three modes, matching the three ways a rule can be established:

MODE A — HUMAN ENTERED   :func:`set_human_interpretation`
MODE B — LLM ASSISTED    :func:`propose_interpretation`
MODE C — HUMAN VERIFIED  :func:`verify_interpretation`

The official card text is never overwritten and is always displayed beside
the structured interpretation.  An LLM proposal can never silently become
authoritative: it lands as ``llm_proposed`` and stays there until a human
marks it ``human_verified``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from ..llm import LLMUnavailable, structured_call
from ..models import Card
from .conditions import CONDITION_TYPES
from .generic import EFFECTS, Effect
from .triggers import TRIGGERS

EFFECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "effects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "trigger": {"type": "string", "enum": list(TRIGGERS)},
                    "effect": {"type": "string", "enum": list(EFFECTS)},
                    "amount": {"type": "integer"},
                    "conditions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": list(CONDITION_TYPES)},
                                "operator": {
                                    "type": "string",
                                    "enum": ["==", "!=", ">", ">=", "<", "<=", "in", "contains"],
                                },
                                "value": {
                                    "anyOf": [
                                        {"type": "string"},
                                        {"type": "number"},
                                        {"type": "boolean"},
                                    ]
                                },
                            },
                            "required": ["type", "value"],
                            "additionalProperties": False,
                        },
                    },
                    "notes": {"type": "string"},
                },
                "required": ["trigger", "effect", "amount", "conditions", "notes"],
                "additionalProperties": False,
            },
        },
        "unrepresentable": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Parts of the card text this vocabulary cannot express.",
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "rationale": {"type": "string"},
    },
    "required": ["effects", "unrepresentable", "confidence", "rationale"],
    "additionalProperties": False,
}

SYSTEM = """You convert trading-card rules text into a fixed structured vocabulary.

Rules:
- Only use the triggers, effects and condition types provided in the schema.
- Represent exactly what the card text says. Do not infer effects that are not written.
- If part of the text cannot be represented, list it verbatim under
  "unrepresentable" rather than approximating it.
- If the text is ambiguous, say so in "rationale" and set confidence to "low".
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_metadata(metadata: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate proposed metadata by round-tripping it through :class:`Effect`."""
    return [Effect.from_dict(entry).to_dict() for entry in metadata]


def set_human_interpretation(
    card: Card, metadata: Iterable[Mapping[str, Any]], notes: str = ""
) -> Card:
    """MODE A — a human enters structured rules directly (authoritative)."""
    card.effect_metadata = validate_metadata(metadata)
    card.interpretation_status = "human_verified"
    card.interpretation_notes = notes or f"Human-entered {_now()}"
    return card


def propose_interpretation(card: Card, model: Optional[str] = None) -> dict[str, Any]:
    """MODE B — ask Claude for structured metadata.  Advisory only.

    Returns the raw proposal; the caller decides whether to attach it.  Raises
    :class:`LLMUnavailable` when no credentials are configured — callers should
    fall back to MODE A.
    """
    if not card.rules_text:
        raise ValueError(
            f"{card.name} has no official rules text cached; run "
            "`cli.py update-cards` first or enter the interpretation by hand"
        )
    prompt = json.dumps(
        {
            "name": card.name,
            "type": card.type,
            "subtype": card.subtype,
            "cost": card.cost,
            "ram": card.ram,
            "sellable": card.sellable,
            "rules_text": card.rules_text,
        },
        indent=2,
        ensure_ascii=False,
    )
    kwargs = {"model": model} if model else {}
    response = structured_call(SYSTEM, prompt, EFFECT_SCHEMA, **kwargs)
    if response.refused:
        raise LLMUnavailable(
            f"the model declined this request ({response.refusal_reason}); "
            "enter the interpretation by hand"
        )
    return response.data


def attach_proposal(card: Card, proposal: Mapping[str, Any]) -> Card:
    """Attach an LLM proposal as ``llm_proposed`` — explicitly not authoritative."""
    card.effect_metadata = validate_metadata(proposal.get("effects", []))
    card.interpretation_status = "llm_proposed"
    notes = [f"LLM proposal {_now()}", f"confidence={proposal.get('confidence')}"]
    if proposal.get("rationale"):
        notes.append(f"rationale={proposal['rationale']}")
    if proposal.get("unrepresentable"):
        notes.append("unrepresentable=" + "; ".join(proposal["unrepresentable"]))
    card.interpretation_notes = " | ".join(notes)
    return card


def verify_interpretation(card: Card, verifier: str = "human", notes: str = "") -> Card:
    """MODE C — a human approves the current interpretation."""
    if not card.effect_metadata:
        raise ValueError(f"{card.name} has no interpretation to verify")
    card.interpretation_status = "human_verified"
    existing = card.interpretation_notes or ""
    card.interpretation_notes = (
        f"{existing} | verified by {verifier} {_now()}"
        + (f" | {notes}" if notes else "")
    ).strip(" |")
    return card


def interpretation_report(cards: Iterable[Card]) -> dict[str, list[str]]:
    """Group cards by interpretation status, for the CARD RULES tab."""
    report: dict[str, list[str]] = {"raw": [], "llm_proposed": [], "human_verified": []}
    for card in cards:
        report[card.interpretation_status].append(card.name)
    return report
