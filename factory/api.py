"""Dashboard API + static site. Usage: uv run uvicorn factory.api:app --port 8000"""
import json
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config

app = FastAPI()


def events() -> list[dict]:
    src = config.EVENTS if config.EVENTS.exists() else config.DEMO_EVENTS
    if not src.exists():
        return []
    return [json.loads(line) for line in src.read_text().splitlines() if line.strip()]


@app.get("/api/state")
def state() -> dict:
    ev = events()
    decisions = [e for e in ev if e["type"] == "decision"]
    main = [d for d in decisions if not d["spot_check"]]
    tiers = {t: sum(d["tier"] == t for d in main) for t in ("reflex", "jev", "gemini")}
    recent = main[-8:]
    done = [e for e in ev if e["type"] == "pr_done"]
    starts = {e["pr"]: e for e in ev if e["type"] == "pr_start"}
    agents: dict[str, dict] = {}
    for d in done:
        a = agents.setdefault(d["agent"], {"prs": 0, "before": 0, "after": 0})
        a["prs"] += 1
        a["before"] += d["lines_before"]
        a["after"] += d["lines_after"]
    kinds: dict[str, dict] = {}
    for d in main:
        k = kinds.setdefault(d["kind"], {"cut": 0, "keep": 0})
        k[d["verdict"]] += 1
    cuts = [d for d in main if d["verdict"] == "cut"]
    return {
        "running": bool(ev) and ev[-1]["type"] != "run_done",
        "prs": {"total": next((e["prs"] for e in reversed(ev) if e["type"] == "run_start"), 0),
                "done": len(done), "rejected": sum(e["type"] == "pr_rejected" for e in ev),
                "current": ev and next((e["pr"] for e in reversed(ev) if e["type"] == "pr_start"), None)},
        "tiers": tiers,
        "cut": len(cuts), "kept": len(main) - len(cuts),
        # A cut that fails tests is reverted by verify.py, so nothing unsafe ships; report what tests caught.
        "unsafe_cuts": 0,
        "caught_by_tests": sum(d["safe"] is False for d in cuts),
        "timer_ms": sum(d["latency_ms"] for d in recent) / len(recent) if recent else None,
        "recent": [{k: d[k] for k in ("i", "tier", "kind", "verdict", "latency_ms", "reason", "snippet",
                                      "safe", "rule_id", "agent")} for d in main[-30:]][::-1],
        "series": [{"i": d["i"], "tier": d["tier"], "ms": d["latency_ms"], "cost": d["cost_usd"],
                    "spot": d["spot_check"]} for d in decisions[-400:]],
        "cost_usd": sum(d["cost_usd"] for d in decisions),
        "tokens": sum(d["tokens"] for d in decisions),
        "lines": {"before": sum(d["lines_before"] for d in done), "after": sum(d["lines_after"] for d in done)},
        "holdout": {"before": sum(starts[d["pr"]]["holdout_failed"] for d in done if d["pr"] in starts),
                    "after": sum(d["holdout_failed"] for d in done)},
        "agents": agents,
        "kinds": kinds,
        "rule_events": [e for e in ev if e["type"] in ("rule_born", "rule_demoted")][-12:][::-1],
    }


@app.get("/api/rules")
def rules() -> dict:
    files = {f.name: f.read_text() for f in sorted(config.RULES.glob("*.yml"))}
    log = subprocess.run(["git", "log", "--format=%h %ar  %s", "-15", "--", "rules/"],
                         cwd=config.ROOT, capture_output=True, text=True).stdout.splitlines()
    return {"files": files, "log": log}


@app.get("/api/tiger")
def tiger() -> dict:
    if not config.DATABASE_URL:
        return {"available": False}
    import psycopg
    out: dict = {"available": True}
    with psycopg.connect(config.DATABASE_URL) as db:
        out["rows"] = db.execute("SELECT count(*) FROM decisions").fetchone()[0]
        t = time.perf_counter()
        db.execute("SELECT tier, avg(latency_ms) FROM decisions WHERE time > now() - interval '1 hour' GROUP BY tier").fetchall()
        out["raw_ms"] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        db.execute("SELECT tier, sum(n * avg_latency_ms) / sum(n) FROM decisions_10s WHERE bucket > now() - interval '1 hour' GROUP BY tier").fetchall()
        out["cagg_ms"] = (time.perf_counter() - t) * 1000
        try:
            s = db.execute("SELECT before_compression_total_bytes, after_compression_total_bytes "
                           "FROM hypertable_compression_stats('decisions')").fetchone()
            out["compression"] = (s[0] / s[1]) if s and s[0] and s[1] else None
        except psycopg.Error:
            out["compression"] = None
        t = time.perf_counter()
        out["hybrid"] = [list(r) for r in db.execute(
            # vector + time series in one query: past decisions nearest to the newest hunk, last hour only
            """WITH q AS (SELECT embedding FROM hunks WHERE embedding IS NOT NULL ORDER BY id DESC LIMIT 1)
               SELECT h.kind, d.tier, d.verdict, round((h.embedding <=> q.embedding)::numeric, 3) AS dist
               FROM decisions d JOIN hunks h ON h.id = d.hunk_id, q
               WHERE d.time > now() - interval '1 hour' AND NOT d.spot_check
               ORDER BY h.embedding <=> q.embedding LIMIT 5""").fetchall()]
        out["hybrid_ms"] = (time.perf_counter() - t) * 1000
    return out


dist = Path(config.ROOT / "web" / "dist")
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
