# AGENTS.md

Hackathon build, 5h, deadline 3 PM. Ship the demo path; nothing else. Why/plan: README.md (read only if asked).

## Token rules
- Don't read `data/`, `rules/*.yml` history, lockfiles, or `node_modules`. Open a single file only when needed.
- Don't re-read files you just wrote. No repo-wide scans; use `rg` with a path.
- Answers: code + 1-line summary. No recaps, no alternatives unless asked.
- Don't add docs, comments, tests, or abstractions beyond the task.

## Ownership (don't edit the other person's area)
- Shri: `factory/` `target/` `rules/` `scripts/`
- Ali: `web/` `db/` DigitalOcean (Serverless Inference agent + App Platform), Sentry
- Shared contract = `db/schema.sql`. Column changes need both people.

## Stack
- factory: Python 3.12, `uv`, Jev client (TypeSafe AI), `google-genai`, `psycopg[binary]`, `pgvector`, `sentry-sdk`, `fastapi`, `pyyaml`
- web: Vite + React + TS, polls `factory/api.py` (FastAPI: /api/state from data/run/events.jsonl, /api/rules, /api/tiger), `@sentry/react`
- DB: Tiger Data (Postgres + timescaledb + vector).
- Models via env only: `JEV_MODEL` (System 1), `GEMINI_S2_MODEL` (System 2), `GEMINI_EMBED_MODEL` (768 dims).
- Any Jev/TypeSafe code: use the `typesafe-ai` skill and its live docs (docs.typesafe.ai/llms.txt). Don't guess API shape.

## Commands
- smoke: `uv run scripts/smoke.py [--apply-schema]`
- PRs: `uv run scripts/make_prs.py`
- factory: `uv run python -m factory.run --prs data/prs [--reset] [--pace 0.5]`
- api: `uv run uvicorn factory.api:app --port 8000` · web: `cd web && npm run dev`
- target tests: `cd target && uv run pytest tests tickets/test_T01.py` (<1s). Hidden: `target/holdout/`
- rules in CI: `semgrep --config rules/ <path>`

## Invariants
- Tiers in order: `reflex` (rule regex) → `jev` → `gemini`.
- Candidate kind is decided in code (`factory/candidates.py`), not by a model. Jev gives judgments, code decides: one request per candidate with that kind's atomic Nouls. Keep/cut = truth table in `factory/questions.py` (all wording + thresholds live there). Don't gate on `confidence`. Failed call = error, never a verdict. Log every decision to `decisions` with tier, latency_ms, tokens. Sentry span on every Jev/Gemini call.
- Every verdict is shadow-verified (remove hunk → run tests + holdout) before `correct` is set.
- New rule only when a `kind` has ≥5 verified CUTs; Gemini writes a regex; it must match ≥80% of verified CUTs and 0 verified KEEPs.
- Spot check: Gemini re-decides 15% of reflex/jev calls. A reflex cut that breaks tests sets `active: false`; Gemini patches it as v+1.
- Models never see `target/holdout/`.
- Comment patterns in Semgrep: use `pattern-regex`.
- Secrets only in `.env`. Never commit it.
