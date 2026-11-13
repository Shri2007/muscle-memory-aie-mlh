# Muscle Memory

**Live dashboard:** https://muscle-memory-mjivi.ondigitalocean.app  
**Code:** https://github.com/Shri2007/muscle-memory-aie-mlh

**A software factory that turns slow thinking into reflexes.**

## What it does

AI coding agents ship slop: comments that restate the code, `try/except` blocks that swallow errors so bugs hide, debug prints left behind. Muscle Memory sits between the agents and the main branch and cleans every PR before it merges.

At first it thinks about every cut, which is slow and costs money. Each cut that the tests prove correct is remembered. Once the factory has made the same call enough times, it writes the habit down as a plain regex rule (standard Semgrep YAML, committed to git). From then on that call takes 0.05 ms and costs nothing. When a rule over-cuts, the tests catch it, the rule is switched off, and a fixed version is written. You can watch all of this happen live on the dashboard.

## How it works

1. **Find candidates in code.** A Python scanner picks out the suspicious hunks (full-line comments, `except` blocks that never re-raise, one-line `if` guards, `print` calls). Models never decide what counts as a candidate.
2. **Decide, cheapest tier first.**
   - **Reflex:** a learned rule matches. No model call.
   - **System 1 (Jev, TypeSafe):** Jev answers small yes/no questions about the hunk and its ticket. A truth table in code (`factory/questions.py`) turns those answers into keep/cut.
   - **System 2 (Gemini):** used only when a Jev answer is unsettled (probability 0.3–0.7).
3. **Verify.** Each cut is applied in a scratch copy and the public tests plus a hidden test set run. Models never see the hidden tests. A cut that breaks anything is reverted.
4. **Learn.** After 5 verified cuts of one kind, Gemini drafts a regex. It's accepted only if it matches at least 80% of verified cuts and zero verified keeps.
5. **Self-correct and audit.** If a rule's cut breaks the tests, the rule is switched off and Gemini writes v+1. Gemini also re-checks 15% of reflex/Jev calls.

Every decision is logged with its tier, latency and token count to a JSONL event stream (which feeds the dashboard) and to Tiger Data.

## Results from the real run (Nov 13)

Two Gemini coding agents (`gemini-4-hydrogen`, `gemini-3.5-flash-lite`) implemented the same 10 tickets on a small Python library, for 20 PRs total.

| Tier | Decisions | Avg time | Cost per decision |
|---|---|---|---|
| Reflex (learned rule) | 11 | 0.05 ms | $0 |
| System 1: Jev | 80 | 127 ms | $0.00004 |
| System 2: Gemini 4 Hydrogen | 4 | 2,031 ms | $0.003 |

- Jev handled 80 of the 84 model decisions on its own. That's about 16× faster and 80× cheaper than Gemini.
- Two rules were learned live: `restating_comment` and `swallowed_exception`.
- The factory caught and fixed its own mistake. `swallowed_exception` v1 over-cut a function whose ticket requires returning `None` on bad input. The tests caught it, v1 was switched off, and Gemini wrote v2, which excludes that case. All three steps are in the `rules/` git history.
- 0 unsafe cuts shipped. 1 bad cut was caught by the tests and reverted.
- On the seed PRs, cutting swallowed exceptions took hidden-test failures from 3 to 0.

## What's real and what isn't

- **Hand-written:** the 6 seed PRs in `data/seed/`. They're labeled `seed` on the dashboard and exist so the first rules appear on cue in a live demo. The target library, its tickets, and its tests were also written by us.
- **Real agent output:** everything else. That includes the 20 agent PRs, every Jev and Gemini decision, every learned rule and its git commits, the demotion and v2 patch, and all of the numbers above. The real agent PRs had less slop than our seeds: Flash Lite's code was cut by 8% and Hydrogen's by under 1%, mostly comments that restate the code.
- The plan and DB schema were drafted the night before. All running code was written at the event.

## Tracks

| Track | Why it fits |
|---|---|
| **Best Use of System One Models** | Jev is the System 1 tier and settled 95% of model decisions. We use TypeSafe's recommended pattern (Jev gives judgments, code decides). We also take "System One models should become integrated with code" literally: habits Jev has proven turn into code rules. |
| **Cleanest Use of a Software Factory** | Agents → gate → clean merged code. Every cut is verified by public and hidden tests, every decision is logged, and every learned habit is a readable, versioned Semgrep rule. 0 unsafe cuts shipped. |
| **Best Overall** | Real agent PRs, real tests and real numbers, from a factory that learns live and fixes its own mistake on camera. |
| **Gemini** | Gemini 4 Hydrogen is System 2: it decides unsettled cases, writes rules, and rewrites rules that over-cut. Two Gemini models are the coding agents, and Gemini embeddings power the similar-case lookup. |
| **Tiger Data** | One Postgres database holds the relational data (PRs, rules), the vectors (pgvector, for similar past decisions) and the time series (a `decisions` hypertable with a continuous aggregate and compression). The dashboard runs one query that combines vector similarity with a time window, and it shows continuous-aggregate speed next to the raw query. |
| **Sentry** | Every Jev and Gemini call is a `gen_ai` span with the model name and token counts, and each PR is a transaction. The dashboard uses `@sentry/react`. |
| **DigitalOcean** | The API serves the built dashboard, so the whole app is one container (`Dockerfile`) deployed as one App Platform service (`.do/app.yaml`, all keys stored as secrets). `scripts/make_prs.py` can add a third coding agent on DO Serverless Inference. |
| **Snowflake** | `scripts/snowflake_report.py` loads the decision log into Snowflake, aggregates slop kinds per agent in SQL, and uses Cortex `AI_COMPLETE` to write a short slop report for each agent: what it produces most and what the factory learned. It runs separately from the live demo. |

## Built with

Jev (TypeSafe AI) · Gemini 4 Hydrogen, Gemini 3.5 Flash Lite, Gemini embeddings · Tiger Data (TimescaleDB + pgvector) · Sentry · Semgrep · Snowflake Cortex · DigitalOcean App Platform + Serverless Inference · Python 3.12 (FastAPI, pytest, uv) · React + Vite + TypeScript · Docker
