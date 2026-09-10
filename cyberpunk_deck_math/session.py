"""Wiring shared by the CLI and the Streamlit app.

Loads the card cache, parses a deck, resolves profiles, and assembles the
:class:`AnalysisConfig` for a run — so both front-ends behave identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from .analytics import playability
from .config import (
    DEFAULT_CARD_CACHE,
    PROFILES_DIR,
    AnalysisConfig,
    RuleConfig,
    SellableSettings,
)
from .database.cache import CardDatabase
from .database.placeholder import DISCLAIMER, build_placeholder_pool
from .models import Deck, PlayabilityProfile
from .parser import ParseResult, parse_decklist
from .probability.mulligan import MulliganPolicy, load_policies
from .simulation.board_proxy import BoardProxy

MULLIGAN_DIR = PROFILES_DIR / "mulligan"
STRATEGY_DIR = PROFILES_DIR / "strategies"


@dataclass
class Session:
    database: CardDatabase
    config: AnalysisConfig
    deck: Optional[Deck] = None
    parse: Optional[ParseResult] = None
    profile: Optional[PlayabilityProfile] = None
    board_proxy: BoardProxy = field(default_factory=BoardProxy)
    policies: dict[str, MulliganPolicy] = field(default_factory=dict)
    strategy: dict[str, Any] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)

    @property
    def using_placeholder_data(self) -> bool:
        return self.database.data_provenance != "official"


def load_card_database(
    path: str | Path | None = None, allow_placeholder: bool = True
) -> tuple[CardDatabase, list[str]]:
    """Load the cache, falling back to the placeholder pool with a loud notice."""
    target = Path(path) if path else DEFAULT_CARD_CACHE
    notices: list[str] = []
    if target.exists():
        database = CardDatabase.load(target)
        if database.data_provenance != "official":
            notices.append(DISCLAIMER)
        return database, notices
    if not allow_placeholder:
        raise FileNotFoundError(
            f"no card cache at {target}. Run `python cli.py update-cards` first."
        )
    notices.append(
        f"No card cache at {target}; falling back to the built-in placeholder pool. "
        + DISCLAIMER
    )
    return build_placeholder_pool(), notices


def load_strategy(name: str | Path) -> dict[str, Any]:
    import json

    path = Path(name)
    if not path.exists():
        path = STRATEGY_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"no strategy profile at {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_session(
    decklist: Optional[str] = None,
    deck_path: Optional[str | Path] = None,
    cache_path: Optional[str | Path] = None,
    minimum_sellable: Any = None,
    target_sellable: Any = None,
    target_sellable_min: Any = None,
    target_sellable_max: Any = None,
    playability_profile: Optional[str] = None,
    mulligan_profile: Optional[str] = None,
    strategy_profile: Optional[str] = None,
    rules: Optional[RuleConfig] = None,
    iterations: Optional[int] = None,
    seed: Optional[int] = None,
    max_turn: Optional[int] = None,
    ignore_legality: bool = False,
    deck_name: Optional[str] = None,
) -> Session:
    database, notices = load_card_database(cache_path)
    strategy = load_strategy(strategy_profile) if strategy_profile else {}

    settings_source = strategy.get("sellable", {})
    settings = SellableSettings.build(
        minimum=minimum_sellable
        if minimum_sellable is not None
        else settings_source.get("minimum_sellable_pct"),
        target=target_sellable
        if target_sellable is not None
        else settings_source.get("target_sellable_pct"),
        range_min=target_sellable_min
        if target_sellable_min is not None
        else (settings_source.get("target_sellable_range") or [None, None])[0],
        range_max=target_sellable_max
        if target_sellable_max is not None
        else (settings_source.get("target_sellable_range") or [None, None])[1],
    )

    config = AnalysisConfig(
        rules=rules or RuleConfig(),
        sellable=settings,
        card_cache_path=Path(cache_path) if cache_path else DEFAULT_CARD_CACHE,
    )
    if iterations is not None:
        config.simulation_iterations = iterations
    if seed is not None:
        config.simulation_seed = seed
    if max_turn is not None:
        config.max_turn = max_turn

    session = Session(
        database=database,
        config=config,
        board_proxy=(
            BoardProxy.from_dict(strategy["board_proxy"])
            if strategy.get("board_proxy")
            else BoardProxy()
        ),
        policies=load_policies([MULLIGAN_DIR]),
        strategy=strategy,
        notices=notices,
    )

    if deck_path and decklist is None:
        decklist = Path(deck_path).read_text(encoding="utf-8")
    if decklist is not None:
        session.parse = parse_decklist(
            decklist,
            database,
            config.rules,
            deck_name=deck_name,
            ignore_legality=ignore_legality,
        )
        session.deck = session.parse.deck

    profile_name = playability_profile or strategy.get("playability_profile")
    if profile_name:
        session.profile = playability.load_profile(profile_name)
    elif session.deck is not None:
        session.profile = playability.default_profile(session.deck, "default")
        session.notices.append(
            "No playability profile given; using the cost-gated default. Create one "
            "under profiles/playability/ for deck-specific estimates."
        )

    chosen_mulligan = mulligan_profile or strategy.get("mulligan_profile")
    if chosen_mulligan and chosen_mulligan not in session.policies:
        raise KeyError(
            f"unknown mulligan profile {chosen_mulligan!r}; available: "
            + ", ".join(sorted(session.policies))
        )
    session.strategy.setdefault("mulligan_profile", chosen_mulligan or "")
    return session


def selected_policy(session: Session, name: Optional[str] = None) -> Optional[MulliganPolicy]:
    key = name or session.strategy.get("mulligan_profile")
    if not key:
        return None
    return session.policies.get(key)


def strategy_targets(session: Session, override: Sequence[str] = ()) -> tuple[str, ...]:
    if override:
        return tuple(override)
    return tuple(session.strategy.get("targets", ()))
