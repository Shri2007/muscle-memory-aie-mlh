import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, "").split("#")[0].strip() or default


TARGET = ROOT / "target"
RULES = ROOT / "rules"
RUN_DIR = ROOT / "data" / "run"
EVENTS = RUN_DIR / "events.jsonl"

JEV_MODEL = env("JEV_MODEL", "jev-latest")
S2_MODEL = env("GEMINI_S2_MODEL")
EMBED_MODEL = env("GEMINI_EMBED_MODEL")
DATABASE_URL = env("DATABASE_URL")
SENTRY_DSN = env("SENTRY_DSN")

# USD per 1M tokens. Jev: input only, output free. Gemini: set to your model's price.
JEV_PRICE_IN = float(env("JEV_PRICE_IN", "0.042"))
S2_PRICE_IN = float(env("GEMINI_S2_PRICE_IN", "1.25"))
S2_PRICE_OUT = float(env("GEMINI_S2_PRICE_OUT", "10"))

RULE_MIN_SUPPORT = int(env("RULE_MIN_SUPPORT", "5"))
SPOT_CHECK_RATE = float(env("SPOT_CHECK_RATE", "0.15"))
