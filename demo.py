#!/usr/bin/env python3
"""First demonstration: the sample 40-card deck, Jackie x2 versus Jackie x3.

Run with ``python demo.py`` or ``python cli.py demo``.

The demonstration runs on the *placeholder* card pool unless an official cache
exists at ``data/cards_beta.json``.  Placeholder costs, sellable flags and
effects are assumptions made to exercise the model — they are not claims about
the real cards.  Run ``python cli.py update-cards`` and re-run this demo to see
the same analysis on official data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from cyberpunk_deck_math.analytics import (
    access,
    dead_cards,
    deck_summary,
    interpretation,
    marginal_value,
    mulligan_analytics,
    opportunity_density,
    sell_density,
)
from cyberpunk_deck_math.analytics import target as target_analytics
from cyberpunk_deck_math.database.placeholder import SAMPLE_DECK_TEXT
from cyberpunk_deck_math.probability import sells as sells_math
from cyberpunk_deck_math.session import build_session, selected_policy

TARGET = "Jackie Welles — Ride or Die Choom"
FILLER = "Placeholder Combat Unit"  # non-sellable, so the swap isolates access
SELLABLE_FILLER = "Placeholder Sellable Gig G"
TURN = 3
RULE = "=" * 78


def _heading(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


def run_demo(iterations: int = 100_000, seed: Optional[int] = 20770301) -> int:
    deck_file = Path("data/sample_deck_jackie.txt")
    decklist = deck_file.read_text(encoding="utf-8") if deck_file.exists() else SAMPLE_DECK_TEXT
    cache = Path("data/cards_beta.json")
    if not cache.exists():
        cache = Path("data/cards_beta.placeholder.json")
    session = build_session(
        decklist=decklist,
        cache_path=cache if cache.exists() else None,
        strategy_profile="YYG_Jackie",
        iterations=iterations,
        seed=seed,
    )
    for notice in session.notices:
        print(f"NOTE: {notice}\n")
    if session.parse and (session.parse.errors or session.parse.unknown):
        print(session.parse.render())
        return 1

    deck_a = session.deck
    profile = session.profile
    rules = session.config.rules
    policy = selected_policy(session)
    policies = [
        session.policies[name]
        for name in ("Jackie Aggressive", "Jackie or Draw", "Balanced YYG", "No Mulligan")
        if name in session.policies
    ]

    filler_card = session.database.require(FILLER)
    deck_b = deck_a.with_copies(TARGET, 3, filler_card)
    deck_b.name = "Build B — Jackie x3 (cut 1 non-sellable filler)"
    deck_a = deck_a.clone()
    deck_a.name = "Build A — Jackie x2"

    sellable_filler = session.database.require(SELLABLE_FILLER)
    deck_c = session.deck.with_copies(TARGET, 3, sellable_filler)
    deck_c.name = "Build C — Jackie x3 (cut 1 sellable filler)"

    _heading("FIRST DEMONSTRATION — sample 40-card deck")
    print(f"Legends: {', '.join(c.name for c in deck_a.legends)}")
    print(f"Playability profile: {profile.name}  [{profile.source}]")
    print(f"Mulligan profile:    {policy.name if policy else 'none'}")
    print(f"Simulation:          {iterations:,} iterations, seed {seed}")

    for deck in (deck_a, deck_b, deck_c):
        _heading(deck.name)
        summary = deck_summary.summarize(deck, profile, session.config, (TARGET,))
        status = summary.sell.status
        print(f"  Mechanical sellables:      {status.sellable_count}/{status.deck_size} "
              f"= {status.actual_pct:.1%}")
        print(f"  Effective sellable T1/T3:  "
              f"{summary.sell.effective[1].value:.1%} / {summary.sell.effective[3].value:.1%}")
        print(f"  Sellable status:           {status.status}")
        print(f"  Cards to minimum/target:   {status.cards_to_minimum} / {status.cards_to_target}")
        print("  Raw Jackie access:         "
              + "  ".join(
                  f"{k}:{r.value:.1%}"
                  for k, r in summary.target_access[TARGET].items()
              ))
        print("  Successful sells (exact):  "
              + "  ".join(
                  f"T{t}:{r.value:.2%}" for t, r in list(summary.sell.consecutive.items())[:3]
              ))
        print("  Dead-card burden T1/T2/T3: "
              + " / ".join(f"{summary.dead_burden[t].value:.1%}" for t in (1, 2, 3)))
        print("  Action density T1/T2/T3:   "
              + " / ".join(f"{summary.action_density[t].value:.1%}" for t in (1, 2, 3)))
        jackie_cost = deck.find(TARGET).card.cost or 0
        print(
            f"  Jackie AND >= {jackie_cost} sellables by T{TURN}: "
            f"{access.target_and_sellables(deck, TARGET, TURN, jackie_cost, rules).value:.2%}"
        )

    _heading(f"MULLIGAN POLICIES — turn {TURN} (SIMULATED)")
    rows = mulligan_analytics.compare_policies(
        deck_a, policies, (TARGET,), profile, rules,
        iterations=max(5_000, iterations // 10),
        opening_iterations=max(5_000, iterations // 5),
        seed=seed, max_turn=TURN, board_proxy=session.board_proxy,
    )
    print(mulligan_analytics.render_comparison(rows, TURN))
    print("\n  " + interpretation.mulligan_sentence(rows, TURN))

    reports = {}
    for deck in (deck_a, deck_b):
        _heading(f"TARGET REPORT — {deck.name}")
        report = target_analytics.target_report(
            deck, TARGET, TURN, profile, rules, policy,
            iterations=iterations, seed=seed, board_proxy=session.board_proxy,
        )
        reports[deck.name] = report
        print(report.render())

    _heading("CARD CONTRIBUTIONS (average extra draws per game, SIMULATED)")
    contributions = reports[deck_a.name].draws_by_source
    for name in (
        "Muamar Reyes — El Capitán",
        "Field Operator",
        "Memory Relapse",
        "Zetatech Faceplate",
    ):
        value = contributions.get(name)
        if value is None:
            print(f"  {name:<30} no draw contribution modelled "
                  "(no draw effect in the card metadata)")
        else:
            print(f"  {name:<30} {value:.3f} extra cards/game")
            print("      " + interpretation.draw_source_sentence(name, value))

    _heading("WHAT THE THIRD JACKIE COSTS AND BUYS")
    for variant in (deck_b, deck_c):
        comparison = marginal_value.compare_decks(deck_a, variant, TARGET, profile, rules)
        print(f"\n{variant.name}")
        for metric in (
            "target_access",
            "sell_consistency",
            "effective_sellable",
            "dead_burden",
            "action_density",
        ):
            deltas = comparison.deltas[metric]
            print(
                f"  {metric:<20} "
                + "  ".join(f"T{t}:{deltas[t] * 100:+.2f}pp" for t in (1, 2, 3))
            )
        print("  " + interpretation.copies_sentence(comparison, "Jackie Welles", TURN))

    played_a = reports[deck_a.name].played
    played_b = reports[deck_b.name].played
    delta = (played_b.value - played_a.value) * 100
    print(
        f"\n  Simulated P(Jackie played by T{TURN}): {played_a.formatted()} -> "
        f"{played_b.formatted()}  ({delta:+.2f} percentage points)"
    )
    if abs(delta) < 1.96 * 100 * (
        (played_a.standard_error or 0) ** 2 + (played_b.standard_error or 0) ** 2
    ) ** 0.5:
        print("  That difference is inside the combined 95% confidence interval — "
              "treat it as noise, not a finding.")

    _heading("HONEST LIMITS OF THIS DEMONSTRATION")
    for line in [
        "Card costs, sellable flags and effects come from the placeholder pool "
        "unless data/cards_beta.json holds official data.",
        "Playability and sell-willingness values are HEURISTIC — Human Estimate; "
        "they are assumptions you should replace after playtesting.",
        "Memory Relapse's draw depends on an opponent board state modelled by a "
        "proxy probability (HEURISTIC — Board-State Proxy), not by an opponent AI.",
        "Sell consistency from the exact math assumes full willingness to sell; "
        "the simulated figure is lower because the pilot also plays those cards.",
        "60%–65% sellable is a USER / PLAYTESTING HEURISTIC, not an official rule.",
    ]:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_demo())
