"""Shared fixtures.

The tests run against the placeholder pool so they never need the network or
an official card cache.
"""

from __future__ import annotations

import pytest

from cyberpunk_deck_math.analytics.playability import default_profile, load_profile
from cyberpunk_deck_math.config import AnalysisConfig, RuleConfig, SellableSettings
from cyberpunk_deck_math.database.placeholder import SAMPLE_DECK_TEXT, build_placeholder_pool
from cyberpunk_deck_math.parser import parse_decklist

TARGET = "Jackie Welles — Ride or Die Choom"


@pytest.fixture(scope="session")
def database():
    return build_placeholder_pool()


@pytest.fixture()
def parse_result(database):
    return parse_decklist(SAMPLE_DECK_TEXT, database)


@pytest.fixture()
def deck(parse_result):
    return parse_result.deck


@pytest.fixture()
def rules():
    return RuleConfig()


@pytest.fixture()
def profile(deck):
    return load_profile("YYG_Jackie")


@pytest.fixture()
def flat_profile(deck):
    """A profile with no per-card values: everything legal and correct."""
    return default_profile(None, "flat")


@pytest.fixture()
def config(rules):
    return AnalysisConfig(rules=rules, sellable=SellableSettings(), max_turn=6)
