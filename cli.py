#!/usr/bin/env python3
"""Command-line interface for the Cyberpunk TCG deck analyzer.

    python cli.py analyze deck.txt --target "Jackie Welles — Ride or Die Choom" --turn 3
    python cli.py sells deck.txt --through-turn 3
    python cli.py compare deck_a.txt deck_b.txt
    python cli.py update-cards

Run ``python cli.py <command> --help`` for the options of any command.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from cyberpunk_deck_math import export
from cyberpunk_deck_math.analytics import (
    axioms,
    deck_summary,
    interpretation,
    marginal_value,
    mulligan_analytics,
    playability,
    recommender,
    sell_density,
    sensitivity,
    target as target_analytics,
)
from cyberpunk_deck_math.config import RuleConfig
from cyberpunk_deck_math.database.cache import CardDatabase
from cyberpunk_deck_math.database.fetch_official import FetchError, update_cards
from cyberpunk_deck_math.database.placeholder import (
    DISCLAIMER,
    SAMPLE_DECK_TEXT,
    build_placeholder_pool,
)
from cyberpunk_deck_math.probability import sells as sells_math
from cyberpunk_deck_math.session import Session, build_session, selected_policy
from cyberpunk_deck_math.simulation.game import ITERATION_CHOICES


# ----------------------------------------------------------------- arg plumbing


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cards", dest="cache_path", help="path to the card cache")
    parser.add_argument("--minimum-sellable", help="minimum sellable %% (60, 60%%, 0.60)")
    parser.add_argument("--target-sellable", help="target sellable %%")
    parser.add_argument("--target-sellable-min", help="target range lower bound")
    parser.add_argument("--target-sellable-max", help="target range upper bound")
    parser.add_argument("--playability-profile", help="playability profile name or path")
    parser.add_argument("--mulligan-profile", help="saved mulligan profile name")
    parser.add_argument("--strategy", dest="strategy_profile", help="strategy profile name")
    parser.add_argument("--max-turn", type=int, default=6)
    parser.add_argument("--ignore-legality", action="store_true",
                        help="parse and analyse an illegal deck anyway")
    parser.add_argument("--opening-hand-size", type=int, help="rule override")
    parser.add_argument("--draws-per-turn", type=int, help="rule override")
    parser.add_argument("--sells-per-turn", type=int, help="rule override")
    parser.add_argument("--export", dest="export_stem",
                        help="write <stem>.json/.csv/.md with all assumptions")


def add_simulation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--iterations", type=int, default=100_000,
                        help=f"Monte Carlo iterations (suggested: {ITERATION_CHOICES})")
    parser.add_argument("--seed", type=int, default=20770301)


def rules_from_args(args: argparse.Namespace) -> RuleConfig:
    rules = RuleConfig()
    if getattr(args, "opening_hand_size", None):
        rules.opening_hand_size = args.opening_hand_size
    if getattr(args, "draws_per_turn", None):
        rules.natural_draws_per_turn = args.draws_per_turn
    if getattr(args, "sells_per_turn", None):
        rules.max_sells_per_turn = args.sells_per_turn
    return rules


def session_from_args(args: argparse.Namespace, deck_path: Optional[str] = None) -> Session:
    session = build_session(
        deck_path=deck_path,
        cache_path=getattr(args, "cache_path", None),
        minimum_sellable=getattr(args, "minimum_sellable", None),
        target_sellable=getattr(args, "target_sellable", None),
        target_sellable_min=getattr(args, "target_sellable_min", None),
        target_sellable_max=getattr(args, "target_sellable_max", None),
        playability_profile=getattr(args, "playability_profile", None),
        mulligan_profile=getattr(args, "mulligan_profile", None),
        strategy_profile=getattr(args, "strategy_profile", None),
        rules=rules_from_args(args),
        iterations=getattr(args, "iterations", None),
        seed=getattr(args, "seed", None),
        max_turn=getattr(args, "max_turn", None),
        ignore_legality=getattr(args, "ignore_legality", False),
    )
    for notice in session.notices:
        print(f"NOTE: {notice}\n", file=sys.stderr)
    if session.parse is not None:
        report = session.parse.render()
        problems = (
            session.parse.errors or session.parse.unknown or session.parse.ambiguous
            or session.parse.warnings
        )
        if problems:
            print(report + "\n", file=sys.stderr)
        if session.parse.errors and not getattr(args, "ignore_legality", False):
            raise SystemExit(
                "deck failed validation; fix it or pass --ignore-legality to continue"
            )
    return session


def maybe_export(args: argparse.Namespace, session: Session, payload: dict[str, Any]) -> None:
    stem = getattr(args, "export_stem", None)
    if not stem:
        return
    payload = dict(payload)
    payload["metadata"] = export.analysis_metadata(
        session.deck,
        session.config,
        session.database,
        mulligan_profile=session.strategy.get("mulligan_profile", ""),
        playability_profile=session.profile.name if session.profile else "",
    )
    paths = export.export_all(payload, stem)
    print("\nExported:")
    for kind, path in paths.items():
        print(f"  {kind:<9} {path}")


def targets_from_args(args: argparse.Namespace, session: Session) -> tuple[str, ...]:
    explicit = getattr(args, "target", None)
    if explicit:
        return (explicit,)
    return tuple(session.strategy.get("targets", ()))


# --------------------------------------------------------------------- commands


def cmd_analyze(args: argparse.Namespace) -> int:
    session = session_from_args(args, args.deck)
    deck, profile = session.deck, session.profile
    targets = targets_from_args(args, session)

    summary = deck_summary.summarize(deck, profile, session.config, targets)
    print(deck_summary.render_summary(summary))

    print("\nCONCLUSIONS")
    for line in interpretation.summary_conclusions(summary, targets, min(args.turn, args.max_turn)):
        print(f"  - {line}")

    payload: dict[str, Any] = {"summary": summary.to_dict()}

    if targets and not args.no_simulation:
        policy = selected_policy(session, getattr(args, "mulligan_profile", None))
        print(
            f"\nRunning {args.iterations:,} simulated games "
            f"(seed {args.seed}, mulligan: {policy.name if policy else 'none'})..."
        )
        report = target_analytics.target_report(
            deck, targets[0], args.turn, profile, session.config.rules, policy,
            args.iterations, args.seed, board_proxy=session.board_proxy,
        )
        print()
        print(report.render())
        payload["target"] = report.to_dict()
        entry = deck.find(targets[0])
        if entry and entry.card.cost:
            print()
            print("  " + interpretation.resource_sentence(
                entry.card.name, entry.card.cost, args.turn,
                report.resources_available.value,
            ))

    maybe_export(args, session, payload)
    return 0


def cmd_sells(args: argparse.Namespace) -> int:
    session = session_from_args(args, args.deck)
    deck = session.deck
    report = sell_density.sell_report(
        deck, session.config.sellable, session.config.rules, session.profile, args.max_turn
    )
    status = report.status
    print(f"DECK: {deck.name}")
    print(interpretation.sellable_sentence(status))
    print()
    print("SELL CONSISTENCY                        [EXACT — Hypergeometric]")
    for turn, result in report.consecutive.items():
        if turn > args.through_turn and args.through_turn > 0:
            break
        print(
            f"  through T{turn}: {result.value:>8.2%}   "
            f"(miss at least one: {report.misses[turn].value:.2%})"
        )
    if report.effective:
        print()
        print(f"EFFECTIVE SELLABLE DENSITY              [{session.profile.source}]")
        for turn, result in report.effective.items():
            print(f"  T{turn}: {result.value:.1%}")

    print()
    print("SELLABLE DENSITY REFERENCE TABLE        [EXACT — Hypergeometric]")
    rows = sells_math.density_table(deck.size, max_turn=args.max_turn, rules=session.config.rules)
    header = f"{'Sellables':>10}{'%':>8}" + "".join(
        f"{'T' + str(t):>9}" for t in range(1, args.max_turn + 1)
    )
    print(header)
    for row in rows:
        marker = " <- current" if row.sellables == deck.sellable_count else ""
        print(
            f"{row.sellables:>10}{row.pct:>8.1%}"
            + "".join(f"{row.by_turn[t].value:>9.2%}" for t in range(1, args.max_turn + 1))
            + marker
        )

    print()
    print("TARGET SENSITIVITY")
    counts = sorted(
        {
            deck.sellable_count,
            *[
                sells_math.cards_needed(deck.size, 0, p)
                for p in (0.55, 0.575, 0.60, 0.625, 0.65, 0.675)
            ],
        }
    )
    for count in counts:
        if count > deck.size:
            continue
        curve = sells_math.sell_curve(deck.size, count, args.max_turn, session.config.rules)
        print(
            f"  {count:>3} sellables ({count / deck.size:>6.1%}): "
            + "  ".join(f"T{t}:{curve[t].value:.2%}" for t in range(1, args.max_turn + 1))
        )
    if status.cards_to_target:
        print()
        print("  " + interpretation.sell_step_sentence(
            deck.size, status.sellable_count,
            status.sellable_count + status.cards_to_target,
            min(args.through_turn or 3, args.max_turn),
        ))

    maybe_export(args, session, {"sells": report.to_dict()})
    return 0


def cmd_target(args: argparse.Namespace) -> int:
    session = session_from_args(args, args.deck)
    policy = selected_policy(session, getattr(args, "mulligan_profile", None))
    report = target_analytics.target_report(
        session.deck, args.target, args.turn, session.profile, session.config.rules,
        policy, args.iterations, args.seed, board_proxy=session.board_proxy,
    )
    print(report.render())

    if args.compare_copies:
        filler = session.database.get(args.filler) if args.filler else None
        if filler is None:
            filler = _guess_filler(session, args.target)
        comparison = marginal_value.compare_copies(
            session.deck, args.target, filler, session.profile,
            (args.compare_copies[0], args.compare_copies[1]),
            session.config.rules, args.max_turn,
        )
        print()
        print(_render_comparison(comparison, args.turn))
        print()
        print("  " + interpretation.copies_sentence(comparison, args.target, args.turn))
    maybe_export(args, session, {"target": report.to_dict()})
    return 0


def cmd_mulligan(args: argparse.Namespace) -> int:
    session = session_from_args(args, args.deck)
    targets = targets_from_args(args, session)
    if not targets:
        raise SystemExit("pass --target or use a strategy profile that defines one")
    names = args.policies or list(session.policies)
    missing = [n for n in names if n not in session.policies]
    if missing:
        raise SystemExit(f"unknown mulligan profile(s): {', '.join(missing)}")
    policies = [session.policies[n] for n in names]
    print(f"Comparing {len(policies)} mulligan policies over {args.iterations:,} games each...\n")
    rows = mulligan_analytics.compare_policies(
        session.deck, policies, targets, session.profile, session.config.rules,
        args.iterations, args.opening_iterations, args.seed, max(args.turn, 1),
        board_proxy=session.board_proxy,
    )
    print(mulligan_analytics.render_comparison(rows, args.turn))
    print()
    print("  " + interpretation.mulligan_sentence(rows, args.turn))
    maybe_export(args, session, {"mulligan": [r.to_dict() for r in rows]})
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    session_a = session_from_args(args, args.deck_a)
    session_b = build_session(
        deck_path=args.deck_b,
        cache_path=getattr(args, "cache_path", None),
        playability_profile=getattr(args, "playability_profile", None),
        strategy_profile=getattr(args, "strategy_profile", None),
        rules=rules_from_args(args),
        ignore_legality=args.ignore_legality,
    )
    targets = targets_from_args(args, session_a)
    if not targets:
        raise SystemExit("pass --target or use a strategy profile that defines one")
    comparison = marginal_value.compare_decks(
        session_a.deck, session_b.deck, targets[0], session_a.profile,
        session_a.config.rules, args.max_turn,
    )
    print(_render_comparison(comparison, args.turn))
    print()
    print("  " + interpretation.comparison_sentence(comparison, args.turn))
    maybe_export(args, session_a, {"comparison": comparison.to_dict()})
    return 0


def cmd_recommend(args: argparse.Namespace) -> int:
    session = session_from_args(args, args.deck)
    targets = targets_from_args(args, session)
    recommendation = recommender.recommend_sellable_swaps(
        session.deck, session.profile, session.config.sellable, targets, args.turn
    )
    status = recommendation.status
    print(f"DECK: {session.deck.name}")
    print(interpretation.sellable_sentence(status))
    print()
    print("CANDIDATE SLOTS TO CONVERT TO SELLABLES   [heuristic ranking, not advice]")
    header = f"{'Card':<34}{'x':>3}{'Cost':>6}{'Strat T' + str(args.turn):>10}{'Score':>8}"
    print(header)
    print("-" * len(header))
    for candidate in recommendation.candidates:
        print(
            f"{candidate.name[:33]:<34}{candidate.copies:>3}"
            f"{('?' if candidate.cost is None else candidate.cost):>6}"
            f"{candidate.early_strategic:>10.0%}{candidate.score:>8.2f}"
        )
        print(f"    tradeoff: {candidate.tradeoff}")
    print()
    for note in recommendation.notes:
        print(f"  - {note}")
    maybe_export(args, session, {"recommendation": recommendation.to_dict()})
    return 0


def cmd_sensitivity(args: argparse.Namespace) -> int:
    session = session_from_args(args, args.deck)
    runs = []
    runs.append(
        sensitivity.sweep_sellable_target(
            session.deck, through_turn=args.turn, rules=session.config.rules
        )
    )
    if args.card:
        runs.append(
            sensitivity.sweep_strategic_playability(
                session.deck, session.profile, args.card, args.turn,
                values=tuple(float(v) for v in args.values) if args.values else (0.0, 0.05, 0.10, 0.20, 0.30),
            )
        )
        runs.append(
            sensitivity.sweep_strategic_playability(
                session.deck, session.profile, args.card, args.turn,
                values=tuple(float(v) for v in args.values) if args.values else (0.0, 0.05, 0.10, 0.20, 0.30),
                metric="dead_burden",
            )
        )
    for run in runs:
        print(f"\n{run.assumption} -> {run.metric}   [{run.method.value}]")
        for value, outcome in zip(run.values, run.outcomes):
            print(f"  {value:>8.3f}  ->  {outcome:.2%}")
        print(f"  spread {run.spread:.2%} — {run.to_dict()['verdict']}")
    flags = sensitivity.flag_material(runs)
    if flags:
        print("\nMATERIAL ASSUMPTIONS")
        for flag in flags:
            print(f"  ! {flag}")
    maybe_export(args, session, {"sensitivity": [r.to_dict() for r in runs]})
    return 0


def cmd_update_cards(args: argparse.Namespace) -> int:
    try:
        _, report = update_cards(
            cache_path=args.cache_path or "data/cards_beta.json",
            source_url=args.source_url,
            source_file=args.source_file,
            json_path=args.json_path,
            set_codes=args.set_code,
            keep_all=args.keep_all,
            timeout=args.timeout,
        )
    except FetchError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(report.render())
    return 0


def cmd_init_placeholder(args: argparse.Namespace) -> int:
    """Write the placeholder pool so the app runs without network access."""
    database = build_placeholder_pool()
    path = database.save(args.cache_path or "data/cards_beta.placeholder.json")
    deck_path = Path(args.deck_path or "data/sample_deck_jackie.txt")
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    deck_path.write_text(SAMPLE_DECK_TEXT, encoding="utf-8")
    print(f"Wrote {len(database)} placeholder cards to {path}")
    print(f"Wrote the sample decklist to {deck_path}")
    print(f"\n{DISCLAIMER}")
    return 0


def cmd_cards(args: argparse.Namespace) -> int:
    database, notices = _load_database(args)
    for notice in notices:
        print(f"NOTE: {notice}\n", file=sys.stderr)
    if args.name:
        result = database.match(args.name)
        if result.card is None:
            print(f"No unique match for {args.name!r}: {result.reason}")
            for candidate in result.candidates:
                print(f"  candidate: {candidate.name} [{candidate.card_id}]")
            return 1
        card = result.card
        for key, value in card.to_dict().items():
            print(f"{key:<22} {value}")
        return 0
    print(f"{len(database)} cards cached (provenance: {database.data_provenance})")
    print(f"updated_at: {database.updated_at}   source: {database.source_url}")
    for card in sorted(database.cards, key=lambda c: (c.set_code or "", c.card_id)):
        flags = "".join(
            [
                "L" if card.is_legend else "-",
                "S" if card.is_sellable else "-",
                "X" if card.starter_exclusive else "-",
            ]
        )
        print(f"  {card.card_id:<12} {flags}  cost={str(card.cost):<4} {card.name}")
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    """Show the configured rules and which values are user overrides."""
    rules = rules_from_args(args)
    print(f"{'Setting':<28}{'Value':>10}   Provenance")
    for name, value, provenance in rules.describe():
        print(f"{name:<28}{str(value):>10}   {provenance}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from demo import run_demo

    return run_demo(iterations=args.iterations, seed=args.seed)


# ----------------------------------------------------------------------- helpers


def _load_database(args: argparse.Namespace) -> tuple[CardDatabase, list[str]]:
    from cyberpunk_deck_math.session import load_card_database

    return load_card_database(getattr(args, "cache_path", None))


def _guess_filler(session: Session, exclude: str):
    """Pick the most redundant filler card to trade against."""
    from cyberpunk_deck_math.models import normalize_name

    excluded = normalize_name(exclude)
    candidates = [
        entry
        for entry in session.deck.main
        if entry.card.key != excluded and entry.card.has_tag("filler")
    ] or [entry for entry in session.deck.main if entry.card.key != excluded]
    if not candidates:
        raise SystemExit("no filler card available to trade against; pass --filler")
    return max(candidates, key=lambda e: e.copies).card


def _render_comparison(comparison: marginal_value.Comparison, turn: int) -> str:
    a, b = comparison.a, comparison.b
    lines = [
        f"{'Metric':<26}{a.name[:18]:>20}{b.name[:18]:>20}{'Delta':>12}",
        "-" * 78,
    ]
    rows = [
        ("mechanical sellable %", a.sellable_pct, b.sellable_pct),
        (f"effective sellable T{turn}", a.effective_sellable[turn], b.effective_sellable[turn]),
        (f"target access T{turn}", a.target_access[turn], b.target_access[turn]),
        (f"sell consistency T{turn}", a.sell_consistency[turn], b.sell_consistency[turn]),
        (f"dead-card burden T{turn}", a.dead_burden[turn], b.dead_burden[turn]),
        (f"action density T{turn}", a.action_density[turn], b.action_density[turn]),
        (f"target+resources T{turn}", a.target_and_resources[turn], b.target_and_resources[turn]),
    ]
    for label, left, right in rows:
        lines.append(
            f"{label:<26}{left:>19.2%}{right:>20.2%}{(right - left) * 100:>+11.2f}pp"
        )
    for note in comparison.notes:
        lines.append(f"  note: {note}")
    return "\n".join(lines)


# ------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="full deck dashboard plus a target report")
    analyze.add_argument("deck")
    analyze.add_argument("--target", help="target card name, id or collector number")
    analyze.add_argument("--turn", type=int, default=3)
    analyze.add_argument("--no-simulation", action="store_true")
    add_common_arguments(analyze)
    add_simulation_arguments(analyze)
    analyze.set_defaults(func=cmd_analyze)

    sells_cmd = sub.add_parser("sells", help="sell consistency and density tables")
    sells_cmd.add_argument("deck")
    sells_cmd.add_argument("--through-turn", type=int, default=0,
                           help="limit the printed consecutive-sell rows")
    add_common_arguments(sells_cmd)
    sells_cmd.set_defaults(func=cmd_sells)

    target_cmd = sub.add_parser("target", help="layered target playability")
    target_cmd.add_argument("deck")
    target_cmd.add_argument("--target", required=True)
    target_cmd.add_argument("--turn", type=int, default=3)
    target_cmd.add_argument("--compare-copies", type=int, nargs=2, metavar=("A", "B"),
                            help="e.g. --compare-copies 2 3")
    target_cmd.add_argument("--filler", help="card to trade against when changing copies")
    add_common_arguments(target_cmd)
    add_simulation_arguments(target_cmd)
    target_cmd.set_defaults(func=cmd_target)

    mulligan_cmd = sub.add_parser("mulligan", help="compare mulligan policies")
    mulligan_cmd.add_argument("deck")
    mulligan_cmd.add_argument("--target")
    mulligan_cmd.add_argument("--turn", type=int, default=3)
    mulligan_cmd.add_argument("--policies", nargs="*", help="policy names to compare")
    mulligan_cmd.add_argument("--opening-iterations", type=int, default=None)
    add_common_arguments(mulligan_cmd)
    add_simulation_arguments(mulligan_cmd)
    mulligan_cmd.set_defaults(func=cmd_mulligan, iterations=20_000)

    compare_cmd = sub.add_parser("compare", help="compare two decklists slot for slot")
    compare_cmd.add_argument("deck_a")
    compare_cmd.add_argument("deck_b")
    compare_cmd.add_argument("--target")
    compare_cmd.add_argument("--turn", type=int, default=3)
    add_common_arguments(compare_cmd)
    compare_cmd.set_defaults(func=cmd_compare)

    recommend_cmd = sub.add_parser("recommend", help="sellable slot recommender")
    recommend_cmd.add_argument("deck")
    recommend_cmd.add_argument("--target")
    recommend_cmd.add_argument("--turn", type=int, default=3)
    add_common_arguments(recommend_cmd)
    recommend_cmd.set_defaults(func=cmd_recommend)

    sensitivity_cmd = sub.add_parser("sensitivity", help="sweep uncertain assumptions")
    sensitivity_cmd.add_argument("deck")
    sensitivity_cmd.add_argument("--card", help="card whose playability to sweep")
    sensitivity_cmd.add_argument("--turn", type=int, default=3)
    sensitivity_cmd.add_argument("--values", nargs="*", help="assumption values to test")
    add_common_arguments(sensitivity_cmd)
    sensitivity_cmd.set_defaults(func=cmd_sensitivity)

    update = sub.add_parser("update-cards", help="fetch the official Beta card database")
    update.add_argument("--cards", dest="cache_path", help="cache path to write")
    update.add_argument("--source-url", help="official JSON endpoint")
    update.add_argument("--source-file", help="a JSON export from the official site")
    update.add_argument("--json-path", help="dotted path to the card list inside the payload")
    update.add_argument("--set-code", action="append", help="extra Beta set code to accept")
    update.add_argument("--keep-all", action="store_true",
                        help="skip Beta-pool filtering (diagnostic)")
    update.add_argument("--timeout", type=float, default=30.0)
    update.set_defaults(func=cmd_update_cards)

    init = sub.add_parser("init-placeholder",
                          help="write the offline placeholder pool and sample deck")
    init.add_argument("--cards", dest="cache_path")
    init.add_argument("--deck-path")
    init.set_defaults(func=cmd_init_placeholder)

    cards_cmd = sub.add_parser("cards", help="list or inspect cached cards")
    cards_cmd.add_argument("name", nargs="?")
    cards_cmd.add_argument("--cards", dest="cache_path")
    cards_cmd.set_defaults(func=cmd_cards)

    rules_cmd = sub.add_parser("rules", help="show rule settings and overrides")
    rules_cmd.add_argument("--opening-hand-size", type=int)
    rules_cmd.add_argument("--draws-per-turn", type=int)
    rules_cmd.add_argument("--sells-per-turn", type=int)
    rules_cmd.set_defaults(func=cmd_rules)

    demo_cmd = sub.add_parser("demo", help="run the first-demonstration analysis")
    demo_cmd.add_argument("--iterations", type=int, default=100_000)
    demo_cmd.add_argument("--seed", type=int, default=20770301)
    demo_cmd.set_defaults(func=cmd_demo)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
