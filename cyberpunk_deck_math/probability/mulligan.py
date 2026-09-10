"""Mulligan rule engine.

A mulligan policy is a boolean expression over *hand features*, optionally
combined with a numeric hand score.  Policies are data (JSON), so the UI can
build them from dropdowns and users can save reusable profiles without editing
Python.

Nothing here assumes "mulligan if no target card": that is merely one policy
among many, and the analytics module exists to show its cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from ..models import Card, PlayabilityProfile, normalize_name

# --------------------------------------------------------------------- features

FEATURES: tuple[str, ...] = (
    "hand_size",
    "sellables",
    "effective_sellables",
    "target",
    "draw_sources",
    "early_draw_sources",
    "early_playables",
    "cards_cost_4_plus",
    "average_cost",
    "sellable_pct",
    "dead_cards",
    "score",
    "distinct_names",
)


@dataclass
class HandContext:
    """Everything hand-feature extraction needs beyond the cards themselves."""

    target_names: tuple[str, ...] = ()
    draw_tag: str = "draw"
    early_turn: int = 2
    expensive_cost: int = 4
    profile: Optional[PlayabilityProfile] = None
    score_config: Optional["ScoreConfig"] = None

    def is_target(self, card: Card) -> bool:
        keys = {normalize_name(n) for n in self.target_names}
        return card.key in keys

    def is_draw_source(self, card: Card) -> bool:
        if card.has_tag(self.draw_tag):
            return True
        return any(e.get("effect") == "draw" for e in card.effect_metadata or [])

    def is_early_draw_source(self, card: Card) -> bool:
        if not self.is_draw_source(card):
            return False
        if self.profile is None:
            return True
        return self.profile.strategic_playability(card, self.early_turn) > 0.0

    def is_early_playable(self, card: Card) -> bool:
        if self.profile is None:
            return card.cost is not None and card.cost <= self.early_turn
        return self.profile.strategic_playability(card, self.early_turn) >= 0.5


def hand_features(hand: Sequence[Card], context: HandContext) -> dict[str, float]:
    """Compute every feature a mulligan rule may reference."""
    size = len(hand)
    sellables = sum(1 for c in hand if c.is_sellable)
    effective = (
        sum(context.profile.willingness(c, 1) for c in hand)
        if context.profile
        else float(sellables)
    )
    costs = [c.cost for c in hand if c.cost is not None]
    features = {
        "hand_size": float(size),
        "sellables": float(sellables),
        "effective_sellables": float(effective),
        "target": float(sum(1 for c in hand if context.is_target(c))),
        "draw_sources": float(sum(1 for c in hand if context.is_draw_source(c))),
        "early_draw_sources": float(
            sum(1 for c in hand if context.is_early_draw_source(c))
        ),
        "early_playables": float(sum(1 for c in hand if context.is_early_playable(c))),
        "cards_cost_4_plus": float(
            sum(1 for c in hand if c.cost is not None and c.cost >= context.expensive_cost)
        ),
        "average_cost": (sum(costs) / len(costs)) if costs else 0.0,
        "sellable_pct": (sellables / size) if size else 0.0,
        "dead_cards": float(
            sum(
                1
                for c in hand
                if context.profile is not None
                and context.profile.strategic_playability(c, context.early_turn) <= 0.0
            )
        ),
        "distinct_names": float(len({c.key for c in hand})),
    }
    features["score"] = (
        context.score_config.score(hand, features, context)
        if context.score_config
        else 0.0
    )
    return features


# ------------------------------------------------------------------ expressions

OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}


class Node:
    """Base class for mulligan rule expression nodes."""

    def evaluate(self, features: Mapping[str, float]) -> bool:  # pragma: no cover
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> str:  # pragma: no cover
        raise NotImplementedError


@dataclass
class Condition(Node):
    feature: str
    operator: str = ">="
    value: float = 1.0

    def __post_init__(self) -> None:
        if self.feature not in FEATURES:
            raise ValueError(f"unknown hand feature {self.feature!r}; expected {FEATURES}")
        if self.operator not in OPERATORS:
            raise ValueError(f"unknown operator {self.operator!r}")

    def evaluate(self, features: Mapping[str, float]) -> bool:
        return OPERATORS[self.operator](float(features[self.feature]), float(self.value))

    def to_dict(self) -> dict[str, Any]:
        return {"feature": self.feature, "operator": self.operator, "value": self.value}

    def describe(self) -> str:
        return f"{self.feature} {self.operator} {self.value:g}"


@dataclass
class And(Node):
    children: list[Node] = field(default_factory=list)

    def evaluate(self, features: Mapping[str, float]) -> bool:
        return all(child.evaluate(features) for child in self.children)

    def to_dict(self) -> dict[str, Any]:
        return {"all": [c.to_dict() for c in self.children]}

    def describe(self) -> str:
        return "(" + " AND ".join(c.describe() for c in self.children) + ")"


@dataclass
class Or(Node):
    children: list[Node] = field(default_factory=list)

    def evaluate(self, features: Mapping[str, float]) -> bool:
        return any(child.evaluate(features) for child in self.children)

    def to_dict(self) -> dict[str, Any]:
        return {"any": [c.to_dict() for c in self.children]}

    def describe(self) -> str:
        return "(" + " OR ".join(c.describe() for c in self.children) + ")"


@dataclass
class Not(Node):
    child: Node

    def evaluate(self, features: Mapping[str, float]) -> bool:
        return not self.child.evaluate(features)

    def to_dict(self) -> dict[str, Any]:
        return {"not": self.child.to_dict()}

    def describe(self) -> str:
        return f"NOT {self.child.describe()}"


@dataclass
class Always(Node):
    value: bool = True

    def evaluate(self, features: Mapping[str, float]) -> bool:
        return self.value

    def to_dict(self) -> dict[str, Any]:
        return {"always": self.value}

    def describe(self) -> str:
        return "ALWAYS KEEP" if self.value else "ALWAYS MULLIGAN"


def parse_node(data: Mapping[str, Any]) -> Node:
    """Build an expression tree from nested dictionaries."""
    if "all" in data:
        return And([parse_node(c) for c in data["all"]])
    if "any" in data:
        return Or([parse_node(c) for c in data["any"]])
    if "not" in data:
        return Not(parse_node(data["not"]))
    if "always" in data:
        return Always(bool(data["always"]))
    if "feature" in data:
        return Condition(
            feature=data["feature"],
            operator=data.get("operator", ">="),
            value=float(data["value"]),
        )
    raise ValueError(f"cannot parse mulligan rule node: {data!r}")


# ----------------------------------------------------------------------- scoring


@dataclass
class ScoreConfig:
    """Numeric opening-hand scoring with interaction bonuses."""

    card_scores: dict[str, float] = field(default_factory=dict)
    tag_scores: dict[str, float] = field(default_factory=dict)
    interactions: list[dict[str, Any]] = field(default_factory=list)
    sellable_score: float = 0.0

    def score(
        self,
        hand: Sequence[Card],
        features: Mapping[str, float],
        context: "HandContext",
    ) -> float:
        total = 0.0
        for card in hand:
            total += self.card_scores.get(card.key, 0.0)
            for tag, points in self.tag_scores.items():
                if card.has_tag(tag):
                    total += points
            if card.is_sellable:
                total += self.sellable_score
        for rule in self.interactions:
            node = parse_node(rule["when"])
            # Interaction rules see the features computed so far; ``score``
            # itself is excluded to keep evaluation acyclic.
            partial = {k: v for k, v in features.items() if k != "score"}
            partial["score"] = 0.0
            if node.evaluate(partial):
                total += float(rule["points"])
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_scores": dict(self.card_scores),
            "tag_scores": dict(self.tag_scores),
            "sellable_score": self.sellable_score,
            "interactions": list(self.interactions),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScoreConfig":
        return cls(
            card_scores={normalize_name(k): float(v) for k, v in (data.get("card_scores") or {}).items()},
            tag_scores={k: float(v) for k, v in (data.get("tag_scores") or {}).items()},
            interactions=list(data.get("interactions") or []),
            sellable_score=float(data.get("sellable_score", 0.0)),
        )


# ---------------------------------------------------------------------- policies


@dataclass
class MulliganPolicy:
    """A saved, reusable mulligan profile.

    Exactly one of ``keep`` / ``mulligan`` drives the decision; the other is
    derived.  ``max_mulligans`` bounds how many times a hand is redrawn (the
    final hand is always kept, matching the game rules).
    """

    name: str
    keep: Optional[Node] = None
    mulligan: Optional[Node] = None
    description: str = ""
    score_config: Optional[ScoreConfig] = None
    max_mulligans: int = 1

    def __post_init__(self) -> None:
        if self.keep is None and self.mulligan is None:
            self.keep = Always(True)

    def should_keep(self, features: Mapping[str, float]) -> bool:
        if self.keep is not None:
            return self.keep.evaluate(features)
        assert self.mulligan is not None
        return not self.mulligan.evaluate(features)

    def decide(self, hand: Sequence[Card], context: HandContext) -> bool:
        ctx = context
        if self.score_config is not None and context.score_config is None:
            ctx = HandContext(
                target_names=context.target_names,
                draw_tag=context.draw_tag,
                early_turn=context.early_turn,
                expensive_cost=context.expensive_cost,
                profile=context.profile,
                score_config=self.score_config,
            )
        return self.should_keep(hand_features(hand, ctx))

    def describe(self) -> str:
        if self.keep is not None:
            return f"KEEP IF {self.keep.describe()}"
        assert self.mulligan is not None
        return f"MULLIGAN IF {self.mulligan.describe()}"

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "max_mulligans": self.max_mulligans,
        }
        if self.keep is not None:
            data["keep"] = self.keep.to_dict()
        if self.mulligan is not None:
            data["mulligan"] = self.mulligan.to_dict()
        if self.score_config is not None:
            data["score"] = self.score_config.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MulliganPolicy":
        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            keep=parse_node(data["keep"]) if "keep" in data else None,
            mulligan=parse_node(data["mulligan"]) if "mulligan" in data else None,
            score_config=ScoreConfig.from_dict(data["score"]) if "score" in data else None,
            max_mulligans=int(data.get("max_mulligans", 1)),
        )


def builtin_policies() -> dict[str, MulliganPolicy]:
    """Policies always available, even with no profile files on disk."""
    defs: list[Mapping[str, Any]] = [
        {
            "name": "No Mulligan",
            "description": "Keep every opening hand. The baseline.",
            "keep": {"always": True},
        },
        {
            "name": "Target Only",
            "description": "Hard mulligan for the target card.",
            "keep": {"feature": "target", "operator": ">=", "value": 1},
        },
        {
            "name": "Target or Draw",
            "description": "Keep on the target card or an early draw source.",
            "keep": {
                "any": [
                    {"feature": "target", "operator": ">=", "value": 1},
                    {"feature": "early_draw_sources", "operator": ">=", "value": 1},
                ]
            },
        },
        {
            "name": "2+ Sellables",
            "description": "Resource-first: keep any hand with two sellables.",
            "keep": {"feature": "sellables", "operator": ">=", "value": 2},
        },
        {
            "name": "Sell Stability",
            "description": "Keep only hands with three sellables.",
            "keep": {"feature": "sellables", "operator": ">=", "value": 3},
        },
        {
            "name": "Balanced",
            "description": "Two sellables plus a target, a draw source, or two early plays.",
            "keep": {
                "all": [
                    {"feature": "sellables", "operator": ">=", "value": 2},
                    {
                        "any": [
                            {"feature": "target", "operator": ">=", "value": 1},
                            {"feature": "early_draw_sources", "operator": ">=", "value": 1},
                            {"feature": "early_playables", "operator": ">=", "value": 2},
                        ]
                    },
                ]
            },
        },
        {
            "name": "Draw Engine Priority",
            "description": "Mulligan hands with neither a draw source nor the target.",
            "mulligan": {
                "all": [
                    {"feature": "draw_sources", "operator": "==", "value": 0},
                    {"feature": "target", "operator": "==", "value": 0},
                ]
            },
        },
        {
            "name": "Low Curve",
            "description": "Mulligan hands clogged with expensive cards.",
            "mulligan": {"feature": "cards_cost_4_plus", "operator": ">=", "value": 3},
        },
        {
            "name": "No Early Play",
            "description": "Mulligan hands with nothing playable early.",
            "mulligan": {"feature": "early_playables", "operator": "==", "value": 0},
        },
    ]
    return {d["name"]: MulliganPolicy.from_dict(d) for d in defs}


def score_policy(
    name: str,
    threshold: float,
    score_config: ScoreConfig,
    description: str = "",
) -> MulliganPolicy:
    """A policy that keeps when the numeric hand score meets ``threshold``."""
    return MulliganPolicy(
        name=name,
        description=description or f"Keep when hand score >= {threshold:g}.",
        keep=Condition("score", ">=", threshold),
        score_config=score_config,
    )


def load_policies(paths: Iterable[Any]) -> dict[str, MulliganPolicy]:
    """Load saved policy JSON files, merged over the built-ins."""
    import json
    from pathlib import Path

    policies = builtin_policies()
    for path in paths:
        p = Path(path)
        if not p.exists():
            continue
        for file in sorted(p.glob("*.json")) if p.is_dir() else [p]:
            data = json.loads(file.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                policy = MulliganPolicy.from_dict(entry)
                policies[policy.name] = policy
    return policies
