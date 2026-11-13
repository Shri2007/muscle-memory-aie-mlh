"""Dashboard API + static site. Usage: uv run uvicorn factory.api:app --port 8000"""
import json
import secrets
import threading
import subprocess
import time
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from fastapi.staticfiles import StaticFiles

from . import config

if config.SENTRY_DSN:
    sentry_sdk.init(dsn=config.SENTRY_DSN, traces_sample_rate=1.0, send_default_pii=False)

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



GAME_ROUNDS = json.loads(Path(__file__).with_name("game_rounds.json").read_text())
games: dict[str, dict] = {}
game_lock = threading.RLock()


class JoinGame(BaseModel):
    name: str = Field(min_length=1, max_length=24)


class HostGame(BaseModel):
    host_token: str


class GameAnswer(BaseModel):
    player_id: str
    choice: Literal["junk", "needed"]


def room(code: str) -> dict:
    if code not in games:
        raise HTTPException(404, "Room not found. Check the code.")
    g = games[code]
    if g["phase"] == "question" and (time.monotonic() >= g["deadline"] or
            len(g["answers"]) == len(g["players"])):
        g["phase"] = "reveal"
    return g


def begin_round(g: dict) -> None:
    g.update(phase="question", answers={}, deadline=time.monotonic() + 10)


@app.post("/api/game/host")
def game_host() -> dict:
    with game_lock:
        code = str(secrets.randbelow(900000) + 100000)
        while code in games:
            code = str(secrets.randbelow(900000) + 100000)
        token = secrets.token_urlsafe(32)
        games[code] = dict(host_token=token, phase="lobby", players={}, answers={}, index=0, deadline=0)
        return dict(code=code, host_token=token)


@app.post("/api/game/{code}/join")
def game_join(code: str, body: JoinGame) -> dict:
    with game_lock:
        g = room(code)
        if g["phase"] != "lobby":
            raise HTTPException(409, "This game has already started.")
        name = body.name.strip()
        if not name:
            raise HTTPException(422, "Enter your name.")
        player_id = secrets.token_urlsafe(24)
        g["players"][player_id] = dict(name=name, score=0)
        return dict(player_id=player_id)


@app.post("/api/game/{code}/start")
def game_start(code: str, body: HostGame) -> dict:
    with game_lock:
        g = room(code)
        if not secrets.compare_digest(body.host_token, g["host_token"]):
            raise HTTPException(403, "Only the host can do that.")
        if g["phase"] != "lobby" or not g["players"]:
            raise HTTPException(409, "Start from the lobby with at least one player.")
        begin_round(g)
        return dict(ok=True)


@app.post("/api/game/{code}/next")
def game_next(code: str, body: HostGame) -> dict:
    with game_lock:
        g = room(code)
        if not secrets.compare_digest(body.host_token, g["host_token"]):
            raise HTTPException(403, "Only the host can do that.")
        if g["phase"] != "reveal":
            raise HTTPException(409, "Wait for the answer.")
        if g["index"] == len(GAME_ROUNDS) - 1:
            g["phase"] = "final"
        else:
            g["index"] += 1
            begin_round(g)
        return dict(ok=True)


@app.post("/api/game/{code}/answer")
def game_answer(code: str, body: GameAnswer) -> dict:
    with game_lock:
        g = room(code)
        if body.player_id not in g["players"]:
            raise HTTPException(403, "Join this game first.")
        if g["phase"] != "question" or body.player_id in g["answers"]:
            raise HTTPException(409, "Your answer is locked or time is up.")
        elapsed = max(0, 10 - (g["deadline"] - time.monotonic()))
        points = 500 + round(500 * (1 - elapsed / 10)) if body.choice == GAME_ROUNDS[g["index"]]["answer"] else 0
        g["answers"][body.player_id] = dict(choice=body.choice, seconds=round(elapsed, 2), points=points)
        g["players"][body.player_id]["score"] += points
        room(code)
        return dict(ok=True)


@app.get("/api/game/{code}")
def game_state(code: str, player_id: str = "") -> dict:
    with game_lock:
        g = room(code)
        reveal = g["phase"] == "reveal"
        ranked = sorted(g["players"].items(), key=lambda item: -item[1]["score"])
        ranking = [dict(name=p["name"], score=p["score"], rank=i+1) for i, (_, p) in enumerate(ranked)]
        own = next((dict(score=p["score"], rank=i+1) for i, (pid, p) in enumerate(ranked) if pid == player_id), None)
        vote = g["answers"].get(player_id)
        if own is not None:
            own["answered"] = vote is not None
            if reveal:
                own.update(vote or dict(choice=None, seconds=None, points=0))
        r = GAME_ROUNDS[g["index"]]
        result = dict(phase=g["phase"], players=[dict(name=p["name"]) for p in g["players"].values()],
                      round=g["index"]+1, total=len(GAME_ROUNDS),
                      seconds_left=max(0, g["deadline"]-time.monotonic()) if g["phase"] == "question" else 0,
                      top5=ranking[:5] if g["phase"] in ("reveal", "final") else [], me=own)
        if g["phase"] in ("question", "reveal"):
            result.update(code=r["code"], plain=r["plain"])
        if reveal:
            n = len(g["answers"])
            result.update(answer=r["answer"], why=r["why"], jev_ms=r["jev_ms"],
                          votes={c: round(100 * sum(a["choice"] == c for a in g["answers"].values()) / n) if n else 0 for c in ("junk", "needed")},
                          fastest=min((a["seconds"] for a in g["answers"].values()), default=None))
        return result


dist = Path(config.ROOT / "web" / "dist")
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
