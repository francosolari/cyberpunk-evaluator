"""Generic condition vocabulary and evaluation.

Conditions are dictionaries, evaluated against a context mapping supplied by
the simulator (or by a proxy model when the simulator does not track the
relevant board state).  A condition whose context value is unknown evaluates
to ``None`` — "cannot determine" — and callers must decide how to treat that
rather than silently assuming ``True``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

CONDITION_TYPES: tuple[str, ...] = (
    "turn",
    "street_cred",
    "street_cred_parity",
    "distinct_gigs",
    "gig_count",
    "resource_available",
    "friendly_unit_count",
    "enemy_unit_count",
    "card_type_in_play",
    "card_in_hand",
    "legend_face_up",
    "opponent_state_proxy",
)

OPERATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "in": lambda a, b: a in b,
    "contains": lambda a, b: b in (a or []),
}


def validate_condition(condition: Mapping[str, Any]) -> Mapping[str, Any]:
    ctype = condition.get("type")
    if ctype not in CONDITION_TYPES:
        raise ValueError(f"unknown condition type {ctype!r}")
    op = condition.get("operator", "==")
    if op not in OPERATORS:
        raise ValueError(f"unknown operator {op!r}")
    if "value" not in condition:
        raise ValueError(f"condition {ctype!r} requires a 'value'")
    return condition


def _context_value(condition: Mapping[str, Any], context: Mapping[str, Any]) -> Any:
    ctype = condition["type"]
    if ctype == "street_cred_parity":
        cred = context.get("street_cred")
        if cred is None:
            return None
        return "even" if cred % 2 == 0 else "odd"
    if ctype == "card_type_in_play":
        return context.get("card_types_in_play")
    if ctype == "card_in_hand":
        return context.get("hand_names")
    if ctype == "opponent_state_proxy":
        proxies = context.get("opponent_state_proxy") or {}
        return proxies.get(condition.get("key", condition.get("value")))
    return context.get(ctype)


def evaluate_condition(
    condition: Mapping[str, Any], context: Mapping[str, Any]
) -> Optional[bool]:
    """Evaluate one condition.  ``None`` means "context does not know"."""
    validate_condition(condition)
    ctype = condition["type"]
    actual = _context_value(condition, context)
    if actual is None:
        return None
    op = OPERATORS[condition.get("operator", "==")]
    expected = condition["value"]
    if ctype in ("card_type_in_play", "card_in_hand") and condition.get(
        "operator"
    ) in (None, "=="):
        op = OPERATORS["contains"]
    if ctype == "opponent_state_proxy":
        # A proxy stores a probability; the simulator resolves it upstream and
        # places a bool in the context.  A raw float here means unresolved.
        if isinstance(actual, float):
            return None
        return bool(actual)
    try:
        return bool(op(actual, expected))
    except TypeError:
        return None


def evaluate_all(
    conditions: list[Mapping[str, Any]],
    context: Mapping[str, Any],
    unknown_is: Optional[bool] = None,
) -> Optional[bool]:
    """AND-combine conditions.

    ``unknown_is`` controls how an undeterminable condition is treated.  The
    default (``None``) propagates the uncertainty to the caller.
    """
    result = True
    for condition in conditions or []:
        outcome = evaluate_condition(condition, context)
        if outcome is None:
            if unknown_is is None:
                return None
            outcome = unknown_is
        result = result and outcome
        if not result:
            return False
    return result
