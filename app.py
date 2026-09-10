#!/usr/bin/env python3
"""Streamlit UI for the Cyberpunk TCG deck analyzer.

    streamlit run app.py

Every panel labels the method behind its numbers.  Exact math, Monte Carlo
simulation and heuristic estimates are never blended into one figure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from cyberpunk_deck_math import export
from cyberpunk_deck_math.analytics import (
    access,
    axioms,
    dead_cards,
    deck_summary,
    interpretation,
    marginal_value,
    mulligan_analytics,
    opportunity_density,
    playability,
    recommender,
    sell_density,
    sensitivity,
)
from cyberpunk_deck_math.analytics import target as target_analytics
from cyberpunk_deck_math.config import (
    DEFAULT_CARD_CACHE,
    AnalysisConfig,
    RuleConfig,
    SellableSettings,
    normalize_pct,
)
from cyberpunk_deck_math.database.cache import CardDatabase
from cyberpunk_deck_math.database.fetch_official import FetchError, update_cards
from cyberpunk_deck_math.database.placeholder import DISCLAIMER, SAMPLE_DECK_TEXT
from cyberpunk_deck_math.effects import interpreter
from cyberpunk_deck_math.llm import LLMUnavailable
from cyberpunk_deck_math.llm import available as llm_available
from cyberpunk_deck_math.probability import sells as sells_math
from cyberpunk_deck_math.probability.mulligan import (
    FEATURES,
    And,
    Condition,
    MulliganPolicy,
    Or,
    ScoreConfig,
    score_policy,
)
from cyberpunk_deck_math.session import (
    MULLIGAN_DIR,
    build_session,
    load_card_database,
    selected_policy,
)
from cyberpunk_deck_math.simulation.game import ITERATION_CHOICES
from cyberpunk_deck_math.simulation.pilot import PilotPolicy

st.set_page_config(page_title="Cyberpunk TCG deck math", layout="wide")

TABS = [
    "DECK",
    "OVERVIEW",
    "SELLS",
    "TARGET",
    "BOARD",
    "MULLIGAN",
    "SIMULATION",
    "COMPARE",
    "SENSITIVITY",
    "CARD RULES",
]


# ------------------------------------------------------------------- utilities


def pct_input(label: str, value: float, key: str) -> float:
    """Accept 60, 60%, or 0.60 and normalize to a fraction."""
    raw = st.text_input(label, value=f"{value * 100:g}%", key=key)
    try:
        return normalize_pct(raw)
    except ValueError as exc:
        st.warning(f"{label}: {exc}. Using {value:.1%}.")
        return value


def results_frame(curve: dict, label: str = "value") -> pd.DataFrame:
    rows = []
    for key, result in curve.items():
        row = {"turn": key, label: result.value, "method": result.method.value}
        if result.ci95:
            row["ci95_low"], row["ci95_high"] = result.ci95
        rows.append(row)
    return pd.DataFrame(rows)


def method_caption(*methods: str) -> None:
    st.caption(" · ".join(dict.fromkeys(methods)))


@st.cache_resource(show_spinner=False)
def cached_database(path: str, mtime: float) -> CardDatabase:
    database, _ = load_card_database(path)
    return database


def get_database(path: str) -> CardDatabase:
    p = Path(path)
    mtime = p.stat().st_mtime if p.exists() else 0.0
    return cached_database(path, mtime)


def current_session():
    return st.session_state.get("session")


# ------------------------------------------------------------------- sidebar


def sidebar() -> dict[str, Any]:
    st.sidebar.header("Card database")
    cache_path = st.sidebar.text_input("Card cache", value=str(DEFAULT_CARD_CACHE))
    source_url = st.sidebar.text_input(
        "Official JSON endpoint (optional)",
        help="Leave blank to try the known candidate endpoints for "
        "https://cyberpunktcg.com/cards.",
    )
    source_file = st.sidebar.text_input("…or a JSON export file (optional)")
    if st.sidebar.button("Update Card Database", width="stretch"):
        with st.spinner("Fetching the official Beta card database…"):
            try:
                _, report = update_cards(
                    cache_path=cache_path,
                    source_url=source_url or None,
                    source_file=source_file or None,
                )
                st.sidebar.success("Card database updated.")
                st.sidebar.code(report.render())
                cached_database.clear()
            except FetchError as exc:
                st.sidebar.error(str(exc))

    database = get_database(cache_path)
    st.sidebar.caption(
        f"{len(database)} cards · provenance: **{database.data_provenance}** · "
        f"updated {database.updated_at or 'unknown'}"
    )
    if database.data_provenance != "official":
        st.sidebar.warning(DISCLAIMER)

    st.sidebar.header("Sellable targets")
    st.sidebar.caption("USER / PLAYTESTING HEURISTIC — not an official rule.")
    minimum = pct_input("Minimum sellable %", 0.60, "min_sell")
    target = pct_input("Target sellable %", 0.625, "target_sell")
    range_min = pct_input("Target range min", 0.60, "range_min")
    range_max = pct_input("Target range max", 0.65, "range_max")

    st.sidebar.header("Rules")
    st.sidebar.caption("Changing a value marks it USER OVERRIDE in every export.")
    rules = RuleConfig()
    rules.opening_hand_size = st.sidebar.number_input(
        "Opening hand size", 1, 12, rules.opening_hand_size
    )
    rules.natural_draws_per_turn = st.sidebar.number_input(
        "Natural draws per turn", 0, 5, rules.natural_draws_per_turn
    )
    rules.max_sells_per_turn = st.sidebar.number_input(
        "Max sells per turn", 0, 5, rules.max_sells_per_turn
    )
    rules.eddie_value = st.sidebar.number_input("Eddie value per sell", 0, 5, rules.eddie_value)
    rules.legend_resource_value = st.sidebar.number_input(
        "Legend resource value", 0, 5, rules.legend_resource_value
    )
    rules.draw_on_first_turn = st.sidebar.checkbox(
        "Draw on turn 1", value=rules.draw_on_first_turn
    )
    overrides = rules.overrides()
    if overrides:
        st.sidebar.info("USER OVERRIDE: " + ", ".join(sorted(overrides)))

    st.sidebar.header("Profiles")
    profiles = playability.list_profiles()
    profile_name = st.sidebar.selectbox(
        "Playability profile", ["(cost-gated default)"] + profiles
    )
    max_turn = st.sidebar.slider("Turns to analyse", 3, 10, 6)

    return {
        "cache_path": cache_path,
        "database": database,
        "sellable": SellableSettings.build(minimum, target, range_min, range_max),
        "rules": rules,
        "profile_name": None if profile_name.startswith("(") else profile_name,
        "max_turn": max_turn,
    }


# ---------------------------------------------------------------------- tabs


def tab_deck(settings: dict[str, Any]) -> None:
    st.subheader("Decklist")
    st.caption(
        "Paste any supported format: `3x Card Name`, `3 Card Name`, collector "
        "numbers, card ids, `Legends`/`Main Deck` headings, `#` comments."
    )
    default = st.session_state.get("decklist", SAMPLE_DECK_TEXT)
    text = st.text_area("Decklist", value=default, height=380, key="decklist_input")
    columns = st.columns(3)
    ignore_legality = columns[0].checkbox("Ignore legality (testing)", key="deck_ignore")
    deck_name = columns[1].text_input("Deck name override", "", key="deck_name")
    strategies = sorted(p.stem for p in (Path("profiles/strategies")).glob("*.json"))
    strategy = columns[2].selectbox("Strategy profile", ["(none)"] + strategies, key="deck_strategy")

    if st.button("Parse and validate", type="primary", key="deck_parse"):
        session = build_session(
            decklist=text,
            cache_path=settings["cache_path"],
            minimum_sellable=settings["sellable"].minimum_pct,
            target_sellable=settings["sellable"].target_pct,
            target_sellable_min=settings["sellable"].target_range[0],
            target_sellable_max=settings["sellable"].target_range[1],
            playability_profile=settings["profile_name"],
            strategy_profile=None if strategy.startswith("(") else strategy,
            rules=settings["rules"],
            max_turn=settings["max_turn"],
            ignore_legality=ignore_legality,
            deck_name=deck_name or None,
        )
        st.session_state["session"] = session
        st.session_state["decklist"] = text

    session = current_session()
    if session is None:
        st.info("Parse a decklist to unlock the other tabs.")
        return

    parse = session.parse
    if parse.errors:
        for error in parse.errors:
            st.error(f"VALIDATION: {error}")
    else:
        st.success("Deck is legal for the configured rules.")
    for number, raw, reason in parse.unknown:
        st.error(f"UNKNOWN line {number}: `{raw}` — {reason}")
    for number, raw, candidates in parse.ambiguous:
        st.warning(f"AMBIGUOUS line {number}: `{raw}` — candidates: {', '.join(candidates)}")
    for warning in parse.warnings:
        st.warning(warning)

    st.subheader("Matched cards")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "copies": entry.copies,
                    "name": entry.card.name,
                    "card_id": entry.card.card_id,
                    "set": entry.card.set_code,
                    "type": entry.card.type,
                    "cost": entry.card.cost,
                    "sellable": entry.card.sellable,
                    "provenance": entry.card.data_provenance,
                }
                for entry in session.deck.main
            ]
        ),
        width="stretch",
    )
    st.write("**Legends:** " + ", ".join(c.name for c in session.deck.legends))


def tab_overview(settings: dict[str, Any]) -> None:
    session = current_session()
    if session is None:
        st.info("Parse a decklist first.")
        return
    summary = deck_summary.summarize(
        session.deck, session.profile, session.config,
        tuple(session.strategy.get("targets", ())),
    )
    status = summary.sell.status
    columns = st.columns(5)
    columns[0].metric("Deck size", status.deck_size)
    columns[1].metric("Mechanical sellables", f"{status.sellable_count} ({status.actual_pct:.1%})")
    if summary.sell.effective:
        columns[2].metric("Effective sellable T3", f"{summary.sell.effective[3].value:.1%}")
    columns[3].metric("Status", status.status)
    columns[4].metric(
        "Cards to min / target", f"{status.cards_to_minimum} / {status.cards_to_target}"
    )
    method_caption(
        "Sellable targets: USER / PLAYTESTING HEURISTIC",
        f"Playability: {summary.profile_source or 'n/a'}",
    )

    for warning in summary.warnings:
        (st.warning if warning.level == "warning" else st.info)(warning.message)

    left, right = st.columns(2)
    with left:
        st.subheader("Cost curve")
        st.bar_chart(pd.Series(summary.composition.cost_curve, name="copies"))
        st.subheader("Card types")
        st.bar_chart(pd.Series(summary.composition.card_types, name="copies"))
    with right:
        st.subheader("Action density & dead-card burden")
        if summary.action_density:
            frame = pd.DataFrame(
                {
                    "action density": {
                        t: r.value for t, r in summary.action_density.items()
                    },
                    "dead-card burden": {
                        t: r.value for t, r in summary.dead_burden.items()
                    },
                }
            )
            st.line_chart(frame)
            method_caption(summary.profile_source)
        st.subheader("Draw sources")
        st.json(
            {
                "draw sources": summary.composition.draw_sources,
                "conditional": summary.composition.conditional_draw_sources,
                "reactive": summary.composition.reactive_cards,
                "finishers": summary.composition.finishers,
            }
        )

    st.subheader("Conclusions")
    for line in interpretation.summary_conclusions(
        summary, tuple(session.strategy.get("targets", ())), 3
    ):
        st.markdown(f"- {line}")

    export_panel({"summary": summary.to_dict()}, session, "overview")


def tab_sells(settings: dict[str, Any]) -> None:
    session = current_session()
    if session is None:
        st.info("Parse a decklist first.")
        return
    deck = session.deck
    report = sell_density.sell_report(
        deck, session.config.sellable, session.config.rules,
        session.profile, session.config.max_turn,
    )
    st.markdown(interpretation.sellable_sentence(report.status))

    left, right = st.columns(2)
    with left:
        st.subheader("Consecutive sells")
        st.dataframe(results_frame(report.consecutive, "P(sell every turn through)"),
                     width="stretch")
        method_caption("EXACT — Hypergeometric")
    with right:
        st.subheader("Missed sells")
        st.dataframe(results_frame(report.misses, "P(miss at least one)"),
                     width="stretch")

    if report.effective:
        st.subheader("Effective sellable density")
        st.caption(
            "Mechanical sellables weighted by sell willingness — the part of your "
            "sellable count the pilot can actually give up."
        )
        frame = pd.DataFrame(
            {
                "mechanical": {t: deck.sellable_pct for t in report.effective},
                "effective": {t: r.value for t, r in report.effective.items()},
            }
        )
        st.line_chart(frame)
        method_caption(session.profile.source)

    st.subheader("Sellable density reference table")
    rows = sells_math.density_table(
        deck.size, max_turn=session.config.max_turn, rules=session.config.rules
    )
    table = pd.DataFrame(
        [
            {
                "sellables": row.sellables,
                "%": f"{row.pct:.1%}",
                **{f"T{t}": row.by_turn[t].value for t in row.by_turn},
                "current": row.sellables == deck.sellable_count,
            }
            for row in rows
        ]
    )
    st.dataframe(table, width="stretch")
    method_caption("EXACT — Hypergeometric")

    st.subheader("Compare sellable percentages")
    choices = st.multiselect(
        "Percentages",
        [0.55, 0.575, 0.60, 0.625, 0.65, 0.675],
        default=[0.575, 0.60, 0.625, 0.65],
        format_func=lambda p: f"{p:.1%}",
        key="sells_pcts",
    )
    counts = sorted({sell_density.counts_for_pcts(deck.size, choices)[p] for p in choices})
    if counts:
        curves = sells_math.sensitivity(
            deck.size, counts, session.config.max_turn, session.config.rules
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "sellables": count,
                        "%": f"{count / deck.size:.1%}",
                        **{f"T{t}": r.value for t, r in curve.items()},
                    }
                    for count, curve in curves.items()
                ]
            ),
            width="stretch",
        )

    st.subheader("Sell willingness assumptions")
    st.caption(
        "Sell willingness is not the same thing as being mechanically sellable. "
        "Edit these in profiles/playability/<name>.json."
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "card": entry.card.name,
                    "copies": entry.copies,
                    "sellable": entry.card.is_sellable,
                    **{
                        f"T{t}": session.profile.willingness(entry.card, t)
                        for t in range(1, 6)
                    },
                }
                for entry in deck.main
            ]
        ),
        width="stretch",
    )
    export_panel({"sells": report.to_dict()}, session, "sells")


def tab_target(settings: dict[str, Any]) -> None:
    session = current_session()
    if session is None:
        st.info("Parse a decklist first.")
        return
    deck = session.deck
    names = [entry.card.name for entry in deck.main]
    default_targets = list(session.strategy.get("targets", ()))
    index = names.index(default_targets[0]) if default_targets and default_targets[0] in names else 0
    columns = st.columns(4)
    target = columns[0].selectbox("Target card", names, index=index, key="target_card")
    turn = columns[1].number_input("Target turn", 1, session.config.max_turn, 3, key="target_turn")
    iterations = columns[2].selectbox("Iterations", ITERATION_CHOICES, index=0, key="target_iterations")
    policy_name = columns[3].selectbox(
        "Mulligan policy", ["(none)"] + sorted(session.policies), key="target_policy"
    )

    st.subheader("Raw access (exact)")
    st.dataframe(results_frame(access.access_curve(deck, target, session.config.max_turn,
                                                   session.config.rules), "P(seen)"),
                 width="stretch")
    method_caption("EXACT — Hypergeometric · natural draws only, no mulligan")

    st.subheader("Copies comparison")
    comparison_table = access.copies_comparison(
        deck.size, (1, 2, 3), session.config.max_turn, session.config.rules
    )
    st.dataframe(
        pd.DataFrame(
            [
                {"copies": copies, **{key: r.value for key, r in row.items()}}
                for copies, row in comparison_table.items()
            ]
        ),
        width="stretch",
    )

    st.subheader("2 vs 3 copies in this deck")
    filler_names = [n for n in names if n != target]
    filler = st.selectbox("Card to trade against", filler_names, key="target_filler")
    if st.button("Compare 2 vs 3 copies", key="target_compare_copies"):
        filler_card = deck.find(filler).card
        comparison = marginal_value.compare_copies(
            deck, target, filler_card, session.profile, (2, 3),
            session.config.rules, session.config.max_turn,
        )
        st.dataframe(comparison_frame(comparison, int(turn)), width="stretch")
        st.markdown(interpretation.copies_sentence(comparison, target, int(turn)))

    if st.button("Run layered target report", type="primary", key="target_run"):
        with st.spinner(f"Simulating {iterations:,} games…"):
            report = target_analytics.target_report(
                deck, target, int(turn), session.profile, session.config.rules,
                None if policy_name.startswith("(") else session.policies[policy_name],
                iterations, session.config.simulation_seed,
                board_proxy=session.board_proxy,
            )
        st.session_state["target_report"] = report
    report = st.session_state.get("target_report")
    if report is not None:
        st.subheader("Layers — never collapsed into one number")
        st.dataframe(
            pd.DataFrame(
                [
                    {"layer": name, "probability": result.value, "method": result.method.value,
                     "detail": result.detail}
                    for name, result in [
                        ("1. seen (exact, no mulligan)", report.seen),
                        ("2. seen (simulated, with mulligan)", report.seen_simulated),
                        ("3. in hand", report.in_hand),
                        ("4. affordable", report.affordable),
                        ("5. legally playable", report.legal),
                        ("6. strategically playable", report.strategic),
                        ("7. actually played", report.played),
                    ]
                ]
            ),
            width="stretch",
        )
        st.code(report.render())
        export_panel({"target": report.to_dict()}, session, "target")


def comparison_frame(comparison: marginal_value.Comparison, turn: int) -> pd.DataFrame:
    a, b = comparison.a, comparison.b
    rows = [
        ("mechanical sellable %", a.sellable_pct, b.sellable_pct),
        ("effective sellable", a.effective_sellable[turn], b.effective_sellable[turn]),
        ("target access", a.target_access[turn], b.target_access[turn]),
        ("sell consistency", a.sell_consistency[turn], b.sell_consistency[turn]),
        ("dead-card burden", a.dead_burden[turn], b.dead_burden[turn]),
        ("action density", a.action_density[turn], b.action_density[turn]),
        ("target + resources", a.target_and_resources[turn], b.target_and_resources[turn]),
    ]
    return pd.DataFrame(
        [
            {"metric": f"{label} T{turn}", a.name: left, b.name: right,
             "delta (pp)": (right - left) * 100}
            for label, left, right in rows
        ]
    )


def tab_board(settings: dict[str, Any]) -> None:
    session = current_session()
    if session is None:
        st.info("Parse a decklist first.")
        return
    profile = session.profile
    st.subheader("Playability assumptions")
    st.caption(
        "LEGAL playability: could you play it. STRATEGIC playability: should you. "
        "Both are per-strategy assumptions, never facts."
    )
    rows = []
    for entry in session.deck.main:
        card = entry.card
        rows.append(
            {
                "card": card.name,
                "copies": entry.copies,
                "cost": card.cost,
                **{f"legal T{t}": profile.legal_playability(card, t) for t in range(1, 7)},
                **{f"strategic T{t}": profile.strategic_playability(card, t) for t in range(1, 7)},
                "confidence": profile.confidence.get(card.key, ""),
                "source": profile.source,
            }
        )
    edited = st.data_editor(pd.DataFrame(rows), width="stretch", key="playability_editor")
    if st.button("Apply edited playability values", key="board_apply"):
        for _, row in edited.iterrows():
            entry = session.deck.find(row["card"])
            if entry is None:
                continue
            playability.set_estimate(
                profile, entry.card,
                {t: float(row[f"legal T{t}"]) for t in range(1, 7)}, "legal",
            )
            playability.set_estimate(
                profile, entry.card,
                {t: float(row[f"strategic T{t}"]) for t in range(1, 7)}, "strategic",
                confidence="human-edited",
                rationale="Edited in the BOARD tab.",
            )
        st.success("Applied. Save the profile below to keep the changes.")
    columns = st.columns(2)
    profile_name = columns[0].text_input("Profile name", profile.name, key="board_profile_name")
    if columns[1].button("Save profile to profiles/playability/", key="board_save_profile"):
        profile.name = profile_name
        path = playability.save_profile(profile)
        st.success(f"Saved {path}")

    st.subheader("Reactive-card / opponent-state proxies")
    st.caption(
        "HEURISTIC — Board-State Proxy. These probabilities stand in for an "
        "opponent model; any result that uses them is labelled heuristic."
    )
    proxy = session.board_proxy
    proxy_rows = []
    for key, table in proxy.probabilities.items():
        proxy_rows.append({"condition": key, **{f"T{t}": proxy.probability(key, t) for t in range(1, 7)}})
    edited_proxy = st.data_editor(pd.DataFrame(proxy_rows), width="stretch",
                                  key="proxy_editor")
    if st.button("Apply proxy values", key="board_apply_proxy"):
        for _, row in edited_proxy.iterrows():
            proxy.probabilities[row["condition"]] = {
                t: float(row[f"T{t}"]) for t in range(1, 7)
            }
        st.success("Proxy updated for this session.")

    st.subheader("LLM-assisted playability estimate")
    if not llm_available():
        st.info(
            "No Anthropic credentials detected. Enter estimates by hand above, or "
            "run `ant auth login` / set ANTHROPIC_API_KEY to enable proposals."
        )
    else:
        card_name = st.selectbox(
            "Card", [e.card.name for e in session.deck.main], key="llm_playability_card"
        )
        strategy_text = st.text_area(
            "Strategy description", session.strategy.get("description", ""),
            key="board_strategy_text",
        )
        if st.button("Propose playability (HEURISTIC — LLM ESTIMATE)", key="board_propose"):
            entry = session.deck.find(card_name)
            try:
                with st.spinner("Asking Claude…"):
                    proposal = playability.propose_playability(
                        entry.card, session.deck, strategy_text
                    )
                st.session_state["playability_proposal"] = proposal
            except (LLMUnavailable, ValueError) as exc:
                st.error(str(exc))
        proposal = st.session_state.get("playability_proposal")
        if proposal is not None:
            st.warning("HEURISTIC — LLM ESTIMATE. Nothing is applied until you accept it.")
            st.json(proposal.to_dict())
            if st.button("Accept into the profile", key="board_accept"):
                playability.apply_proposal(profile, proposal)
                st.success("Applied as an LLM estimate. Verify it before trusting it.")


def tab_mulligan(settings: dict[str, Any]) -> None:
    session = current_session()
    if session is None:
        st.info("Parse a decklist first.")
        return
    st.subheader("Saved profiles")
    names = st.multiselect(
        "Policies to compare",
        sorted(session.policies),
        default=[n for n in ("No Mulligan", "Target or Draw", "2+ Sellables") if n in session.policies],
        key="mull_policies",
    )
    targets = st.multiselect(
        "Target cards",
        [e.card.name for e in session.deck.main],
        default=list(session.strategy.get("targets", ())),
        key="mull_targets",
    )

    with st.expander("Build a rule-based policy"):
        st.caption("Combine conditions with AND / OR. Saved to profiles/mulligan/.")
        name = st.text_input("Policy name", "My Policy", key="mull_name")
        combiner = st.radio("Combine with", ["AND", "OR"], horizontal=True, key="mull_combiner")
        conditions = []
        for index in range(3):
            columns = st.columns([3, 2, 2, 1])
            feature = columns[0].selectbox(
                f"Feature {index + 1}", ["(unused)"] + list(FEATURES), key=f"feat{index}"
            )
            operator = columns[1].selectbox(
                "Operator", [">=", ">", "==", "<=", "<", "!="], key=f"op{index}"
            )
            value = columns[2].number_input("Value", value=1.0, step=0.5, key=f"val{index}")
            columns[3].write("")
            if not feature.startswith("("):
                conditions.append(Condition(feature, operator, value))
        keep_node = (And(conditions) if combiner == "AND" else Or(conditions)) if conditions else None
        if keep_node is not None:
            st.code(f"KEEP IF {keep_node.describe()}")
        if st.button("Save policy", key="mull_save") and keep_node is not None:
            policy = MulliganPolicy(name=name, keep=keep_node)
            MULLIGAN_DIR.mkdir(parents=True, exist_ok=True)
            path = MULLIGAN_DIR / f"{name.lower().replace(' ', '_')}.json"
            path.write_text(json.dumps(policy.to_dict(), indent=2), encoding="utf-8")
            session.policies[name] = policy
            st.success(f"Saved {path}")

    with st.expander("Score-based policy"):
        threshold = st.number_input("Keep if hand score >=", value=6.0, step=0.5, key="mull_threshold")
        st.caption("Card scores are edited in profiles/mulligan/*.json.")
        base = st.selectbox(
            "Score config to reuse",
            [n for n, p in session.policies.items() if p.score_config],
            index=0 if any(p.score_config for p in session.policies.values()) else None,
            key="mull_score_base",
        ) if any(p.score_config for p in session.policies.values()) else None
        if base and st.button("Add score policy to the comparison", key="mull_add_score"):
            config = session.policies[base].score_config
            policy = score_policy(f"Score >= {threshold:g}", threshold, config)
            session.policies[policy.name] = policy
            st.success(f"Added {policy.name}")

    columns = st.columns(3)
    iterations = columns[0].selectbox("Simulated games per policy", [5_000, 10_000, 20_000, 50_000], key="mull_iterations")
    turn = columns[1].number_input("Report turn", 1, session.config.max_turn, 3, key="mull_turn")
    seed = columns[2].number_input("Seed", value=session.config.simulation_seed or 0, key="mull_seed")

    if st.button("Compare policies", type="primary", key="mull_compare") and names and targets:
        with st.spinner("Simulating…"):
            rows = mulligan_analytics.compare_policies(
                session.deck, [session.policies[n] for n in names], targets,
                session.profile, session.config.rules, int(iterations),
                seed=int(seed), max_turn=int(turn), board_proxy=session.board_proxy,
            )
        st.session_state["mulligan_rows"] = rows
    rows = st.session_state.get("mulligan_rows")
    if rows:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "policy": row.policy,
                        "mulligan %": row.mulligan_rate,
                        f"target seen T{turn}": row.target_by_turn[int(turn)].value,
                        f"sell through T{turn}": row.sells_through[int(turn)].value,
                        f"target played T{turn}": row.target_played[int(turn)].value,
                        "good hand %": row.good_hand_rate,
                        "avg sellables kept": row.average_sellables,
                    }
                    for row in rows
                ]
            ),
            width="stretch",
        )
        method_caption("SIMULATED — Monte Carlo")
        st.markdown(interpretation.mulligan_sentence(rows, int(turn)))
        export_panel({"mulligan": [r.to_dict() for r in rows]}, session, "mulligan")


def tab_simulation(settings: dict[str, Any]) -> None:
    session = current_session()
    if session is None:
        st.info("Parse a decklist first.")
        return
    from cyberpunk_deck_math.simulation.game import simulate

    columns = st.columns(4)
    iterations = columns[0].selectbox("Iterations", ITERATION_CHOICES, index=0, key="sim_iterations")
    seed = columns[1].number_input("Seed", value=session.config.simulation_seed or 0, key="sim_seed")
    turns = columns[2].number_input("Turns", 1, 12, session.config.max_turn, key="sim_turns")
    policy_name = columns[3].selectbox("Mulligan policy", ["(none)"] + sorted(session.policies), key="sim_policy")
    targets = st.multiselect(
        "Target cards",
        [e.card.name for e in session.deck.main],
        default=list(session.strategy.get("targets", ())),
        key="sim_targets",
    )
    st.caption(
        "Large runs are slow but exact-ish: 500,000 iterations takes a few minutes. "
        "The 95% confidence interval tells you when a difference is real."
    )
    if st.button("Run simulation", type="primary", key="sim_run"):
        pilot = PilotPolicy(
            target_names=tuple(targets),
            profile=session.profile,
            mulligan=None if policy_name.startswith("(") else session.policies[policy_name],
        )
        with st.spinner(f"Simulating {iterations:,} games…"):
            summary = simulate(
                session.deck, pilot, session.config.rules, int(iterations), int(seed),
                int(turns), profile=session.profile, board_proxy=session.board_proxy,
            )
        st.session_state["simulation"] = summary
    summary = st.session_state.get("simulation")
    if summary is None:
        return
    st.metric("Mulligan rate", f"{summary.mulligans / summary.iterations:.1%}")
    frames = []
    for key in ("target_seen", "target_in_hand", "target_affordable", "target_legal",
                "target_strategic", "target_played", "sold_this_turn", "sells_through"):
        for turn in range(1, summary.max_turn + 1):
            result = summary.rate(key, turn)
            frames.append(
                {
                    "metric": key,
                    "turn": turn,
                    "probability": result.value,
                    "std error": result.standard_error,
                    "ci95 low": result.ci95[0],
                    "ci95 high": result.ci95[1],
                    "n": result.sample_size,
                }
            )
    st.dataframe(pd.DataFrame(frames), width="stretch")
    st.subheader("Averages per turn")
    st.dataframe(
        pd.DataFrame(
            {
                key: [summary.average(key, t).value for t in range(1, summary.max_turn + 1)]
                for key in summary.totals
            },
            index=[f"T{t}" for t in range(1, summary.max_turn + 1)],
        ),
        width="stretch",
    )
    st.subheader("Average draws per game by source")
    st.dataframe(
        pd.DataFrame(
            [
                {"source": k, "draws per game": v / summary.iterations}
                for k, v in sorted(summary.draws_by_source.items(), key=lambda kv: -kv[1])
            ]
        ),
        width="stretch",
    )
    st.json(summary.assumptions)
    export_panel({"simulation": summary.to_dict()}, session, "simulation")


def tab_compare(settings: dict[str, Any]) -> None:
    session = current_session()
    if session is None:
        st.info("Parse a decklist first.")
        return
    st.caption("Variant A is the parsed deck. Paste Variant B below.")
    text_b = st.text_area("Variant B decklist", value=st.session_state.get("decklist", ""), height=260, key="cmp_text")
    columns = st.columns(2)
    targets = list(session.strategy.get("targets", ())) or [session.deck.main[0].card.name]
    target = columns[0].selectbox("Target card", [e.card.name for e in session.deck.main],
                                  index=[e.card.name for e in session.deck.main].index(targets[0])
                                  if targets[0] in [e.card.name for e in session.deck.main] else 0,
                                  key="cmp_target")
    turn = columns[1].number_input("Turn", 1, session.config.max_turn, 3, key="cmp_turn")
    if st.button("Compare", type="primary", key="cmp_run"):
        session_b = build_session(
            decklist=text_b,
            cache_path=settings["cache_path"],
            playability_profile=(
                session.profile.name
                if session.profile and session.profile.name in playability.list_profiles()
                else None
            ),
            rules=session.config.rules,
            ignore_legality=True,
        )
        comparison = marginal_value.compare_decks(
            session.deck, session_b.deck, target, session.profile,
            session.config.rules, session.config.max_turn,
        )
        st.dataframe(comparison_frame(comparison, int(turn)), width="stretch")
        for note in comparison.notes:
            st.warning(note)
        st.markdown(interpretation.comparison_sentence(comparison, int(turn)))
        export_panel({"comparison": comparison.to_dict()}, session, "compare")


def tab_sensitivity(settings: dict[str, Any]) -> None:
    session = current_session()
    if session is None:
        st.info("Parse a decklist first.")
        return
    st.caption(
        "Any uncertain assumption can be swept. A conclusion that moves more than "
        "5 percentage points across the range is flagged as material."
    )
    choice = st.selectbox(
        "Assumption",
        ["sellable density", "strategic playability of a card", "target copies"],
        key="sens_choice",
    )
    turn = st.number_input("Turn", 1, session.config.max_turn, 3, key="sens_turn")
    runs = []
    if choice == "sellable density":
        pcts = st.multiselect(
            "Percentages", [0.55, 0.575, 0.60, 0.625, 0.65, 0.675],
            default=[0.575, 0.60, 0.625, 0.65], format_func=lambda p: f"{p:.1%}",
            key="sens_pcts",
        )
        if pcts:
            runs.append(sensitivity.sweep_sellable_target(
                session.deck, pcts, int(turn), session.config.rules))
    elif choice == "strategic playability of a card":
        card = st.selectbox("Card", [e.card.name for e in session.deck.main], key="sens_card")
        values = st.multiselect(
            "Values", [0.0, 0.05, 0.10, 0.20, 0.30, 0.50],
            default=[0.0, 0.05, 0.10, 0.20, 0.30], key="sens_values",
        )
        if values:
            runs.append(sensitivity.sweep_strategic_playability(
                session.deck, session.profile, card, int(turn), values))
            runs.append(sensitivity.sweep_strategic_playability(
                session.deck, session.profile, card, int(turn), values, metric="dead_burden"))
    else:
        card = st.selectbox("Card", [e.card.name for e in session.deck.main], key="sens_copies_card")
        filler = st.selectbox(
            "Trade against", [e.card.name for e in session.deck.main if e.card.name != card],
            key="sens_copies_filler",
        )
        counts = st.multiselect("Copies", [0, 1, 2, 3], default=[1, 2, 3], key="sens_copies")
        if counts:
            runs.append(sensitivity.sweep_copies(
                session.deck, card, session.deck.find(filler).card, counts,
                int(turn), session.config.rules))

    for run in runs:
        st.subheader(f"{run.assumption} → {run.metric}")
        st.line_chart(pd.DataFrame({run.metric: run.outcomes}, index=run.values))
        st.caption(f"{run.method.value} · spread {run.spread:.2%}")
        (st.warning if run.material else st.info)(run.to_dict()["verdict"])
    if runs:
        export_panel({"sensitivity": [r.to_dict() for r in runs]}, session, "sensitivity")


def tab_card_rules(settings: dict[str, Any]) -> None:
    session = current_session()
    database = settings["database"]
    cards = [e.card for e in session.deck.main] + list(session.deck.legends) if session else list(database)
    if not cards:
        st.info("No cards to show.")
        return
    names = sorted({c.name for c in cards})
    name = st.selectbox("Card", names, key="rules_card")
    card = next(c for c in cards if c.name == name)

    left, right = st.columns(2)
    with left:
        st.subheader("Official card text")
        st.caption(f"Provenance: {card.data_provenance} · source: {card.source_url or 'unknown'}")
        if card.rules_text:
            st.code(card.rules_text)
        else:
            st.warning(
                "No official rules text cached for this card. Run the card-database "
                "update, or enter the interpretation by hand."
            )
        st.json({k: v for k, v in card.to_dict().items()
                 if k in ("card_id", "set_code", "type", "cost", "ram", "sellable", "tags")})
    with right:
        st.subheader("Structured interpretation")
        st.metric("Interpretation status", card.interpretation_status)
        st.json(card.effect_metadata or [])
        if card.interpretation_notes:
            st.caption(card.interpretation_notes)

    st.subheader("Edit / propose")
    manual = st.text_area(
        "Effect metadata (JSON list)", value=json.dumps(card.effect_metadata or [], indent=2),
        height=200, key="rules_metadata",
    )
    columns = st.columns(3)
    if columns[0].button("Save as human-entered", key="rules_save_human"):
        try:
            interpreter.set_human_interpretation(card, json.loads(manual))
            st.success("Saved as human_verified for this session.")
        except (ValueError, json.JSONDecodeError) as exc:
            st.error(str(exc))
    if columns[1].button("Propose with Claude", disabled=not llm_available(), key="rules_propose"):
        try:
            with st.spinner("Asking Claude…"):
                proposal = interpreter.propose_interpretation(card)
            st.session_state["rule_proposal"] = proposal
        except (LLMUnavailable, ValueError) as exc:
            st.error(str(exc))
    if columns[2].button("Mark human-verified", key="rules_verify"):
        try:
            interpreter.verify_interpretation(card)
            st.success("Marked human_verified.")
        except ValueError as exc:
            st.error(str(exc))
    proposal = st.session_state.get("rule_proposal")
    if proposal:
        st.warning("LLM PROPOSAL — not authoritative until you verify it.")
        st.json(proposal)
        if st.button("Attach proposal as llm_proposed", key="rules_attach"):
            interpreter.attach_proposal(card, proposal)
            st.success("Attached. Status is llm_proposed until a human verifies it.")

    st.subheader("Interpretation status across the deck")
    st.json(interpreter.interpretation_report(cards))
    if st.button("Save card database changes to the cache", key="rules_save_cache"):
        path = database.save(settings["cache_path"])
        st.success(f"Saved {path}")


def export_panel(payload: dict[str, Any], session, name: str) -> None:
    with st.expander("Export (JSON / CSV / Markdown, with all assumptions)"):
        full = dict(payload)
        full["metadata"] = export.analysis_metadata(
            session.deck, session.config, session.database,
            mulligan_profile=session.strategy.get("mulligan_profile", ""),
            playability_profile=session.profile.name if session.profile else "",
        )
        columns = st.columns(3)
        columns[0].download_button("JSON", export.to_json(full), f"{name}.json", "application/json")
        columns[1].download_button("CSV", export.to_csv(full), f"{name}.csv", "text/csv")
        columns[2].download_button("Markdown", export.to_markdown(full), f"{name}.md", "text/markdown")


def main() -> None:
    st.title("Cyberpunk TCG deck math")
    st.caption(
        "Exact hypergeometric math, Monte Carlo simulation and clearly-labelled "
        "heuristics — kept apart on purpose."
    )
    settings = sidebar()
    tabs = st.tabs(TABS)
    handlers = [
        tab_deck, tab_overview, tab_sells, tab_target, tab_board,
        tab_mulligan, tab_simulation, tab_compare, tab_sensitivity, tab_card_rules,
    ]
    for tab, handler in zip(tabs, handlers):
        with tab:
            handler(settings)


if __name__ == "__main__":
    main()
