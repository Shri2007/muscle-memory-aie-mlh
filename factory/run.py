"""Muscle Memory factory. Usage: uv run python -m factory.run --prs data/prs [--reset] [--pace 0.5]"""
import argparse
import json
import random
import time
from pathlib import Path

import sentry_sdk

from . import config, gemini, jev, reflex
from .candidates import Candidate, apply_fix, extract
from .store import Store
from .verify import Workspace


class Factory:
    def __init__(self, store: Store, pace: float):
        self.store, self.pace = store, pace
        self.rules = reflex.load()
        self.attempts: dict[str, int] = {}
        self.n = 0

    # ---- routing: reflex -> jev -> gemini ----------------------------------
    def decide(self, c: Candidate, ticket: str, emb) -> dict:
        t0 = time.perf_counter()
        rule = reflex.match(self.rules, c)
        if rule:
            return {"tier": "reflex", "verdict": rule.verdict, "rule_id": rule.id, "reason": rule.message,
                    "latency_ms": (time.perf_counter() - t0) * 1000, "tokens": 0, "cost_usd": 0.0}
        try:
            j = jev.ask(c, ticket, self.store.examples(c.kind, emb))
            if j["verdict"]:
                probs = ", ".join(f"{k}={v:.2f}" for k, v in j["probs"].items())
                return {"tier": "jev", "verdict": j["verdict"], "rule_id": None, "reason": probs,
                        **{k: j[k] for k in ("latency_ms", "tokens", "cost_usd")}}
            self.store.event("escalate", kind=c.kind, probs=j["probs"])
        except Exception as e:  # a failed call is an error, never a verdict: log it and escalate
            sentry_sdk.capture_exception(e)
            self.store.event("error", tier="jev", error=f"{type(e).__name__}: {e}"[:300])
        try:
            g = gemini.decide(c, ticket)
        except Exception as e:  # System 2 unavailable: skip this candidate, never invent a verdict
            sentry_sdk.capture_exception(e)
            self.store.event("error", tier="gemini", kind=c.kind, error=f"{type(e).__name__}: {e}"[:300])
            return None
        return {"tier": "gemini", "rule_id": None, **g}

    # ---- one PR -------------------------------------------------------------
    def run_pr(self, pr: dict, name: str) -> None:
        ticket_id, agent = pr["ticket"], pr["agent"]
        ticket = (config.TARGET / "tickets" / f"{ticket_id}.md").read_text()
        ws = Workspace(ticket_id, pr["files"])
        try:
            public_ok, holdout = ws.run()
            if not public_ok:
                self.store.event("pr_rejected", pr=name, agent=agent, ticket=ticket_id)
                return
            pr_id = self.store.pr(agent, ticket_id)
            before = sum(len(t.splitlines()) for t in pr["files"].values())
            self.store.event("pr_start", pr=name, agent=agent, ticket=ticket_id, lines=before,
                             holdout_failed=len(holdout))
            clean = {}
            for rel, src in pr["files"].items():
                src, holdout = self.clean_file(ws, rel, src, holdout, ticket, name, agent, pr_id)
                clean[rel] = src
            after = sum(len(t.splitlines()) for t in clean.values())
            out = config.RUN_DIR / "clean" / name
            for rel, text in clean.items():
                (out / rel).parent.mkdir(parents=True, exist_ok=True)
                (out / rel).write_text(text)
            self.store.event("pr_done", pr=name, agent=agent, ticket=ticket_id, lines_before=before,
                             lines_after=after, holdout_failed=len(holdout))
        finally:
            ws.close()

    def clean_file(self, ws, rel, src, holdout, ticket, name, agent, pr_id):
        done: set[str] = set()
        while True:
            try:
                cands = [c for c in extract(src) if c.key not in done]
            except SyntaxError:
                return src, holdout
            if not cands:
                return src, holdout
            c = cands[0]
            done.add(c.key)
            fixed = apply_fix(src, c)
            if fixed is None:
                continue
            try:
                emb = gemini.embed(c.snippet) if config.EMBED_MODEL else None
            except Exception as e:
                self.store.event("error", tier="embed", error=f"{type(e).__name__}: {e}"[:300])
                emb = None
            d = self.decide(c, ticket, emb)
            if d is None:
                continue
            hunk_id = self.store.hunk(pr_id, rel, c.kind, c.snippet, emb)

            ws.write(rel, fixed)
            public_ok, h = ws.run()
            safe = public_ok and h <= holdout
            if d["verdict"] == "cut" and safe:
                src, holdout = fixed, h
            else:
                ws.write(rel, src)
            correct = safe if d["verdict"] == "cut" else (True if not safe else None)
            self.record(d, c, name, agent, hunk_id, safe, correct, spot=False)

            if d["verdict"] == "cut" and safe or d["verdict"] == "keep" and (not safe or d["tier"] == "gemini"):
                self.store.remember(c.kind, d["verdict"], c.snippet, emb)
            if d["tier"] == "reflex" and not safe:
                self.demote(d["rule_id"], c)
            elif d["tier"] != "gemini" and random.random() < config.SPOT_CHECK_RATE:
                try:
                    g = gemini.decide(c, ticket)
                    self.record({"tier": "gemini", "rule_id": None, **g}, c, name, agent, hunk_id, safe,
                                g["verdict"] == d["verdict"], spot=True)
                except Exception as e:
                    self.store.event("error", tier="gemini_spot", error=f"{type(e).__name__}: {e}"[:300])
            self.maybe_learn(c.kind)
            time.sleep(self.pace)

    def record(self, d, c, name, agent, hunk_id, safe, correct, spot):
        self.n += 1
        row = {"hunk_id": hunk_id, "tier": d["tier"], "verdict": d["verdict"], "rule_id": d["rule_id"],
               "latency_ms": round(d["latency_ms"], 3), "tokens": d["tokens"], "cost_usd": d["cost_usd"],
               "correct": correct, "safe": safe, "spot_check": spot, "reason": d.get("reason", "")}
        self.store.decision(row)
        self.store.event("decision", i=self.n, pr=name, agent=agent, kind=c.kind, snippet=c.snippet, **row)

    # ---- learning -----------------------------------------------------------
    def maybe_learn(self, kind: str) -> None:
        if kind in self.rules and self.rules[kind].active:
            return
        pos, neg = self.store.by_kind(kind, "cut"), self.store.by_kind(kind, "keep")
        if len(pos) < config.RULE_MIN_SUPPORT or len(pos) <= self.attempts.get(kind, 0):
            return  # need more evidence; retry only after a new CUT example arrives
        self.attempts[kind] = len(pos)
        try:
            draft = gemini.write_rule(kind, pos, neg)
        except Exception as e:
            self.store.event("error", tier="rule_writer", kind=kind, error=f"{type(e).__name__}: {e}"[:300])
            return
        ok, why = reflex.validate(draft["regex"], pos, neg)
        self.store.event("rule_attempt", kind=kind, regex=draft["regex"], ok=ok, why=why,
                         latency_ms=draft["latency_ms"], cost_usd=draft["cost_usd"])
        if not ok:
            return
        old = self.rules.get(kind)
        rule = reflex.Rule(kind, draft["regex"], draft["message"], len(pos), (old.version + 1) if old else 1)
        verb = "patched" if old else "learned"
        reflex.save(rule, f"reflex {verb}: {rule.id} ({why})")
        self.rules[kind] = rule
        self.store.rule(rule)
        self.store.event("rule_born", id=rule.id, kind=kind, regex=rule.regex, message=rule.message,
                         support=rule.support, version=rule.version, why=why)

    def demote(self, rule_id: str, c: Candidate) -> None:
        rule = self.rules[c.kind]
        rule.active = False
        reflex.save(rule, f"reflex demoted: {rule_id} over-cut a hunk the tests needed")
        self.store.rule(rule)
        self.store.remember(c.kind, "keep", c.snippet, None)
        self.attempts[c.kind] = 0
        self.store.event("rule_demoted", id=rule_id, kind=c.kind, snippet=c.snippet)
        self.maybe_learn(c.kind)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prs", default="data/prs", help="folder of PR json files (processed in name order)")
    ap.add_argument("--reset", action="store_true", help="clear events, DB rows, and learned rules first")
    ap.add_argument("--pace", type=float, default=0.0, help="seconds to pause between decisions (demo)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if config.SENTRY_DSN:
        sentry_sdk.init(dsn=config.SENTRY_DSN, traces_sample_rate=1.0, send_default_pii=False)
    if args.reset:
        for f in config.RULES.glob("*.yml"):
            f.unlink()
    store = Store(reset=args.reset)
    factory = Factory(store, args.pace)
    files = sorted(Path(args.prs).glob("*.json"))[: args.limit or None]
    store.event("run_start", prs=len(files))
    for f in files:
        with sentry_sdk.start_transaction(op="factory.pr", name=f.stem):
            factory.run_pr(json.loads(f.read_text()), f.stem)
    store.event("run_done")
    sentry_sdk.flush()


if __name__ == "__main__":
    main()
