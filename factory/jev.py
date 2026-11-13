"""System 1: Jev answers atomic judgments; questions.decide turns them into a verdict."""
import time

import sentry_sdk
from typesafe_sdk import TypeSafeClient

from . import config
from .candidates import Candidate
from .questions import QUESTIONS, decide

_client: TypeSafeClient | None = None


def ask(c: Candidate, ticket: str, examples: list[dict]) -> dict:
    global _client
    _client = _client or TypeSafeClient()
    state = {"ticket": ticket, "function": c.function, "snippet": c.snippet}
    if examples:
        state["past_decisions_in_this_codebase"] = examples
    with sentry_sdk.start_span(op="gen_ai.chat", name=f"jev {c.kind}") as span:
        t0 = time.perf_counter()
        r = _client.system_one(model=config.JEV_MODEL, state=state, questions=QUESTIONS[c.kind])
        latency = (time.perf_counter() - t0) * 1000
        tokens = r.usage.input_tokens if r.usage else 0
        span.set_data("gen_ai.request.model", config.JEV_MODEL)
        span.set_data("gen_ai.usage.input_tokens", tokens)
    probs = {k: r.answers[k].noul for k in QUESTIONS[c.kind]}
    return {
        "verdict": decide(c.kind, probs),
        "probs": probs,
        "latency_ms": latency,
        "tokens": tokens,
        "cost_usd": tokens * config.JEV_PRICE_IN / 1e6,
        "model": getattr(r, "model", config.JEV_MODEL),
    }
