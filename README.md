# Muscle Memory

**A software factory that turns slow thinking into reflexes.**

AIE x MLH Hackathon @ Code Summit · Bright Data, SF · Team: Shri + Ali

> Built at the AIE x MLH Hackathon on Nov 13, 2026. The plan and schema were drafted the night before; all running code was written at the event.

---

## In plain English (30-second pitch)

AI writes a lot of code now, and much of it is sloppy: it's padded, has unnecessary safety checks, and contains junk nobody needs. We built an editor that cleans it up.

At first the editor thinks hard about every cut, which is slow and expensive. Every time a cut proves correct, it remembers. Once it has made the same call enough times, it writes the habit down as a simple rule, and from then on that call is instant and free.

It's how you learned to drive. At first you think through every move. Eventually it becomes muscle memory. We built that for AI, and you can watch it happen live.

*"How do you know the cuts are safe?"* Every cut is checked by actually running the code's tests, plus a second set of tests the AI never sees.

## The idea in one paragraph

Coding agents write PRs. A lot of what they write is slop: try/except blocks that swallow everything, defensive checks nobody needs, dead helpers, comments that restate the code. Muscle Memory is a factory that removes it one hunk at a time. Each hunk gets a keep-or-cut call. At first, every call goes to a slow reasoning model (System 2: Gemini, ~3 s). Each call is checked against the real test suite. Familiar cases move to **Jev**, a System One decision model that answers a typed `Choice: keep | cut` in milliseconds. Once a kind of call has five verified decisions and zero misses, Gemini writes that habit down as a **Semgrep rule**. From then on, that kind of decision runs as a reflex: ~0 ms, zero tokens. Decisions graduate from slow thought, to a System One model, to code. Over one demo the factory gets faster and cheaper while output quality stays flat, and you can read everything it learned in `rules/`.

## Why it's not a toy

- Teams are flooded with agent PRs, and reviewing them is slow and expensive.
- Model routing saves money but leaves the router a black box. Here the cheap path is **code you can read, diff, and turn off**.
- The rules are standard Semgrep YAML. Any team can drop them into the CI they already run. Adopting them doesn't require changing their workflow.

## How it fits the track prompts

| Track prompt | Our answer |
|---|---|
| **Best Use of System One Models**: "Jev started the decision models rush… leverages a system one model" | **Jev is the System 1 tier.** Following TypeSafe's "judgments from Jev, decisions in code" pattern: each hunk gets one bundled request with an atomic Noul per slop pattern plus a Choice for slop kind, and a truth table in code decides keep or cut. Jev's latency and cost sit next to Gemini's on screen. Then we take the summit's "System One models should become integrated with code" theme literally: Jev-verified habits compile to rules. |
| **Cleanest Use of a Software Factory**: "fight back against AI slop with the cleanest and clearest use of a software factory" | The **whole factory is on one screen**: tickets → 3 agents → Muscle Memory → merged clean code. Cleanest: the smallest diff that passes tests, and we **run the learned rules on our own repo: 0 hits**. Clearest: every decision is in a ledger, and every learned habit is a readable, versioned rule. |
| **Best Overall** | Real agent PRs, real tests, real numbers, plus a moment where it learns live and a moment where it fixes its own mistake. |
| **Gemini** | System 2: reasoning decisions, writing rules, patching rules. Also embeddings for similar-case lookup. |
| **Tiger Data**: "innovative, impactful, performance-driven" | One Postgres holds relational (PRs, rules), vector (pgvector), and time series (decisions hypertable). A **Tiger panel** on the dashboard shows (1) one SQL query joining vector similarity with the time series, (2) the compression ratio on `decisions`, (3) continuous-aggregate query time vs. raw. A stretch goal is a bulk run over public agent patches for real volume. |
| **Sentry** (raffle) | AI agent monitoring spans on every Jev and Gemini call. Sentry's own dashboard independently shows token use dropping. Opt in to the raffle at submit. |
| **DigitalOcean** | The 3rd coding agent runs on **DO Serverless Inference** (`DO_INFERENCE_KEY`). App Platform hosts the dashboard (`factory.api` serves `web/dist`). Managed Agents is a stretch goal. |
| Snowflake | Skipped on purpose. Forcing it in would weaken the project. |

## Architecture

```
tickets → 3 coding agents on DO Managed Agents → PRs
        │  split into hunks
        ▼
   ┌─ ROUTER ────────────────────────────────────────┐
   │ 1. Reflex   semgrep rules/*.yml match?   ~0 ms  │
   │ 2. Jev      System One Choice keep|cut,  ~ms    │
   │             state = hunk + 5 nearest (pgvector) │
   │ 3. Gemini   System 2: decide, write/patch ~3 s  │
   │             rules                               │
   └──────────────────────────────────────────────────┘
        │ verdict: KEEP / CUT
        ▼
 SHADOW VERIFY: remove hunk → run target/ tests (+ held-out suite)
        │ correct? → decisions hypertable (Tiger)
        ▼
 RULE WRITER: kind has ≥5 verified S2 decisions, 0 misses
        → S2 writes Semgrep rule → validated against ALL past
          decisions → committed to rules/ (git log = the factory's brain)
 SPOT CHECK: Gemini re-decides 10% of Jev/reflex calls; a miss
        demotes that kind back to Gemini and patches the rule
        │
        ▼
 DASHBOARD (web/): factory strip (tickets→agents→gate→merged),
                   decision timer, 3 tier lanes, rules/ live view,
                   cost + accuracy charts, Tiger panel
```

**Shadow verification.** At the demo we run the tests on every hunk so each call has ground truth. In production you would sample instead. This is what lets us say "quality stayed flat" with a straight face.

**Held-out suite.** `target/tests_holdout/` is never shown to any model. It answers the obvious judge question: "Did it just learn to game your tests?"

## Honest score (our own evaluator, anti-inflation rules)

| Novelty | Feasibility | Scalability | Impact | Demo | Domain | Total |
|---|---|---|---|---|---|---|
| 8 | 8 | 8 | 8 | 9 | 9 | **50/60** |

That total assumes all three of these ship. Each one we drop costs points:
1. **Rules are Semgrep, not Python.** Drop-in CI adoption (Impact 8), no sandbox (Feasibility 8).
2. **Rule birth on cue.** Threshold = 5 verified decisions. Seed 4 examples of one pattern, run the 5th live (Demo 9).
3. **A finding.** Three agents on the same 10 tickets: "Agent A's slop is mostly swallowed exceptions, Agent B's is dead helpers, here are the N rules learned." (Novelty 8.) **Cut this first if we're late.** Without it we score 49.

## Top risks and mitigations

| Risk | Mitigation |
|---|---|
| Tests slower than ~2 s → loop too slow | `target/` is a tiny Python lib we pick at 9 AM. pytest `-x -q`, no I/O. |
| No pattern repeats enough to birth a rule | Narrow decision type (keep/cut hunk), small repo, seeded examples. |
| Curve looks too perfect, so judges call it fake | Show the miss live: a rule over-cuts, held-out test fails, S2 patches the rule, the rule diff is shown on screen. |
| Semgrep can't see comments | Use `pattern-regex` for comment-based rules. |
| No Jev access (early access) | Sign up tonight. If waitlisted, ask TypeSafe/MLH at 9 AM. Without Jev the System One track is out. Fall back to Flash-Lite and say so honestly. |
| Jev's speed claims are vendor numbers | We measure and show our own latency. Don't quote theirs. |

## Demo script (3 min)

1. **0:00** One line: "Agents write slop. Our factory cuts it, and learns to cut it faster." Point at the factory strip: tickets → agents → gate → merged.
2. **0:20** PRs stream in. Every call is in the Gemini lane, and the timer reads 3.1 s.
3. **0:50** Jev lane starts filling. Timer drops to milliseconds. Show the Jev and Gemini latency/cost side by side.
4. **1:20** **Rule birth (live):** the 5th example lands, `rules/swallowed_exception.yml` appears, and that pattern drops to the reflex lane at 0 ms.
5. **1:50** **The miss:** a rule over-cuts, the held-out test goes red, S2 patches the rule, and the git diff is shown.
6. **2:20** Charts: decision time 3.1 s → ~0 ms, cost per PR down X%, held-out pass rate flat. Tiger panel. Sentry's dashboard showing the same token drop.
7. **2:45** "We ran the learned rules on our own repo: 0 hits." The finding plus the close: "These rules are Semgrep. You can run them in your CI tonight."

## How we get there: timeline (day of)

| Time | Shri | Ali |
|---|---|---|
| **Tonight** | Accounts + keys: **Jev (early access, top priority)**, Gemini, Sentry. Smoke-test one Jev `Choice` call. | Accounts + keys: Tiger Cloud (run `db/schema.sql` to test it), DigitalOcean (claim credits, read Managed Agents quickstart). Install Semgrep. |
| **9:00–10:00** | Pick `target/` repo, write 10 tickets | Launch 3 coding agents on **DO Managed Agents** → PRs into `data/prs/` (fallback: run locally). Scaffold `web/`. |
| **10:00–12:00** | `factory/`: hunk splitter, shadow verify, Gemini decider, decision writes | Dashboard: factory strip, timer, 3 lanes, polling `/api/state`; Sentry SDK in web + API |
| **12:00–1:00** | Jev tier (pgvector nearest-5 → `Choice`), router, Sentry spans on Jev + Gemini | Charts from continuous aggregates; `rules/` live view + git-log panel; Tiger panel |
| **1:00–1:30** | Lunch + **integration**: end-to-end run on 5 PRs | Lunch + integration |
| **1:30–2:15** | Rule writer + validator + spot-check demotion; run rules on our own repo | Seed script for rule-birth-on-cue; the finding table (if on time) |
| **2:15** | **Feature freeze.** | **Feature freeze.** |
| **2:15–2:50** | Rehearse demo x3, fix only demo-blocking bugs | Deploy to DO, record backup video of a full run |
| **3:00** | Submit (opt into Sentry raffle + all tracks) | Submit check |

**Cut order if behind:** finding table → Tiger bulk run → DO Managed Agents (run agents locally) → DO deploy (demo locally). **Never cut Jev.** It's the System One track.

## Ownership

- **Shri: `factory/`, `target/`, `rules/`.** Pipeline, Jev + Gemini tiers, rule generation.
- **Ali: `web/`, `db/`, `data/`, DigitalOcean, Sentry wiring.** Agents on Managed Agents, data layer, dashboard, hosting, tracing.
- **Contract between us: the database.** Shri writes rows, Ali reads them. Don't change a column without telling the other person. Schema: `db/schema.sql`.

## Repo layout

```
factory/   pipeline (Python): split, route, decide, verify, write rules   [Shri]
target/    tiny lib + tests/ + tests_holdout/ the factory cleans          [Shri]
rules/     generated Semgrep YAML; git history = what the factory learned [Shri]
data/      agent PRs from DO Managed Agents (gitignored)                   [Ali]
db/        schema.sql (Tiger Data / Postgres)                             [Ali]
web/       dashboard + /api/state (Vite React + small Node API)           [Ali]
```

## Run it

```bash
uv sync && (cd web && npm install && npm run build)
cp .env.example .env                                   # fill keys (see comments in the file)
uv run scripts/smoke.py --apply-schema                 # one call per service + creates Tiger tables
uv run scripts/make_prs.py                             # 3 agents x 10 tickets -> data/prs/
uv run uvicorn factory.api:app --port 8000             # dashboard at http://localhost:8000
uv run python -m factory.run --prs data/prs --reset    # in a 2nd terminal: run the factory
```

Dev dashboard with hot reload: `cd web && npm run dev` (proxies `/api` to :8000).

### Demo run (rule birth on cue)

```bash
uv run python -m factory.run --prs data/seed --reset --pace 0.6   # 5 hand-written slop PRs, labeled agent "seed"
uv run python -m factory.run --prs data/prs --pace 0.3            # then the real agent PRs; rules carry over
```

The seed PRs are hand-written and labeled `seed` on screen, so say so in the demo. They give `restating_comment`
and `swallowed_exception` enough verified examples to write a rule. Everything after that is real agent output.

### How a decision works

1. `factory/candidates.py` finds candidates **in code** (try/except that never re-raises, full-line comments,
   single-line if-guards, `print` calls). Models never decide what a candidate is.
2. Router: **reflex** rule match (`rules/*.yml`, Python `re`) → **Jev** atomic Nouls → truth table in
   `factory/questions.py` → if the answer is unsettled (any Noul between 0.3 and 0.7), **Gemini** decides.
3. `factory/verify.py` applies the fix in a scratch copy of `target/` and runs public + hidden tests.
   A cut ships only if public tests stay green and hidden-test failures don't increase.
4. After 5 verified CUTs of a kind, Gemini writes a regex rule. It must match ≥80% of verified CUTs and
   **zero** verified KEEPs, or it's rejected. Saved as Semgrep YAML and committed to git (`rules/` history).
5. A reflex cut that breaks tests demotes its rule (`active: false`) and Gemini patches it (v2).
   15% of reflex/Jev calls are re-checked by Gemini (dim dots on the chart).

Offline check (no keys needed): the seed PRs pass the candidate finder and verification. Hidden-test failures go
from 2 to 0 on the T04 seed after cutting the swallowed exception, and every needed guard is caught as unsafe.
