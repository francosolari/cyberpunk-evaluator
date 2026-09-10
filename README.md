# Cyberpunk TCG deck math

A local tool for improving Cyberpunk TCG constructed decks with exact probability
math, Monte Carlo simulation, configurable gameplay assumptions, deck-slot
comparison and board-state proxies.

It exists to answer one question — **what is the most valuable use of the next
deck slot?** — and it refuses to answer it with a single blended number.

## The five things this tool never collapses into one metric

| Layer | Question | How it is computed |
| --- | --- | --- |
| 1. Raw card access | Have I *seen* the card? | `EXACT — Hypergeometric` |
| 2. Resource access | Do I have the eddies/Legends to pay? | `EXACT` or `SIMULATED` |
| 3. Legal playability | *Could* I play it? | Simulated affordability × a playability profile |
| 4. Strategic playability | *Should* I play it? | Playability profile (`HEURISTIC`) |
| 5. Actual pilot decision | Did the simulated pilot play it? | `SIMULATED — Monte Carlo` |

Every number printed anywhere carries the label of the method that produced it:

```
EXACT — Hypergeometric        EXACT — Multivariate Hypergeometric
SIMULATED — Monte Carlo       HEURISTIC — Human Estimate
HEURISTIC — LLM Estimate      HEURISTIC — Board-State Proxy
USER / PLAYTESTING HEURISTIC
```

Heuristic values are printed with less precision on purpose: a proxy assumption
does not deserve four significant figures.

---

## Installation

```bash
git clone <this repo>
cd cyberpunk-evaluator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # core analysis needs no third-party packages
```

Python 3.10+. The probability engine is pure standard library (`math.comb` and
`fractions.Fraction`), so exact results are computed as exact rationals and only
converted to floats at the end. `streamlit` and `pandas` are needed only for the
UI; `anthropic` only for the optional LLM-assisted workflows; `pytest` only for
the tests.

Nothing needs the network except the card-database update.

---

## Quick start

```bash
# 1. Get card data. With network access to the official database:
python cli.py update-cards

#    Without it, write the offline placeholder pool and a sample decklist:
python cli.py init-placeholder

# 2. Analyse a deck
python cli.py analyze data/sample_deck_jackie.txt \
    --strategy YYG_Jackie \
    --cards data/cards_beta.placeholder.json \
    --target "Jackie Welles — Ride or Die Choom" --turn 3

# 3. Or open the UI
streamlit run app.py

# 4. Or run the worked example from section 39 of the spec
python demo.py
```

---

## Card database

The **official Cyberpunk TCG card database** (<https://cyberpunktcg.com/cards>)
is the authoritative source. `update-cards` fetches it, restricts the result to
**released Beta cards and Beta starter-deck exclusives**, normalizes the records
and writes a local cache. Preview-only, unreleased, future-set, fan-made and
speculative cards are dropped, and each drop is reported.

```bash
python cli.py update-cards                                   # try the known endpoints
python cli.py update-cards --source-url https://…/api/cards  # explicit endpoint
python cli.py update-cards --source-file cards_export.json   # a file you exported
export CYBERPUNK_TCG_CARDS_URL=https://…/api/cards           # or configure it once
```

The site's JSON endpoint is **configured, not guessed**. If none of the
candidate endpoints respond, the command fails with instructions rather than
inventing data. Normalization is alias-driven, so a change in the source's field
names is a one-line edit in `database/normalize.py` rather than a rewrite.

Cached fields: `card_id, name, collector_number, set_code, set_name,
starter_exclusive, type, subtype, color, cost, ram, sellable, rules_text,
flavor_text, tags, effect_metadata, source_url, database_updated_at`.

**A field the source does not provide stays `null`. The tool never invents a
value.** Official card text is stored verbatim and is always displayed beside any
structured interpretation of it.

Human-verified rule interpretations survive a database refresh: `update-cards`
carries them across automatically.

### The placeholder pool

`python cli.py init-placeholder` writes `data/cards_beta.placeholder.json` so the
application, tests and demo run with no network access. Those cards are marked
`data_provenance: "placeholder"`, their `rules_text` is `null`, and every deck
containing them raises a warning in the dashboard. Their costs, sellable flags
and effects are *assumptions made to exercise the model*, not claims about the
real cards. Replace them with `update-cards` before trusting any conclusion.

---

## Deck import

Plain text, in any of these shapes, mixed freely:

```
Name: YYG Jackie              Legends:                  Main Deck
                              Muamar Reyes — El Capitán 1x 106 Alt Cunningham — Soulkiller Architect
Legends                       Legend Two                3x 065 Afterparty at Lizzie's
1x Muamar Reyes — El Capitán  Legend Three
                                                        3x A027
Main Deck                     Main Deck:                1x MS01-131
2x Jackie Welles — Ride…      2 Field Operator          2x Field Operator (MS01)
3x Zetatech Faceplate         3 Zetatech Faceplate      # comments are ignored
```

The parser handles `3x Name`, `3 Name`, `x3 Name`, collector numbers, card ids,
set-qualified ids, trailing `(MS01)` set codes, `Legends` / `Main Deck`
headings, `#` comments, blank lines, and every dash variant (em `—`, en `–`,
non-breaking `‑`, plain `-`).

**Unknown lines are never silently ignored.** Parsing returns parsed cards,
warnings, ambiguous matches (with candidates), unknown cards (with the reason),
and validation errors — exactly 3 Legends, a 40–50 card main deck, at most 3
copies of a card, all cards inside the cached Beta pool. `--ignore-legality`
(CLI) / "Ignore legality" (UI) lets you analyse an illegal pile for testing.

---

## Rules configuration

All gameplay constants live in `cyberpunk_deck_math/config.py` and nowhere else:

```
MAIN_DECK_MIN = 40      OPENING_HAND_SIZE = 6         EDDIE_VALUE = 1
MAIN_DECK_MAX = 50      NATURAL_DRAWS_PER_TURN = 1    LEGEND_RESOURCE_VALUE = 1
LEGEND_COUNT = 3        MAX_SELLS_PER_TURN = 1        MAX_LEGEND_CALLS_PER_TURN = 1
MAX_CARD_COPIES = 3
```

Override any of them for experimentation. Anything you change is reported as
`USER OVERRIDE` instead of `OFFICIAL RULE`, in the CLI (`python cli.py rules`),
in the UI sidebar, and in every export:

```bash
python cli.py analyze deck.txt --opening-hand-size 7 --sells-per-turn 2
```

---

## Sellable density

Sellable density is treated as a first-class deckbuilding variable with three
separate settings, all configurable per deck and per analysis:

| Setting | Default | Meaning |
| --- | --- | --- |
| Minimum sellable % | 60% | the lowest you consider acceptable for this deck |
| Target sellable % | 62.5% | what you are building toward |
| Target range | 60–65% | the band you are happy inside |

**These defaults come from constructed playtesting. They are labelled
`USER / PLAYTESTING HEURISTIC`, not an official rule, and they are not derived
from sealed-format guidance.**

`60`, `60%` and `0.60` all normalize to `0.60`.

```bash
python cli.py analyze deck.txt --minimum-sellable 0.60 --target-sellable 0.625
python cli.py analyze deck.txt --target-sellable-min 0.60 --target-sellable-max 0.65
```

Status is one of `BELOW MINIMUM`, `BELOW TARGET`, `IN TARGET RANGE`,
`ABOVE TARGET RANGE`, with the exact number of cards needed to reach the minimum
and the target. For a 40-card deck: 24 sellables = 60%, 25 = 62.5%, 26 = 65%.
For 41–50 card decks the equivalent counts are computed dynamically.

### Sell consistency is sequential

`P(sell every turn through T)` is **not** `P(draw at least T sellables by turn T)`.
Selling is sequential — a hand that finds three sellables on turn 3 cannot
retroactively sell on turn 1 — so the tool computes the sequential version
exactly, with a dynamic program over the draw order, and reports the weaker
"at least k" form separately so you can see the difference.

```bash
python cli.py sells deck.txt --through-turn 3
```

prints the consecutive-sell curve, the miss curve, the full density reference
table (50%–70% of your actual deck size), and a side-by-side of 55 / 57.5 / 60 /
62.5 / 65 / 67.5% so you can judge whether a percentage point is worth a slot.

### Sell willingness and effective sellable density

Mechanically sellable is not the same thing as *willing to sell*. Every card has
a per-turn sell-willingness score in its playability profile:

```
1.00 almost always willing   0.50 neutral       0.00 never sell for this strategy
0.75 generally willing       0.25 prefer to keep
```

Effective sellable density weights the mechanical count by willingness:

```
effective_sellable_density(turn) = Σ sellable(c) · willingness(c, turn) · copies(c) / deck_size
```

A deck can be 62.5% sellable on paper and 46% sellable in practice — that gap is
the part of your resource base you cannot comfortably give up.

---

## Mulligan rules

A mulligan policy is **data**, not code: a boolean expression over hand features
with `AND` / `OR` / `NOT` and arbitrary nesting, optionally driven by a numeric
hand score. Build them from dropdowns in the MULLIGAN tab, or save JSON under
`profiles/mulligan/`:

```json
{
  "name": "Balanced YYG",
  "keep": {"all": [
    {"feature": "sellables", "operator": ">=", "value": 2},
    {"any": [
      {"feature": "target", "operator": ">=", "value": 1},
      {"feature": "early_draw_sources", "operator": ">=", "value": 1},
      {"feature": "early_playables", "operator": ">=", "value": 2}
    ]}
  ]}
}
```

Available features: `hand_size, sellables, effective_sellables, target,
draw_sources, early_draw_sources, early_playables, cards_cost_4_plus,
average_cost, sellable_pct, dead_cards, distinct_names, score`.

Built-in policies include `No Mulligan`, `Target Only`, `Target or Draw`,
`2+ Sellables`, `Sell Stability`, `Balanced`, `Draw Engine Priority`
("mulligan if no draw source **and** no target"), `Low Curve`, `No Early Play`.

### Score-based mulligans

```json
{"name": "Jackie Score Based",
 "keep": {"feature": "score", "operator": ">=", "value": 7},
 "score": {
   "card_scores": {"Jackie Welles — Ride or Die Choom": 3, "Field Operator": 2,
                   "Memory Relapse": -1},
   "sellable_score": 1,
   "interactions": [
     {"when": {"feature": "sellables", "operator": ">=", "value": 2}, "points": 2},
     {"when": {"feature": "sellables", "operator": "==", "value": 0}, "points": -3}
   ]}}
```

### Comparing policies

```bash
python cli.py mulligan deck.txt --strategy YYG_Jackie --turn 3
```

```
Strategy                  Mull %   Target T3   Sell thru T3  Played T3  Good hand  Avg sell
No Mulligan                0.0%       41.6%          87.5%       4.8%      48.2%      3.74
Jackie Aggressive         72.7%       56.4%          90.5%       6.9%      61.3%      3.61
Jackie or Draw            50.6%       52.2%          92.3%       6.0%      72.3%      3.70
```

Both axes are always shown: a policy that buys target access by wrecking
resource consistency has to look like a tradeoff, not like an improvement.

---

## Card effects and rule interpretation

Card behaviour is generic JSON metadata, not one Python module per card:

```json
{"trigger": "on_play", "effect": "draw", "amount": 1,
 "conditions": [{"type": "street_cred_parity", "value": "even"}]}
```

Triggers: `on_play, on_call, on_spend, on_reveal, on_trash, on_score, on_attack,
on_damage, start_phase, main_phase, conditional`.
Effects: `draw, gain_resource, adjust_gig, gain_street_cred, trash,
return_to_hand, search, reveal, discount, ready, spend`.
Conditions: `turn, street_cred, street_cred_parity, distinct_gigs, gig_count,
resource_available, friendly_unit_count, enemy_unit_count, card_type_in_play,
card_in_hand, legend_face_up, opponent_state_proxy`.

A condition whose context is unknown evaluates to "cannot determine", never
silently to true. Anything the vocabulary cannot express is reported as
unrepresentable rather than approximated. Bespoke Python for a card is the last
resort, after: official text → generic metadata → human/LLM interpretation →
playability proxy → explicit simulation.

### The three interpretation modes

| Mode | How | Status stored |
| --- | --- | --- |
| A — human entered | you write the metadata | `human_verified` |
| B — LLM assisted | Claude proposes it from the official text | `llm_proposed` |
| C — human verified | you review and approve a proposal | `human_verified` |

**An LLM interpretation can never silently become authoritative.** It lands as
`llm_proposed` and stays there until a human verifies it, the original card text
is always shown beside it, and the proposal records its own confidence,
rationale, and the parts of the text it could not represent.

The LLM workflows are optional; every one of them has a manual equivalent, and
the tool is fully usable with no API key.

---

## Playability profiles

Some card usefulness cannot be read off the card. Profiles live in
`profiles/playability/<strategy>.json` and store, per card and per turn:

* **legal playability** — given it is in hand, in what fraction of realistic
  states is playing it legal?
* **strategic playability** — in what fraction is playing it *correct*?
* **sell willingness** — how happy is the pilot to sell it?

Cards do not have one universal strategic-playability number: the same card is a
different card in a different deck, so profiles are per strategy.

Values can come from three places, and each is labelled:

* **A. Human estimate** — you type it (`HEURISTIC — Human Estimate`).
* **B. LLM-assisted** — Claude sees the official text, cost, type, deck
  composition, target strategy, typical resources by turn and expected board
  state, and proposes curves with a confidence, a rationale and its assumptions
  (`HEURISTIC — LLM Estimate`).
* **C. Simulation-derived** — the observed frequency once the simulator models
  the relevant condition (`SIMULATED`).

There is a feedback loop: after playtesting, `record_playtest_feedback` (or the
BOARD tab's editor) updates a single turn's value and marks it `playtested`.

> **A caveat worth knowing.** The simulator models affordability exactly, and
> then applies the profile's *legal* curve on top. If your legal curve is purely
> cost-derived (as the built-in default is), cost is counted twice and
> `P(legally playable)` reads low. Use the legal curve for requirements the
> simulator does not model — board conditions, targets, timing — and let the
> simulator handle cost.

---

## Conditional draw

A card that says "draw" is not a guaranteed extra card. Each draw source records
its copies, cards drawn, earliest turn, activation probability by turn, resource
cost, whether it needs a board or opponent state, whether it is repeatable, and
whether it consumes the resource you need for your target.

```
EXPECTED EXTRA DRAWS = P(seen) · P(condition active) · P(affordable) · P(strategic) · cards drawn
```

**Expected extra draws are reported, never substituted into a hypergeometric
target-access formula.** For exact target access in the presence of conditional
draws, use the simulator — that is what it is for.

---

## Board-state proxies

Reactive cards depend on the opponent. Rather than guess, the assumption is made
explicit and configurable:

```json
{"valid_target": {"1": 0.05, "2": 0.10, "3": 0.20, "4": 0.50, "5": 0.65, "6": 0.75}}
```

`MODE A — PROXY` samples these probabilities; `MODE B — SIMULATED` derives them
from a simplified generated board state. Any result that used a proxy is
labelled `HEURISTIC — Board-State Proxy`, never `EXACT`.

---

## Simulation

```bash
python cli.py analyze deck.txt --iterations 500000 --seed 20770301
```

Deterministic given a seed. Default 500,000 iterations (a few minutes); 10k /
50k / 100k / 500k / 1M are offered in the UI. Every simulated probability
reports its sample size, standard error and 95% confidence interval:

```
Jackie playable T3: 47.82%  (95% CI 47.68%–47.96%, n=500,000)
```

The simulator tracks turn, deck, hand, trash, eddies (total and ready), Legends
(order, ready/spent, face-up, called-this-turn), Gigs and Gig values, Street
Cred, units/gear/programs, cards seen, drawn and sold, resources spent and the
full action log. The turn flow is: **start** (ready → draw → gain a Gig) →
**main** (evaluate sell → evaluate Legend Call → evaluate draw effects →
evaluate target playability → evaluate generic plays).

Gig values come from a configurable discrete distribution —
`GigDistribution.uniform(6)`, `from_mapping({1: 3, 6: 1})`, or
`from_observations([...])` for dice you have actually rolled. **Uniformity is
never assumed unless you configure it.**

Legends are separate from the main deck, their order is randomized each game,
they may be Called once per turn, and they may instead be spent for resources.
The simulated pilot models that conflict directly: it will decline to Call a
Legend for a draw when doing so is what makes the target unaffordable this turn.

---

## Marginal slot value

```bash
python cli.py target deck.txt --target "Jackie Welles" --turn 3 --compare-copies 2 3
python cli.py compare deck_a.txt deck_b.txt --target "Jackie Welles"
```

```
Metric                       Jackie x2           Jackie x3        Delta
mechanical sellable %           62.50%              60.00%      -2.50pp
effective sellable T3           46.00%              43.88%      -2.13pp
target access T3                40.38%              54.50%     +14.12pp
sell consistency T3             99.23%              98.73%      -0.51pp
dead-card burden T3             28.03%              29.65%      +1.62pp
action density T3               71.97%              70.35%      -1.62pp
```

Deck size is always held constant: the question is never "should I add a card",
it is "what should this slot be".

---

## Sellable slot recommender

```bash
python cli.py recommend deck.txt --strategy YYG_Jackie
```

Ranks non-sellable cards by how cheap their slot is to convert, using strategic
playability, dead-card burden, redundancy and marginal contribution — and prints
the cost of each cut next to it.

**A card is never recommended for a cut merely because it is non-sellable.**

---

## Sensitivity analysis

```bash
python cli.py sensitivity deck.txt --card "Memory Relapse" --turn 3 \
    --values 0.0 0.05 0.10 0.20 0.30
```

Sweeps an uncertain assumption and reports how far the conclusion moves. A
conclusion that moves more than 5 percentage points across the tested range is
flagged as **material**: the honest answer is then "it depends on X", and X
belongs next to the number.

---

## CLI reference

```bash
python cli.py analyze deck.txt                                  # dashboard + target report
python cli.py analyze deck.txt --target "Jackie Welles" --turn 3
python cli.py analyze deck.txt --minimum-sellable 0.60 --target-sellable 0.625
python cli.py analyze deck.txt --target-sellable-min 0.60 --target-sellable-max 0.65
python cli.py analyze deck.txt --mulligan-profile "Jackie or Draw"
python cli.py sells deck.txt --through-turn 3                   # sell consistency tables
python cli.py target deck.txt --target "Jackie Welles" --compare-copies 2 3
python cli.py mulligan deck.txt --policies "No Mulligan" "Jackie or Draw"
python cli.py compare deck_a.txt deck_b.txt                     # two lists, slot for slot
python cli.py recommend deck.txt                                # sellable slot recommender
python cli.py sensitivity deck.txt --card "Memory Relapse"
python cli.py update-cards                                      # refresh the card database
python cli.py init-placeholder                                  # offline pool + sample deck
python cli.py cards ["Field Operator"]                          # list or inspect cards
python cli.py rules                                             # rules + override provenance
python cli.py demo                                              # the worked example
```

Common flags: `--cards`, `--strategy`, `--playability-profile`,
`--mulligan-profile`, `--max-turn`, `--iterations`, `--seed`,
`--ignore-legality`, `--export <stem>`.

---

## Streamlit UI

```bash
streamlit run app.py
```

| Tab | What it does |
| --- | --- |
| DECK | paste, parse, validate; unknown / ambiguous lines; matched official cards |
| OVERVIEW | composition, sellable status, cost curve, type mix, warnings, conclusions |
| SELLS | minimum / target / range, sell curves, density table, effective density, willingness |
| TARGET | target and turn, 2 vs 3 copies, raw access, the layered playability report |
| BOARD | editable legal/strategic playability, opponent proxies, LLM proposals |
| MULLIGAN | saved profiles, AND/OR rule builder, score-based policies, policy comparison |
| SIMULATION | iterations, seed, run, confidence intervals, draw attribution |
| COMPARE | variant A vs variant B with deltas |
| SENSITIVITY | pick an assumption, sweep a range, see whether conclusions move |
| CARD RULES | official text beside the structured interpretation and its verification status |

The sidebar holds the **Update Card Database** button, the sellable targets, the
rule overrides and the profile selection.

---

## Export

Every panel and every CLI command exports to JSON, CSV and Markdown with the
assumptions attached: deck name, analysis date, card-database version, update
date and provenance, minimum / target / range sellable settings, mulligan
profile, playability profile, iteration count, seed and every rule override.

```bash
python cli.py analyze deck.txt --export exports/jackie_t3
```

A number without its assumptions is not reproducible, so the exporters will not
drop them.

---

## Testing

```bash
python -m pytest -q          # 215 tests, ~25s
```

Covering the deck parser and every import format, card matching and pool
filtering, exact hypergeometric and multivariate probability, sequential sell
math, mechanical and effective sellable density, cards-needed arithmetic,
mulligan logic (including "no draw card" and minimum-sellables rules) and
score-based policies, Legend randomization and resource accounting, generic card
effects and conditional draws, deterministic simulation, marginal slot
comparison and sensitivity analysis.

Where the two can be made to agree, **Monte Carlo output is checked against the
exact hypergeometric result** — for example, a pilot that only draws and sells
reproduces the closed-form sell curve to within four standard errors.

---

## Project structure

```
cyberpunk_deck_math/
    config.py         rules, sellable settings, override tracking
    methods.py        the method labels every result carries
    models.py         Card, Deck, PlayabilityProfile, DrawSource
    parser.py         decklist parsing and validation
    session.py        shared wiring for the CLI and the UI
    export.py         JSON / CSV / Markdown with assumptions
    llm.py            optional Claude client for the assisted workflows
    database/         fetch_official, normalize, validate_pool, cache, placeholder
    probability/      hypergeom, multivariate, sells, mulligan
    simulation/       game, state, pilot, board_proxy, legends, gigs
    effects/          generic, interpreter, conditions, triggers
    analytics/        deck_summary, access, playability, dead_cards,
                      opportunity_density, sell_density, marginal_value,
                      sensitivity, mulligan_analytics, recommender, axioms,
                      target, interpretation
profiles/             mulligan/, playability/, strategies/
data/                 card cache and sample decklists
tests/                the pytest suite
app.py  cli.py  demo.py
```

---

## Limitations — read these before trusting a number

* **No opponent AI.** Opponent-dependent effects use configured proxy
  probabilities. Anything downstream of one is `HEURISTIC`, never `EXACT`.
* **Playability values are assumptions.** The bundled profiles are human
  estimates on a placeholder card pool. They are a starting point for
  playtesting, not a result of it.
* **The bundled card data is placeholder data** until you run `update-cards`.
  Costs, sellable flags and effects in it were chosen to exercise the model.
* **Exact sell math assumes full willingness to sell.** The simulator's figure is
  lower because the pilot also plays those cards. Both are reported; they answer
  different questions.
* **Combat, damage and the score race are not modelled.** This is a consistency
  and resource-development model, not a game engine.
* **60–65% sellable is a playtesting heuristic**, not a rule of the game, and it
  is not derived from sealed-format deckbuilding guidance.
* **Monte Carlo differences inside the 95% confidence interval are noise.** The
  tool prints the interval so you can tell; it will not stop you from
  over-reading a 0.2-point difference.
* **`update-cards` depends on an endpoint that may change.** If the official
  site's JSON URL moves, pass `--source-url` or `--source-file`; the command
  fails loudly rather than falling back to stale or invented data.
