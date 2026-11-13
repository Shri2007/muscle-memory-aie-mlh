"""One call per service. Usage: uv run scripts/smoke.py [--apply-schema]"""
import json, os, sys, time, urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
results = {}

def check(name):
    def wrap(fn):
        t = time.perf_counter()
        try:
            msg = fn()
            results[name] = f"PASS ({(time.perf_counter()-t)*1000:.0f} ms) {msg or ''}"
        except Exception as e:
            results[name] = f"FAIL {type(e).__name__}: {str(e)[:200]}"
        return fn
    return wrap

def need(var):
    v = os.getenv(var, "").split("#")[0].strip()
    if not v:
        raise RuntimeError(f"{var} is empty in .env")
    return v

@check("jev")
def _():
    from typesafe_sdk import TypeSafeClient, Noul, Choice
    need("TYPESAFE_API_KEY")
    with TypeSafeClient() as c:
        r = c.system_one(
            state={"hunk": "try:\n    save(user)\nexcept Exception:\n    pass"},
            questions={
                "swallow": Noul(instructions="Does the except block in `hunk` discard the exception without handling it?"),
                "kind": Choice(instructions="What kind of code is `hunk`?",
                               criteria={"error_handling": None, "business_logic": None, "comment": None}),
            },
        )
    return f"swallow={r.nouls['swallow'].noul} kind={r.choices['kind'].choice}"

@check("gemini_s2")
def _():
    from google import genai
    c = genai.Client(api_key=need("GEMINI_API_KEY"))
    model = os.getenv("GEMINI_S2_MODEL", "").split("#")[0].strip()
    if not model:
        names = [m.name for m in c.models.list() if "pro" in m.name or "embed" in m.name]
        raise RuntimeError("GEMINI_S2_MODEL empty. Candidates: " + ", ".join(names[:12]))
    return c.models.generate_content(model=model, contents="Reply with just OK").text.strip()

@check("gemini_embed")
def _():
    from google import genai
    from google.genai import types
    c = genai.Client(api_key=need("GEMINI_API_KEY"))
    r = c.models.embed_content(model=need("GEMINI_EMBED_MODEL"), contents="except Exception: pass",
                               config=types.EmbedContentConfig(output_dimensionality=768))
    return f"dims={len(r.embeddings[0].values)}"

@check("tiger")
def _():
    import psycopg
    with psycopg.connect(need("DATABASE_URL"), autocommit=True) as conn:
        if "--apply-schema" in sys.argv:
            conn.execute((Path(__file__).parent.parent / "db/schema.sql").read_text())
        ext = [r[0] for r in conn.execute("select extname from pg_extension")]
        tables = [r[0] for r in conn.execute("select tablename from pg_tables where schemaname='public'")]
    missing = {"timescaledb", "vector"} - set(ext)
    if missing:
        raise RuntimeError(f"extensions missing: {missing}")
    return f"tables={sorted(tables)}"

@check("sentry")
def _():
    import sentry_sdk
    sentry_sdk.init(dsn=need("SENTRY_DSN"))
    sentry_sdk.capture_message("muscle-memory smoke test")
    sentry_sdk.flush(5)
    return "check Sentry Issues for 'muscle-memory smoke test'"

@check("digitalocean")
def _():
    req = urllib.request.Request("https://api.digitalocean.com/v2/account",
                                 headers={"Authorization": f"Bearer {need('DIGITALOCEAN_TOKEN')}"})
    return json.load(urllib.request.urlopen(req, timeout=10))["account"]["status"]

w = max(map(len, results))
for k, v in results.items():
    print(f"{k:<{w}}  {v}")
sys.exit(0 if all(v.startswith("PASS") for v in results.values()) else 1)
