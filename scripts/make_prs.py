"""Have 3 coding agents implement every ticket. Output: data/prs/<agent>__<ticket>.json

Agents: Gemini models from AGENT_MODELS (comma list), plus a DigitalOcean Serverless Inference
model if DO_INFERENCE_KEY + DO_AGENT_MODEL are set. Usage: uv run scripts/make_prs.py [--tickets T01,T02]
"""
import argparse
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from factory import config  # noqa: E402

# The instruction people actually give coding agents. It's also what produces slop.
SYSTEM = """You are a senior Python engineer working in an existing repo. Implement the ticket.
Write production-ready, robust code with helpful comments and defensive error handling.
Return ONLY JSON: {"path": "<file path from the ticket>", "content": "<full file content>"}"""

MONEY = (config.TARGET / "ledger" / "money.py").read_text()


def prompt(tid: str) -> str:
    ticket = (config.TARGET / "tickets" / f"{tid}.md").read_text()
    tests = (config.TARGET / "tickets" / f"test_{tid}.py").read_text()
    return f"{SYSTEM}\n\nTicket {tid}:\n{ticket}\nExisting ledger/money.py:\n```python\n{MONEY}```\n\nTests it must pass:\n```python\n{tests}```"


def parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    d = json.loads(m.group(0))
    return {d["path"]: d["content"]}


def gemini_agent(model: str):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=config.env("GEMINI_API_KEY"))

    def run(tid: str) -> dict:
        r = client.models.generate_content(model=model, contents=prompt(tid),
                                           config=types.GenerateContentConfig(response_mime_type="application/json"))
        return parse(r.text)
    return run


def do_agent(model: str):
    key = config.env("DO_INFERENCE_KEY")

    def run(tid: str) -> dict:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt(tid)}]}).encode()
        req = urllib.request.Request("https://inference.do-ai.run/v1/chat/completions", data=body,
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        out = json.load(urllib.request.urlopen(req, timeout=120))
        return parse(out["choices"][0]["message"]["content"])
    return run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickets", default="")
    ap.add_argument("--out", default="data/prs")
    args = ap.parse_args()
    tickets = args.tickets.split(",") if args.tickets else sorted(p.stem for p in (config.TARGET / "tickets").glob("T*.md"))
    agents = {m.strip(): gemini_agent(m.strip()) for m in config.env("AGENT_MODELS").split(",") if m.strip()}
    if config.env("DO_INFERENCE_KEY") and config.env("DO_AGENT_MODEL"):
        agents["do-" + config.env("DO_AGENT_MODEL")] = do_agent(config.env("DO_AGENT_MODEL"))
    if not agents:
        sys.exit("Set AGENT_MODELS (and optionally DO_INFERENCE_KEY + DO_AGENT_MODEL) in .env")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def job(agent_tid):
        agent, tid = agent_tid
        try:
            files = agents[agent](tid)
            name = f"{re.sub(r'[^a-z0-9.-]+', '-', agent.lower())}__{tid}"
            (out / f"{name}.json").write_text(json.dumps({"agent": agent, "ticket": tid, "files": files}, indent=1))
            return f"ok   {name}"
        except Exception as e:
            return f"FAIL {agent} {tid}: {type(e).__name__}: {str(e)[:150]}"

    with ThreadPoolExecutor(8) as pool:
        for line in pool.map(job, [(a, t) for a in agents for t in tickets]):
            print(line)


if __name__ == "__main__":
    main()
