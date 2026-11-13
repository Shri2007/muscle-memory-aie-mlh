# /// script
# requires-python = ">=3.12"
# dependencies = ["snowflake-connector-python", "python-dotenv"]
# ///
"""Slop report: load data/run/events.jsonl into Snowflake, summarize per agent with Cortex AI_COMPLETE.

Standalone (own deps, read-only on local files). Usage: uv run scripts/snowflake_report.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "run" / "events.jsonl"

PROMPT = (
    "You review output from AI coding agents. Write a short slop report (max 5 sentences, plain text) for agent "
    "'{agent}'. Name the slop kinds it produces most, with counts, and what the factory learned from them.\n"
    "Per-kind stats (cut = removed as slop and verified by tests): {stats}\n"
    "Rules the factory learned across all agents (born/demoted): {learned}"
)

REPORT_SQL = """
WITH k AS (
  SELECT agent, kind, COUNT(*) AS n, COUNT_IF(verdict = 'cut') AS cuts,
         COUNT_IF(verdict = 'cut' AND tier = 'reflex') AS reflex_cuts
  FROM mm_decisions WHERE NOT spot_check GROUP BY agent, kind),
a AS (
  SELECT agent, LISTAGG(kind || ': ' || cuts || ' cut of ' || n || ' seen (' || reflex_cuts || ' by learned rules)', '; ')
         WITHIN GROUP (ORDER BY cuts DESC) AS stats
  FROM k GROUP BY agent),
r AS (
  SELECT COALESCE(LISTAGG(type || ' ' || rule_id || ' [' || kind || ']', '; ') WITHIN GROUP (ORDER BY ts), 'none') AS learned
  FROM mm_rule_events)
SELECT a.agent, a.stats,
       AI_COMPLETE(%(model)s, REPLACE(REPLACE(REPLACE(%(prompt)s, '{agent}', a.agent), '{stats}', a.stats), '{learned}', r.learned))
FROM a, r ORDER BY a.agent
"""


def env(name: str, default: str = "") -> str:
    return os.getenv(name, "").split("#")[0].strip() or default


def main() -> None:
    from dotenv import load_dotenv
    import snowflake.connector

    load_dotenv(ROOT / ".env")
    events = [json.loads(line) for line in EVENTS.read_text().splitlines() if line.strip()]
    decisions = [(e.get("ts"), e.get("pr"), e.get("agent"), e.get("kind"), e.get("tier"), e.get("verdict"),
                  bool(e.get("spot_check")), e.get("safe"), e.get("correct"), e.get("rule_id"),
                  e.get("latency_ms"), e.get("tokens"), e.get("cost_usd"))
                 for e in events if e.get("type") == "decision"]
    rule_events = [(e.get("ts"), e["type"], e.get("id"), e.get("kind"), e.get("regex"))
                   for e in events if e.get("type") in ("rule_born", "rule_demoted")]
    if not decisions:
        sys.exit(f"no decision rows in {EVENTS}")

    conn = snowflake.connector.connect(
        account=env("SNOWFLAKE_ACCOUNT"), user=env("SNOWFLAKE_USER"), password=env("SNOWFLAKE_PASSWORD"),
        warehouse=env("SNOWFLAKE_WAREHOUSE") or None, database=env("SNOWFLAKE_DATABASE") or None,
        schema=env("SNOWFLAKE_SCHEMA") or None, role=env("SNOWFLAKE_ROLE") or None,
    )
    try:
        cur = conn.cursor()
        cur.execute("""CREATE OR REPLACE TABLE mm_decisions (ts FLOAT, pr STRING, agent STRING, kind STRING,
            tier STRING, verdict STRING, spot_check BOOLEAN, safe BOOLEAN, correct BOOLEAN, rule_id STRING,
            latency_ms FLOAT, tokens INT, cost_usd FLOAT)""")
        cur.execute("CREATE OR REPLACE TABLE mm_rule_events (ts FLOAT, type STRING, rule_id STRING, kind STRING, regex STRING)")
        cur.executemany("INSERT INTO mm_decisions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", decisions)
        if rule_events:
            cur.executemany("INSERT INTO mm_rule_events VALUES (%s,%s,%s,%s,%s)", rule_events)
        print(f"Loaded {len(decisions)} decisions, {len(rule_events)} rule events into Snowflake.\n")

        model = env("SNOWFLAKE_CORTEX_MODEL", "mistral-large2")
        for agent, stats, report in cur.execute(REPORT_SQL, {"model": model, "prompt": PROMPT}).fetchall():
            print(f"=== {agent} ===\n{stats}\n\n{(report or '(no response)').strip()}\n")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # standalone report: fail loudly, touch nothing else
        sys.exit(f"snowflake_report failed: {type(e).__name__}: {e}")
