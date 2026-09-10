"""Optional Claude-backed assistance.

Two workflows use an LLM: proposing structured effect metadata from official
card text (:mod:`cyberpunk_deck_math.effects.interpreter`) and proposing
playability estimates (:mod:`cyberpunk_deck_math.analytics.playability`).

Both are strictly advisory.  Output is stored with
``interpretation_status = "llm_proposed"`` / ``HEURISTIC — LLM Estimate`` and
never becomes authoritative until a human verifies it.  The application is
fully usable with no API key: every LLM entry point has a documented manual
alternative.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

MODEL = "claude-opus-5"


class LLMUnavailable(RuntimeError):
    """Raised when an LLM-assisted feature is requested without credentials."""


@dataclass
class LLMResponse:
    data: dict[str, Any]
    raw_text: str
    model: str
    refused: bool = False
    refusal_reason: Optional[str] = None


def available() -> bool:
    """True when the SDK is installed and some credential source exists."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    # The SDK also resolves OAuth profiles written by `ant auth login`.
    profile_dir = os.path.expanduser("~/.config/anthropic")
    return os.path.isdir(profile_dir)


def structured_call(
    system: str,
    prompt: str,
    schema: Mapping[str, Any],
    max_tokens: int = 4000,
    model: str = MODEL,
) -> LLMResponse:
    """One structured-output request to Claude.

    Server-side refusal fallback is enabled so a declined request routes to
    another model rather than failing the workflow.
    """
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise LLMUnavailable(
            "the 'anthropic' package is not installed; install it with "
            "`pip install anthropic`, or enter the values by hand"
        ) from exc

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        thinking={"type": "adaptive"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": dict(schema)}},
    )

    if getattr(response, "stop_reason", None) == "refusal":
        details = getattr(response, "stop_details", None)
        return LLMResponse(
            data={},
            raw_text="",
            model=model,
            refused=True,
            refusal_reason=getattr(details, "category", None),
        )

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model did not return JSON: {text[:200]!r}") from exc
    return LLMResponse(data=data, raw_text=text, model=model)
