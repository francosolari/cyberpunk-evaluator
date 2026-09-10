"""Configuration provenance, exports, sessions and the CLI surface."""

from __future__ import annotations

import json

import pytest

from cyberpunk_deck_math import export
from cyberpunk_deck_math.config import (
    OFFICIAL_RULE_DEFAULTS,
    AnalysisConfig,
    RuleConfig,
    SellableSettings,
)
from cyberpunk_deck_math.methods import Method, Result
from cyberpunk_deck_math.session import build_session, selected_policy


def test_official_rules_are_reported_as_official():
    rules = RuleConfig()
    assert rules.overrides() == {}
    assert rules.provenance("opening_hand_size") == "OFFICIAL RULE"


def test_user_overrides_are_tracked():
    rules = RuleConfig(opening_hand_size=7, max_sells_per_turn=2)
    assert rules.overrides() == {"opening_hand_size": 7, "max_sells_per_turn": 2}
    assert rules.provenance("opening_hand_size") == "USER OVERRIDE"
    assert rules.provenance("legend_count") == "OFFICIAL RULE"


def test_defaults_match_the_documented_beta_values():
    assert OFFICIAL_RULE_DEFAULTS["main_deck_min"] == 40
    assert OFFICIAL_RULE_DEFAULTS["main_deck_max"] == 50
    assert OFFICIAL_RULE_DEFAULTS["legend_count"] == 3
    assert OFFICIAL_RULE_DEFAULTS["max_card_copies"] == 3
    assert OFFICIAL_RULE_DEFAULTS["opening_hand_size"] == 6


def test_cards_seen_respects_rule_overrides():
    assert RuleConfig().cards_seen(0) == 6
    assert RuleConfig().cards_seen(3) == 9
    assert RuleConfig(draw_on_first_turn=False).cards_seen(3) == 8
    assert RuleConfig(natural_draws_per_turn=2).cards_seen(3) == 12


def test_sellable_defaults_are_the_playtesting_heuristic():
    settings = SellableSettings()
    assert settings.minimum_pct == 0.60
    assert settings.target_pct == 0.625
    assert settings.target_range == (0.60, 0.65)
    assert settings.method is Method.PLAYTESTING_HEURISTIC
    assert "HEURISTIC" in settings.to_dict()["method"]


def test_analysis_config_round_trips(tmp_path):
    config = AnalysisConfig(
        rules=RuleConfig(opening_hand_size=7),
        sellable=SellableSettings.build("55%", 0.6, 55, 62),
    )
    path = tmp_path / "config.json"
    config.save(path)
    again = AnalysisConfig.load(path)
    assert again.rules.opening_hand_size == 7
    assert again.sellable.minimum_pct == 0.55
    assert again.sellable.target_range == (0.55, 0.62)
    assert again.to_dict()["rule_overrides"] == {"opening_hand_size": 7}


def test_unknown_rule_keys_are_rejected():
    with pytest.raises(ValueError):
        RuleConfig.from_dict({"not_a_rule": 1})


def test_result_labels_and_precision():
    exact = Result(0.4782, Method.EXACT_HYPERGEOMETRIC, "p")
    heuristic = Result(0.4782, Method.HEURISTIC_LLM, "p")
    assert exact.formatted(2) == "47.82%"
    assert heuristic.formatted(2) == "47.8%"  # heuristics never get false precision
    assert exact.method.is_exact() and heuristic.method.is_heuristic()


def test_result_ci_rendering():
    result = Result(0.4782, Method.SIMULATED, "p", sample_size=500_000, ci95=(0.4768, 0.4796))
    text = result.formatted(2)
    assert "95% CI" in text and "n=500,000" in text


def test_export_metadata_carries_assumptions(deck, config, database):
    metadata = export.analysis_metadata(
        deck, config, database, mulligan_profile="Jackie or Draw",
        playability_profile="YYG_Jackie",
    )
    for key in (
        "deck_name", "analysis_date", "card_database_update_date",
        "minimum_sellable_pct", "target_sellable_pct", "target_sellable_range",
        "mulligan_profile", "playability_profile", "simulation_iterations",
        "simulation_seed", "rule_overrides",
    ):
        assert key in metadata
    assert metadata["card_data_provenance"] == "placeholder"


def test_export_json_csv_markdown(tmp_path, deck, config, database):
    payload = {
        "metadata": export.analysis_metadata(deck, config, database),
        "results": {"access": Result(0.4, Method.EXACT_HYPERGEOMETRIC, "P(seen)")},
    }
    paths = export.export_all(payload, tmp_path / "analysis")
    data = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert data["results"]["access"]["method"] == Method.EXACT_HYPERGEOMETRIC.value
    assert "key,value" in paths["csv"].read_text(encoding="utf-8")
    assert "# Cyberpunk TCG deck analysis" in paths["markdown"].read_text(encoding="utf-8")


def test_session_falls_back_to_placeholder_with_a_notice(tmp_path):
    from cyberpunk_deck_math.database.placeholder import SAMPLE_DECK_TEXT

    session = build_session(
        decklist=SAMPLE_DECK_TEXT, cache_path=tmp_path / "missing.json",
        strategy_profile="YYG_Jackie",
    )
    assert session.using_placeholder_data
    assert any("PLACEHOLDER" in n or "placeholder" in n for n in session.notices)
    assert session.deck.size == 40
    assert selected_policy(session).name == "Jackie or Draw"


def test_session_applies_strategy_and_overrides(tmp_path):
    from cyberpunk_deck_math.database.placeholder import SAMPLE_DECK_TEXT

    session = build_session(
        decklist=SAMPLE_DECK_TEXT, strategy_profile="YYG_Jackie",
        minimum_sellable="55%", iterations=1234, seed=7,
    )
    assert session.config.sellable.minimum_pct == 0.55
    assert session.config.simulation_iterations == 1234
    assert session.profile.name == "YYG_Jackie"
    assert session.board_proxy.probability("valid_target", 3) == 0.20


def test_unknown_mulligan_profile_is_rejected():
    from cyberpunk_deck_math.database.placeholder import SAMPLE_DECK_TEXT

    with pytest.raises(KeyError):
        build_session(decklist=SAMPLE_DECK_TEXT, mulligan_profile="Does Not Exist")


def test_cli_parser_accepts_the_documented_commands():
    import cli

    parser = cli.build_parser()
    for argv in (
        ["analyze", "deck.txt"],
        ["analyze", "deck.txt", "--target", "Jackie", "--turn", "3"],
        ["analyze", "deck.txt", "--minimum-sellable", "0.60", "--target-sellable", "0.625"],
        ["analyze", "deck.txt", "--target-sellable-min", "0.60", "--target-sellable-max", "0.65"],
        ["analyze", "deck.txt", "--mulligan-profile", "Jackie or Draw"],
        ["compare", "a.txt", "b.txt"],
        ["update-cards"],
        ["sells", "deck.txt", "--through-turn", "3"],
        ["target", "deck.txt", "--target", "Jackie", "--compare-copies", "2", "3"],
        ["mulligan", "deck.txt", "--policies", "No Mulligan"],
        ["recommend", "deck.txt"],
        ["sensitivity", "deck.txt", "--card", "Memory Relapse"],
        ["cards"],
        ["rules"],
        ["init-placeholder"],
        ["demo"],
    ):
        assert parser.parse_args(argv) is not None


def test_cli_sells_command_runs(capsys, tmp_path):
    import cli
    from cyberpunk_deck_math.database.placeholder import SAMPLE_DECK_TEXT, build_placeholder_pool

    deck_file = tmp_path / "deck.txt"
    deck_file.write_text(SAMPLE_DECK_TEXT, encoding="utf-8")
    cache = tmp_path / "cards.json"
    build_placeholder_pool().save(cache)
    assert cli.main(["sells", str(deck_file), "--cards", str(cache)]) == 0
    output = capsys.readouterr().out
    assert "SELL CONSISTENCY" in output
    assert "EXACT — Hypergeometric" in output


def test_cli_rejects_illegal_decks_without_the_toggle(tmp_path, capsys):
    import cli
    from cyberpunk_deck_math.database.placeholder import build_placeholder_pool

    deck_file = tmp_path / "bad.txt"
    deck_file.write_text("Main Deck\n3x Field Operator\n", encoding="utf-8")
    cache = tmp_path / "cards.json"
    build_placeholder_pool().save(cache)
    with pytest.raises(SystemExit):
        cli.main(["sells", str(deck_file), "--cards", str(cache)])
