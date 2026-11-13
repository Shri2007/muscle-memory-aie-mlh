"""Reflex tier: learned rules stored as Semgrep YAML (pattern-regex), run here with Python re."""
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import yaml

from . import config
from .candidates import Candidate


@dataclass
class Rule:
    kind: str
    regex: str
    message: str
    support: int
    version: int = 1
    active: bool = True
    verdict: str = "cut"
    learned_at: str = ""

    @property
    def id(self) -> str:
        return f"mm-{self.kind}-v{self.version}"

    def matches(self, text: str) -> bool:
        return re.search(self.regex, text, re.MULTILINE) is not None


def path(kind: str):
    return config.RULES / f"{kind}.yml"


def load() -> dict[str, Rule]:
    rules = {}
    for f in sorted(config.RULES.glob("*.yml")):
        r = yaml.safe_load(f.read_text())["rules"][0]
        m = r["metadata"]
        rules[m["kind"]] = Rule(m["kind"], r["pattern-regex"], r["message"], m["support"], m["version"],
                                m["active"], m["verdict"], m["learned_at"])
    return rules


def save(rule: Rule, commit_msg: str) -> None:
    rule.learned_at = rule.learned_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = {k: v for k, v in asdict(rule).items() if k not in ("regex", "message")}
    doc = {"rules": [{
        "id": rule.id, "languages": ["python"], "severity": "WARNING",
        "message": rule.message, "pattern-regex": rule.regex, "metadata": meta,
    }]}
    config.RULES.mkdir(exist_ok=True)
    path(rule.kind).write_text(f"# learned by Muscle Memory from {rule.support} verified decisions\n"
                               + yaml.safe_dump(doc, sort_keys=False, width=1000))
    if config.env("RULES_GIT", "1") == "1":
        p = str(path(rule.kind).relative_to(config.ROOT))
        subprocess.run(["git", "add", p], cwd=config.ROOT, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", commit_msg, "--", p], cwd=config.ROOT, capture_output=True)


def validate(regex: str, positives: list[str], negatives: list[str]) -> tuple[bool, str]:
    try:
        rx = re.compile(regex, re.MULTILINE)
    except re.error as e:
        return False, f"bad regex: {e}"
    if any(rx.search(n) for n in negatives):
        return False, "matches a KEEP example"
    hit = sum(bool(rx.search(p)) for p in positives)
    if hit < 0.8 * len(positives):
        return False, f"matches only {hit}/{len(positives)} CUT examples"
    return True, f"matches {hit}/{len(positives)} CUT, 0/{len(negatives)} KEEP"


def match(rules: dict[str, Rule], c: Candidate) -> Rule | None:
    r = rules.get(c.kind)
    return r if r and r.active and r.matches(c.snippet) else None
