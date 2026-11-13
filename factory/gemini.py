"""System 2: Gemini decides unsettled cases and writes/patches reflex rules."""
import time
from typing import Literal

import sentry_sdk
from google import genai
from google.genai import types
from pydantic import BaseModel

from . import config
from .candidates import FIX_DESCRIPTION, Candidate

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    _client = _client or genai.Client(api_key=config.env("GEMINI_API_KEY"))
    return _client


class Verdict(BaseModel):
    verdict: Literal["cut", "keep"]
    reason: str


class RuleDraft(BaseModel):
    regex: str
    message: str


def _retry(fn, waits=(3, 8, 20, 40)):
    """Free-tier 429 (quota/RPM) and 503 (busy) are transient: back off and retry, then raise."""
    for w in (*waits, None):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if w is None or "PerDay" in msg or not any(c in msg for c in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")):
                raise  # daily quota won't recover by waiting
            time.sleep(w)


def _call(prompt: str, schema: type[BaseModel], name: str):
    if not config.S2_MODEL:
        raise RuntimeError("GEMINI_S2_MODEL is empty in .env")
    with sentry_sdk.start_span(op="gen_ai.chat", name=name) as span:
        t0 = time.perf_counter()
        r = _retry(lambda: client().models.generate_content(
            model=config.S2_MODEL, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema),
        ))
        latency = (time.perf_counter() - t0) * 1000
        u = r.usage_metadata
        tin = (u.prompt_token_count or 0) if u else 0
        tout = ((u.candidates_token_count or 0) + (u.thoughts_token_count or 0)) if u else 0
        span.set_data("gen_ai.request.model", config.S2_MODEL)
        span.set_data("gen_ai.usage.input_tokens", tin)
        span.set_data("gen_ai.usage.output_tokens", tout)
    if r.parsed is None:
        raise RuntimeError(f"Gemini returned unparseable output: {r.text[:200]!r}")
    cost = tin * config.S2_PRICE_IN / 1e6 + tout * config.S2_PRICE_OUT / 1e6
    return r.parsed, latency, tin + tout, cost


def decide(c: Candidate, ticket: str) -> dict:
    prompt = f"""You review code written by an AI coding agent and remove slop.

Ticket the agent was given:
{ticket}

Function containing the candidate:
```python
{c.function}
```

Candidate ({c.kind}):
```python
{c.snippet}
```

If you answer "cut", we will {FIX_DESCRIPTION[c.kind]}.
Answer "cut" only if the code is better without it and the ticket's behavior is unchanged.
reason: one blunt sentence a senior reviewer would say, under 15 words."""
    v, latency, tokens, cost = _call(prompt, Verdict, f"gemini decide {c.kind}")
    return {"verdict": v.verdict, "reason": v.reason, "latency_ms": latency, "tokens": tokens, "cost_usd": cost}


def write_rule(kind: str, positives: list[str], negatives: list[str]) -> dict:
    pos = "\n\n".join(f"--- CUT example {i + 1}\n{p}" for i, p in enumerate(positives))
    neg = "\n\n".join(f"--- KEEP example {i + 1}\n{n}" for i, n in enumerate(negatives)) or "(none yet)"
    prompt = f"""You have reviewed many {kind} snippets. Turn the habit into a reflex rule.

Write ONE Python regular expression (it will run with re.search and re.MULTILINE, and as a Semgrep
pattern-regex) that matches every CUT example and none of the KEEP examples. Prefer a short, readable
regex that captures the general pattern, not one that lists the examples.

{pos}

{neg}

message: one blunt sentence explaining why this pattern is slop, under 15 words."""
    d, latency, tokens, cost = _call(prompt, RuleDraft, f"gemini write_rule {kind}")
    return {"regex": d.regex, "message": d.message, "latency_ms": latency, "tokens": tokens, "cost_usd": cost}


def embed(text: str) -> list[float] | None:
    if not config.EMBED_MODEL:
        return None
    r = _retry(lambda: client().models.embed_content(model=config.EMBED_MODEL, contents=text,
                                      config=types.EmbedContentConfig(output_dimensionality=768)))
    return list(r.embeddings[0].values)
