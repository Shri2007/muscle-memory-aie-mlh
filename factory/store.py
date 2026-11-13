"""Writes every event to data/run/events.jsonl (dashboard source) and, if DATABASE_URL is set, to Tiger."""
import json
import math
import time

from . import config


class Store:
    def __init__(self, reset: bool = False):
        config.RUN_DIR.mkdir(parents=True, exist_ok=True)
        if reset:
            config.EVENTS.unlink(missing_ok=True)
        self.trusted: list[dict] = []   # verified decisions: {kind, verdict, snippet, embedding}
        self.db = None
        if config.DATABASE_URL:
            import psycopg
            from pgvector.psycopg import register_vector
            self.db = psycopg.connect(config.DATABASE_URL, autocommit=True)
            register_vector(self.db)
            if reset:
                self.db.execute("TRUNCATE decisions, hunks, prs, rules RESTART IDENTITY")

    def event(self, type_: str, **data) -> dict:
        row = {"type": type_, "ts": time.time(), **data}
        with config.EVENTS.open("a") as f:
            f.write(json.dumps(row) + "\n")
        return row

    # --- Tiger ---------------------------------------------------------------
    def pr(self, agent: str, ticket: str) -> int | None:
        if not self.db:
            return None
        return self.db.execute("INSERT INTO prs (agent, ticket) VALUES (%s, %s) RETURNING id",
                               (agent, ticket)).fetchone()[0]

    def hunk(self, pr_id, file, kind, content, embedding) -> int | None:
        if not self.db:
            return None
        import numpy as np
        emb = np.array(embedding, dtype=np.float32) if embedding else None
        return self.db.execute(
            "INSERT INTO hunks (pr_id, file, kind, content, embedding) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (pr_id, file, kind, content, emb)).fetchone()[0]

    def decision(self, d: dict) -> None:
        if not self.db:
            return
        self.db.execute(
            """INSERT INTO decisions (hunk_id, tier, verdict, rule_id, latency_ms, tokens, cost_usd,
                                      correct, safe, spot_check, reason)
               VALUES (%(hunk_id)s, %(tier)s, %(verdict)s, %(rule_id)s, %(latency_ms)s, %(tokens)s,
                       %(cost_usd)s, %(correct)s, %(safe)s, %(spot_check)s, %(reason)s)""", d)

    def rule(self, r) -> None:
        if not self.db:
            return
        self.db.execute(
            """INSERT INTO rules (id, kind, verdict, pattern_regex, message, support, version, active)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET active = EXCLUDED.active""",
            (r.id, r.kind, r.verdict, r.regex, r.message, r.support, r.version, r.active))

    # --- examples for Jev ----------------------------------------------------
    def remember(self, kind: str, verdict: str, snippet: str, embedding) -> None:
        self.trusted.append({"kind": kind, "verdict": verdict, "snippet": snippet, "embedding": embedding})

    def examples(self, kind: str, embedding, k: int = 5) -> list[dict]:
        pool = [t for t in self.trusted if t["kind"] == kind]
        if embedding:
            pool = [t for t in pool if t["embedding"]]
            pool.sort(key=lambda t: -_cos(t["embedding"], embedding))
        else:
            pool = pool[::-1]
        return [{"snippet": t["snippet"], "verdict": t["verdict"]} for t in pool[:k]]

    def by_kind(self, kind: str, verdict: str) -> list[str]:
        return list(dict.fromkeys(t["snippet"] for t in self.trusted if t["kind"] == kind and t["verdict"] == verdict))


def _cos(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1)
