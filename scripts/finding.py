#!/usr/bin/env python3
"""Read data/run/events.jsonl and write FINDINGS.md. Safe on a missing or partial log."""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "run" / "events.jsonl"
OUT = ROOT / "FINDINGS.md"


def load() -> list[dict]:
    if not EVENTS.exists():
        return []
    rows = []
    for line in EVENTS.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def pct(part: float, whole: float) -> str:
    if not whole:
        return "—"
    value = 100 * part / whole
    if abs(value - round(value)) < 0.05:
        return f"{round(value):.0f}%"
    return f"{value:.1f}%"


def money(value) -> str:
    if value is None:
        return "—"
    if value == 0:
        return "$0"
    text = f"${value:.6f}".rstrip("0").rstrip(".")
    return text


def latency(ms) -> str:
    if ms is None:
        return "—"
    if ms >= 10:
        return f"{ms:,.0f} ms"
    return f"{ms:.1f} ms"


def n_word(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def avg(values: list[float]):
    if not values:
        return None
    return sum(values) / len(values)


def main() -> None:
    rows = load()
    decisions = [r for r in rows if r.get("type") == "decision" and not r.get("spot_check")]
    cuts: dict[tuple[str, str], int] = defaultdict(int)
    for r in decisions:
        if r.get("verdict") != "cut":
            continue
        cuts[(str(r.get("agent") or "unknown"), str(r.get("kind") or "unknown"))] += 1

    lines: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        if r.get("type") != "pr_done":
            continue
        agent = str(r.get("agent") or "unknown")
        before, after = num(r.get("lines_before")), num(r.get("lines_after"))
        if before is None or after is None:
            continue
        lines[agent][0] += before
        lines[agent][1] += after

    hold: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    started: dict[str, str] = {}
    for r in rows:
        kind = r.get("type")
        if kind == "pr_start":
            pr = r.get("pr")
            if pr is not None:
                started[str(pr)] = str(r.get("agent") or "unknown")
            agent = str(r.get("agent") or "unknown")
            failed = num(r.get("holdout_failed"))
            if failed is not None:
                hold[agent][0] += failed
        elif kind == "pr_done":
            agent = str(r.get("agent") or started.get(str(r.get("pr")), "unknown"))
            failed = num(r.get("holdout_failed"))
            if failed is not None:
                hold[agent][1] += failed

    tiers = {"jev": [], "gemini": []}
    for r in decisions:
        tier = r.get("tier")
        if tier in tiers:
            tiers[tier].append(r)

    demoted = {str(r.get("id")) for r in rows if r.get("type") == "rule_demoted" and r.get("id")}
    rules = [r for r in rows if r.get("type") == "rule_born"]

    agents = sorted(set(lines) | {a for a, _ in cuts} | set(hold))
    cut_rows = []
    for agent in agents:
        kinds = sorted(k for a, k in cuts if a == agent)
        before, after = lines.get(agent, [0.0, 0.0])
        share = pct(before - after, before)
        if not kinds:
            if agent in lines or agent in hold:
                cut_rows.append((agent, "—", 0, share))
            continue
        for kind in kinds:
            cut_rows.append((agent, kind, cuts[(agent, kind)], share))

    total_before = sum(v[0] for v in lines.values())
    total_after = sum(v[1] for v in lines.values())
    total_cuts = sum(cuts.values())
    hold_before = sum(v[0] for v in hold.values())
    hold_after = sum(v[1] for v in hold.values())
    fixed = sorted(agent for agent, (before, after) in hold.items() if after < before)

    def tier_bits(name: str) -> str:
        group = tiers[name]
        lat = avg([n for n in (num(r.get("latency_ms")) for r in group) if n is not None])
        cost = avg([n for n in (num(r.get("cost_usd")) for r in group) if n is not None])
        label = "Jev" if name == "jev" else "Gemini"
        if not group:
            return f"{label} has no decisions"
        return f"{label} averaged {latency(lat)} and {money(cost)} over {n_word(len(group), 'decision')}"

    if not rows:
        headlines = [
            "No pull requests have been cleaned yet.",
            "Hidden-test failures are 0 before and 0 after.",
            "Jev and Gemini have no decisions to compare, and no reflex rule has been learned.",
        ]
    else:
        who = " and ".join(fixed) if fixed else "no agent"
        rule_n = len(rules)
        rule_bit = n_word(rule_n, "reflex rule") + (" has" if rule_n == 1 else " have") + " been learned"
        if total_before:
            cut_line = (
                f"The factory cut {n_word(total_cuts, 'hunk')} and removed "
                f"{pct(total_before - total_after, total_before)} of the lines it cleaned "
                f"({total_before:.0f} to {total_after:.0f})."
            )
        else:
            cut_line = f"The factory cut {n_word(total_cuts, 'hunk')}. Line counts were not logged."
        if fixed:
            drop = f", with the drop on {' and '.join(fixed)}"
        else:
            drop = ""
        headlines = [
            cut_line,
            f"Hidden-test failures went from {hold_before:.0f} to {hold_after:.0f}{drop}.",
            f"{tier_bits('jev')}; {tier_bits('gemini')}. {rule_bit[0].upper() + rule_bit[1:]}.",
        ]

    lines_out = ["# Findings", "", "## Headlines", ""]
    for sentence in headlines:
        lines_out.append(f"- {sentence}")
    lines_out += ["", "## Cuts by agent and slop kind", "",
                  "| Agent | Kind | Cuts | Lines cut |", "| --- | --- | --- | --- |"]
    if cut_rows:
        for agent, kind, count, share in cut_rows:
            lines_out.append(f"| {agent} | {kind} | {count} | {share} |")
    else:
        lines_out.append("| — | — | 0 | — |")
    lines_out += ["", "## Hidden-test failures", "",
                  "| Agent | Before | After |", "| --- | --- | --- |"]
    if hold:
        for agent in sorted(hold):
            before, after = hold[agent]
            lines_out.append(f"| {agent} | {before:.0f} | {after:.0f} |")
    else:
        lines_out.append("| — | 0 | 0 |")
    lines_out += ["", "## Jev vs Gemini", "",
                  "Spot-check rows are excluded.", "",
                  "| Tier | Decisions | Avg latency | Avg cost |", "| --- | --- | --- | --- |"]
    for name, label in (("jev", "Jev"), ("gemini", "Gemini")):
        group = tiers[name]
        lat = avg([n for n in (num(r.get("latency_ms")) for r in group) if n is not None])
        cost = avg([n for n in (num(r.get("cost_usd")) for r in group) if n is not None])
        lines_out.append(f"| {label} | {len(group)} | {latency(lat)} | {money(cost)} |")
    lines_out += ["", "## Rules learned", ""]
    if not rules:
        lines_out.append("No rules learned.")
    for rule in rules:
        rid = str(rule.get("id") or "unknown")
        status = " demoted" if rid in demoted else ""
        support = rule.get("support")
        support_s = "—" if support is None else str(support)
        regex = rule.get("regex") or ""
        lines_out.append(f"- `{rid}`{status} — support {support_s}")
        lines_out.append("")
        lines_out.append("```")
        lines_out.append(str(regex))
        lines_out.append("```")
        lines_out.append("")
    OUT.write_text("\n".join(lines_out).rstrip() + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
