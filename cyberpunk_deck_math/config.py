"""Central configuration.

Two kinds of setting live here and they are never mixed:

``RuleConfig``
    Gameplay constants for the Beta environment.  Anything the game rules
    dictate.  Values a user changes are tracked so every report can say
    ``OFFICIAL RULE`` or ``USER OVERRIDE``.

``SellableSettings``
    Constructed deckbuilding targets.  These are *not* rules; the defaults
    come from constructed playtesting and are always labelled
    ``USER / PLAYTESTING HEURISTIC``.

Nothing else in the codebase may hard-code these numbers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Iterable, Mapping

from .methods import Method

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DATA_DIR = PROJECT_ROOT / "data"
PROFILES_DIR = PROJECT_ROOT / "profiles"
DEFAULT_CARD_CACHE = DATA_DIR / "cards_beta.json"

#: Gameplay values believed to be correct for the Beta environment.  They are
#: presented as OFFICIAL RULE; where the official source is unclear the value
#: is documented as an assumption in ``RULE_NOTES``.
OFFICIAL_RULE_DEFAULTS: dict[str, Any] = {
    "main_deck_min": 40,
    "main_deck_max": 50,
    "legend_count": 3,
    "max_card_copies": 3,
    "opening_hand_size": 6,
    "natural_draws_per_turn": 1,
    "max_sells_per_turn": 1,
    "eddie_value": 1,
    "legend_resource_value": 1,
    "max_legend_calls_per_turn": 1,
    "draw_on_first_turn": True,
    "gig_per_turn": 1,
    "mulligan_count": 1,
}

RULE_NOTES: dict[str, str] = {
    "draw_on_first_turn": (
        "Whether the player on the play draws during turn 1. Modelled as a "
        "rule toggle because it materially changes cards-seen counts."
    ),
    "mulligan_count": "How many times a hand may be redrawn before it is kept.",
    "gig_per_turn": "Gigs gained during the start phase of each turn.",
}


def normalize_pct(value: Any) -> float:
    """Normalize ``60``, ``\"60\"``, ``\"60%\"``, ``0.60`` -> ``0.60``.

    Values in ``(0, 1]`` are treated as already-normalized fractions; values
    above 1 are treated as percentages.  ``0`` is zero either way.
    """
    if value is None:
        raise ValueError("percentage value is required")
    if isinstance(value, str):
        text = value.strip().rstrip("%").strip()
        if not text:
            raise ValueError("empty percentage value")
        value = float(text)
    value = float(value)
    if value < 0:
        raise ValueError(f"percentage may not be negative: {value}")
    if value > 1.0:
        value = value / 100.0
    if value > 1.0:
        raise ValueError(f"percentage above 100%: {value}")
    return value


@dataclass
class RuleConfig:
    """Beta gameplay constants, with override tracking."""

    main_deck_min: int = OFFICIAL_RULE_DEFAULTS["main_deck_min"]
    main_deck_max: int = OFFICIAL_RULE_DEFAULTS["main_deck_max"]
    legend_count: int = OFFICIAL_RULE_DEFAULTS["legend_count"]
    max_card_copies: int = OFFICIAL_RULE_DEFAULTS["max_card_copies"]
    opening_hand_size: int = OFFICIAL_RULE_DEFAULTS["opening_hand_size"]
    natural_draws_per_turn: int = OFFICIAL_RULE_DEFAULTS["natural_draws_per_turn"]
    max_sells_per_turn: int = OFFICIAL_RULE_DEFAULTS["max_sells_per_turn"]
    eddie_value: int = OFFICIAL_RULE_DEFAULTS["eddie_value"]
    legend_resource_value: int = OFFICIAL_RULE_DEFAULTS["legend_resource_value"]
    max_legend_calls_per_turn: int = OFFICIAL_RULE_DEFAULTS["max_legend_calls_per_turn"]
    draw_on_first_turn: bool = OFFICIAL_RULE_DEFAULTS["draw_on_first_turn"]
    gig_per_turn: int = OFFICIAL_RULE_DEFAULTS["gig_per_turn"]
    mulligan_count: int = OFFICIAL_RULE_DEFAULTS["mulligan_count"]

    def overrides(self) -> dict[str, Any]:
        """Fields whose value differs from the official default."""
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if getattr(self, f.name) != OFFICIAL_RULE_DEFAULTS[f.name]
        }

    def provenance(self, name: str) -> str:
        if name not in OFFICIAL_RULE_DEFAULTS:
            raise KeyError(name)
        return "USER OVERRIDE" if name in self.overrides() else "OFFICIAL RULE"

    def cards_seen(self, turn: int) -> int:
        """Cards seen by the end of the draw step of ``turn``.

        Turn 0 means "opening hand only".  Natural draws only; conditional
        draw effects are handled by the simulator, never folded in here.
        """
        if turn < 0:
            raise ValueError("turn may not be negative")
        if turn == 0:
            return self.opening_hand_size
        draws = turn if self.draw_on_first_turn else turn - 1
        return self.opening_hand_size + max(0, draws) * self.natural_draws_per_turn

    def describe(self) -> list[tuple[str, Any, str]]:
        return [
            (f.name, getattr(self, f.name), self.provenance(f.name))
            for f in fields(self)
        ]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuleConfig":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown rule settings: {sorted(unknown)}")
        return cls(**dict(data))


@dataclass
class SellableSettings:
    """Constructed sellable-density targets.

    These are deckbuilding heuristics from constructed playtesting, not game
    rules.  ``method`` is attached to every report that uses them.
    """

    minimum_pct: float = 0.60
    target_pct: float = 0.625
    target_range: tuple[float, float] = (0.60, 0.65)
    method: Method = field(default=Method.PLAYTESTING_HEURISTIC, repr=False)

    def __post_init__(self) -> None:
        self.minimum_pct = normalize_pct(self.minimum_pct)
        self.target_pct = normalize_pct(self.target_pct)
        lo, hi = self.target_range
        lo, hi = normalize_pct(lo), normalize_pct(hi)
        if lo > hi:
            raise ValueError("target_sellable_min may not exceed target_sellable_max")
        self.target_range = (lo, hi)

    @classmethod
    def build(
        cls,
        minimum: Any = None,
        target: Any = None,
        range_min: Any = None,
        range_max: Any = None,
    ) -> "SellableSettings":
        base = cls()
        lo, hi = base.target_range
        return cls(
            minimum_pct=base.minimum_pct if minimum is None else minimum,
            target_pct=base.target_pct if target is None else target,
            target_range=(
                lo if range_min is None else normalize_pct(range_min),
                hi if range_max is None else normalize_pct(range_max),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_sellable_pct": self.minimum_pct,
            "target_sellable_pct": self.target_pct,
            "target_sellable_range": list(self.target_range),
            "method": self.method.value,
        }


@dataclass
class AnalysisConfig:
    """Everything one analysis run needs, plus export metadata."""

    rules: RuleConfig = field(default_factory=RuleConfig)
    sellable: SellableSettings = field(default_factory=SellableSettings)
    card_cache_path: Path = DEFAULT_CARD_CACHE
    simulation_iterations: int = 500_000
    simulation_seed: int | None = 20770301
    max_turn: int = 6
    warning_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "dead_card_burden_turn3": 0.30,
            "low_playability_share_turn3": 0.15,
            "low_playability_cutoff": 0.10,
            "min_action_density_turn3": 0.35,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rules": self.rules.to_dict(),
            "rule_overrides": self.rules.overrides(),
            "sellable": self.sellable.to_dict(),
            "card_cache_path": str(self.card_cache_path),
            "simulation_iterations": self.simulation_iterations,
            "simulation_seed": self.simulation_seed,
            "max_turn": self.max_turn,
            "warning_thresholds": dict(self.warning_thresholds),
        }

    @classmethod
    def load(cls, path: str | Path) -> "AnalysisConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg = cls()
        if "rules" in data:
            cfg.rules = RuleConfig.from_dict(data["rules"])
        if "sellable" in data:
            s = data["sellable"]
            cfg.sellable = SellableSettings.build(
                s.get("minimum_sellable_pct"),
                s.get("target_sellable_pct"),
                (s.get("target_sellable_range") or [None, None])[0],
                (s.get("target_sellable_range") or [None, None])[1],
            )
        for key in ("simulation_iterations", "simulation_seed", "max_turn"):
            if key in data:
                setattr(cfg, key, data[key])
        if "card_cache_path" in data:
            cfg.card_cache_path = Path(data["card_cache_path"])
        if "warning_thresholds" in data:
            cfg.warning_thresholds.update(data["warning_thresholds"])
        return cfg

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def turns(max_turn: int) -> Iterable[int]:
    return range(1, max_turn + 1)
