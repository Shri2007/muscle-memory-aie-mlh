import { useEffect, useState } from "react";

type Tier = "reflex" | "jev" | "gemini";
type Decision = {
  i: number; tier: Tier; kind: string; verdict: "cut" | "keep"; latency_ms: number;
  reason: string; snippet: string; safe: boolean | null; rule_id: string | null; agent: string;
};
type RuleEvent = { type: string; id: string; kind: string; regex?: string; message?: string; support?: number; why?: string; snippet?: string };
type State = {
  running: boolean;
  prs: { total: number; done: number; rejected: number; current: string | null };
  tiers: Record<Tier, number>; cut: number; kept: number; unsafe_cuts: number; caught_by_tests?: number;
  timer_ms: number | null; recent: Decision[];
  series: { i: number; tier: Tier; ms: number; cost: number; spot: boolean }[];
  cost_usd: number; tokens: number;
  lines: { before: number; after: number }; holdout: { before: number; after: number };
  agents: Record<string, { prs: number; before: number; after: number }>;
  kinds: Record<string, { cut: number; keep: number }>;
  rule_events: RuleEvent[];
};
type Rules = { files: Record<string, string>; log: string[] };
type Tiger = { available: boolean; rows?: number; raw_ms?: number; cagg_ms?: number; hybrid_ms?: number; compression?: number | null; hybrid?: [string, string, string, number][] };

const NONE = "-";

const STEPS: { id: Tier; name: string; who: string; does: string }[] = [
  { id: "gemini", name: "Expert AI", who: "Gemini", does: "Takes the hard calls, double-checks the others, and writes the habits." },
  { id: "jev", name: "Gut instinct", who: "Jev, a System One model", does: "Makes most calls in a flash. Unsure ones go to the expert." },
  { id: "reflex", name: "Habit", who: "a rule it wrote itself", does: "Proven right 5 times. No AI needed." },
];
const STEP_NAME: Record<string, string> = { gemini: "Expert AI", jev: "Gut instinct", reflex: "Habit" };

const THING: Record<string, string> = {
  restating_comment: "a comment that just repeats the code",
  swallowed_exception: "code that hides errors",
  redundant_guard: "a safety check",
  debug_print: "a leftover debug print",
};
const HABIT: Record<string, string> = {
  restating_comment: "Delete comments that just repeat the code",
  swallowed_exception: "Remove code that hides errors",
  redundant_guard: "Remove safety checks nothing needs",
  debug_print: "Delete leftover debug prints",
};
const KEPT: Record<string, string> = {
  restating_comment: "a comment",
  swallowed_exception: "an error handler",
  redundant_guard: "a safety check",
  debug_print: "a print statement",
};
const thing = (kind: string) => THING[kind] ?? kind.replace(/_/g, " ");
const habit = (kind: string) => HABIT[kind] ?? `Remove ${thing(kind)}`;

function usePoll<T>(url: string, ms: number): T | null {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    let live = true;
    const tick = () => fetch(url).then((r) => r.json()).then((d) => live && setData(d)).catch(() => {});
    tick();
    const id = setInterval(tick, ms);
    return () => { live = false; clearInterval(id); };
  }, [url, ms]);
  return data;
}

const fmtMs = (ms: number | null | undefined) =>
  ms == null ? NONE : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : ms >= 1 ? `${ms.toFixed(0)} ms` : `${(ms * 1000).toFixed(0)} µs`;
function fmtSec(ms: number | null | undefined) {
  if (ms == null) return NONE;
  const s = ms / 1000;
  if (s >= 1) return `${s.toFixed(1)} s`;
  if (s >= 0.01) return `${s.toFixed(2)} s`;
  if (s <= 0) return "0 s";
  return `${s.toFixed(Math.min(8, -Math.floor(Math.log10(s))))} s`;
}
function fmtCost(c: number | null) {
  if (c == null) return NONE;
  if (c === 0) return "free";
  return `$${c.toFixed(Math.min(8, Math.max(2, -Math.floor(Math.log10(c)))))}`;
}
const pct = (a: number, b: number) => (b ? Math.round((1 - a / b) * 100) : 0);
const times = (slow: number | null, fast: number | null) =>
  slow != null && fast != null && fast > 0 ? Math.round(slow / fast).toLocaleString() : null;

function stepAvg(series: State["series"], tier: Tier) {
  // Expert AI double-checks are real Gemini calls, so they count toward its speed.
  const rows = series.filter((p) => p.tier === tier && (tier === "gemini" || !p.spot));
  if (!rows.length) return { ms: null as number | null, cost: null as number | null };
  return {
    ms: rows.reduce((a, p) => a + p.ms, 0) / rows.length,
    cost: rows.reduce((a, p) => a + p.cost, 0) / rows.length,
  };
}

// Jev's reason is a list of scores like "ticket_requires=0.19, function_relies=0.87"
function why(d: Decision): string {
  if (d.tier === "reflex") return "";
  if (d.tier === "gemini") return "";
  const p: Record<string, number> = {};
  for (const m of d.reason.matchAll(/(\w+)=([\d.]+)/g)) p[m[1]] = Number(m[2]);
  if (d.verdict === "keep") {
    if (d.kind === "redundant_guard") return (p.ticket_requires ?? 0) >= (p.function_relies ?? 0) ? "the ticket requires it" : "the code depends on it";
    if (d.kind === "restating_comment") return "it explains why, not just what";
    if (d.kind === "swallowed_exception") return (p.ticket_wants_silence ?? 0) > 0.7 ? "the ticket asks to ignore these errors" : "it reports the error properly";
    if (d.kind === "debug_print") return "the ticket asks for this output";
  } else if (d.kind === "redundant_guard") return "nothing needs it";
  return "";
}

function dedent(snippet: string) {
  const lines = snippet.split("\n").filter((l) => l.trim());
  const pad = Math.min(...lines.map((l) => l.length - l.trimStart().length));
  return lines.map((l) => l.slice(pad));
}

export default function App() {
  const s = usePoll<State>("/api/state", 700);
  const rules = usePoll<Rules>("/api/rules", 2000);
  const tiger = usePoll<Tiger>("/api/tiger", 4000);

  const total = s ? s.tiers.reflex + s.tiers.jev + s.tiers.gemini : 0;
  const has = !!s && total > 0;
  const events = s?.rule_events ?? [];
  const latest = s?.recent[0];
  const avg = Object.fromEntries(STEPS.map((st) => [st.id, s ? stepAvg(s.series, st.id) : { ms: null, cost: null }])) as Record<Tier, { ms: number | null; cost: number | null }>;
  const jump1 = times(avg.gemini.ms, avg.jev.ms);
  const jump2 = times(avg.jev.ms, avg.reflex.ms);

  return (
    <div className="page">
      <header className="hero">
        <div className="hero-text">
          <h1>Watch an AI code cleaner learn to work <em>without</em> AI.</h1>
          <p className="sub">
            AI agents write sloppy code. A fast AI makes most cleanup calls, an expert AI takes the hard ones, and proven calls become free habits.
          </p>
        </div>
        <Status s={s} has={has} />
      </header>

      <section className="ladder" aria-label="How a decision gets faster">
        {STEPS.map((st, k) => (
          <div key={st.id} className="ladder-cell">
            <div className={`rung t-${st.id} ${latest?.tier === st.id && s?.running ? "active" : ""}`}>
              <div className="rung-name">{st.name}</div>
              <div className="rung-who">{st.who}</div>
              <div className="rung-time">{st.id === "reflex" && avg.reflex.ms != null ? "instant" : fmtSec(avg[st.id].ms)}</div>
              <div className="rung-meta">
                <span>{st.id === "reflex" && avg.reflex.ms != null ? `${fmtSec(avg.reflex.ms)} per call` : "per decision"}</span>
                <span>{fmtCost(avg[st.id].cost)}{avg[st.id].cost ? " each" : ""}</span>
              </div>
              <p className="rung-does">{st.does}</p>
              <div className="rung-count"><b>{s ? s.tiers[st.id] : NONE}</b> decisions made here{st.id === "gemini" && s ? `, ${s.series.filter((p) => p.spot).length} double-checks` : ""}</div>
            </div>
            {k < 2 && (
              <div className="jump" aria-hidden>
                <span className="arrow">→</span>
                <span className="jump-x">{k === 0 ? (jump1 ? `${jump1}× faster` : "faster") : (jump2 ? "no AI at all" : "no AI")}</span>
              </div>
            )}
          </div>
        ))}
      </section>

      <section className="main">
        <div className="panel feed">
          <h2>{s?.running ? "Happening now" : "What it just did"}</h2>
          {!has ? (
            <div className="idle">
              <p className="idle-h">Start a run to watch it learn.</p>
              <p className="dim">Each decision shows up here in plain English, with the code it was about.</p>
              <code>uv run python -m factory.run --prs data/seed --reset --pace 0.6</code>
              {!s && <p className="dim">Waiting for the server on port 8000.</p>}
            </div>
          ) : (
            <ol className="items">
              {s!.recent.slice(0, 6).map((d) => <Item key={d.i} d={d} />)}
            </ol>
          )}
        </div>

        <div className="side">
          <div className="panel">
            <h2>Just learned</h2>
            {events.length === 0 ? (
              <p className="dim">No habits yet. One forms after 5 proven-right calls of the same kind.</p>
            ) : (
              <>
                <Lesson key={events[0].id + events[0].type} e={events[0]} big />
                {events.slice(1, 3).map((e) => <Lesson key={e.id + e.type} e={e} />)}
              </>
            )}
          </div>

          <div className="panel">
            <h2>Did it break anything?</h2>
            <div className="results">
              <Result n={s ? String(s.unsafe_cuts) : NONE} label="broken changes shipped" tone={s ? (s.unsafe_cuts === 0 ? "good" : "bad") : ""} />
              <Result n={s?.caught_by_tests != null ? String(s.caught_by_tests) : NONE} label="bad cuts caught and undone" />
              <Result n={has ? `${s!.holdout.before} → ${s!.holdout.after}` : NONE} label="hidden-test failures" tone={has && s!.holdout.after < s!.holdout.before ? "good" : ""} />
              <Result n={has && s!.lines.before ? `${pct(s!.lines.after, s!.lines.before)}%` : NONE} label="less code" />
            </div>
            <p className="note">Every cut is checked by running the real tests plus hidden tests the AI never sees. Anything that breaks is undone.</p>
          </div>
        </div>
      </section>

      <section className="details">
        <details>
          <summary>Speed of every decision</summary>
          {s ? <Chart series={s.series} /> : <p className="dim">{NONE}</p>}
          <div className="kpi-row">
            <Kpi label="decisions" value={s ? String(total) : NONE} />
            <Kpi label="removed / kept" value={s ? `${s.cut} / ${s.kept}` : NONE} />
            <Kpi label="total AI spend" value={s ? `$${s.cost_usd.toFixed(4)}` : NONE} />
            <Kpi label="tokens" value={s ? s.tokens.toLocaleString() : NONE} />
          </div>
        </details>

        <details>
          <summary>The habits as rule files, with their git history</summary>
          {(!rules || Object.keys(rules.files).length === 0) && <p className="dim">No rule files yet.</p>}
          <div className="rulefiles">
            {rules && Object.entries(rules.files).map(([name, text]) => (
              <pre key={name} className={text.includes("active: false") ? "inactive" : ""}><b>{name}</b>{"\n"}{text}</pre>
            ))}
          </div>
          {rules && rules.log.length > 0 && <><h3>git log -- rules/</h3><pre className="log">{rules.log.join("\n")}</pre></>}
        </details>

        <details>
          <summary>Which coding agent wrote the sloppy code</summary>
          <div className="tables">
            <table>
              <thead><tr><th>coding agent</th><th>changes</th><th>lines</th><th>removed</th></tr></thead>
              <tbody>
                {s && Object.entries(s.agents).map(([a, v]) => (
                  <tr key={a}><td>{a === "seed" ? "seed (hand-written)" : a}</td><td>{v.prs}</td><td>{v.before} → {v.after}</td><td>{pct(v.after, v.before)}%</td></tr>
                ))}
              </tbody>
            </table>
            <table>
              <thead><tr><th>what it found</th><th>removed</th><th>kept</th></tr></thead>
              <tbody>
                {s && Object.entries(s.kinds).map(([k, v]) => <tr key={k}><td>{thing(k)}</td><td>{v.cut}</td><td>{v.keep}</td></tr>)}
              </tbody>
            </table>
          </div>
          {s && <p className="dim">{s.prs.done} code changes cleaned{s.prs.rejected ? `, ${s.prs.rejected} rejected because their own tests failed` : ""}.</p>}
        </details>

        <details>
          <summary>Where decisions are stored (Tiger Data)</summary>
          {!tiger?.available ? <p className="dim">Set DATABASE_URL to show live Tiger Data stats.</p> : (
            <>
              <div className="kpi-row">
                <Kpi label="decisions stored" value={tiger.rows == null ? NONE : String(tiger.rows)} />
                <Kpi label="raw query" value={fmtMs(tiger.raw_ms)} />
                <Kpi label="continuous aggregate" value={fmtMs(tiger.cagg_ms)} />
                <Kpi label="compression" value={tiger.compression ? `${tiger.compression.toFixed(1)}×` : NONE} />
              </div>
              <h3>Most similar past decisions to the newest one (pgvector + time series, {fmtMs(tiger.hybrid_ms)})</h3>
              <table><tbody>
                {tiger.hybrid?.map((r, i) => (
                  <tr key={i}><td>{thing(r[0])}</td><td className={`c-${r[1]}`}>{STEP_NAME[r[1]] ?? r[1]}</td><td>{r[2] === "cut" ? "removed" : "kept"}</td><td>{r[3]}</td></tr>
                ))}
              </tbody></table>
            </>
          )}
        </details>
      </section>
    </div>
  );
}

function Status({ s, has }: { s: State | null; has: boolean }) {
  if (!s) return <div className="status">Connecting</div>;
  if (s.running) {
    const writer = s.prs.current?.split("__")[0];
    return (
      <div className="status on">
        <span className="pulse" aria-hidden />
        <div>
          <b>Live</b>
          <span>cleaning change {Math.min(s.prs.done + 1, s.prs.total)} of {s.prs.total}{writer ? ` by ${writer}` : ""}</span>
        </div>
      </div>
    );
  }
  return <div className="status">{has ? <><b>Run finished</b><span>{s.prs.done} code changes cleaned</span></> : <b>Not running</b>}</div>;
}

function Item({ d }: { d: Decision }) {
  const w = why(d);
  const verb = d.verdict === "cut" ? "Removed" : "Kept";
  const what = d.verdict === "keep" ? KEPT[d.kind] ?? thing(d.kind) : thing(d.kind);
  return (
    <li className={`item t-${d.tier}`}>
      <div className="item-top">
        <span className="who">{STEP_NAME[d.tier]}</span>
        <span className="time">{d.tier === "reflex" ? "instant" : fmtSec(d.latency_ms)}</span>
      </div>
      <p className="say">
        <b className={d.verdict === "cut" ? "v-cut" : "v-keep"}>{verb}</b> {what}{w ? `, because ${w}` : ""}.
        {d.verdict === "cut" && d.safe === true && <span className="ok"> Tests still pass.</span>}
        {d.verdict === "cut" && d.safe === false && <span className="bad"> It broke a test, so it was undone.</span>}
      </p>
      <pre>{dedent(d.snippet).slice(0, 2).join("\n")}</pre>
    </li>
  );
}

function Lesson({ e, big }: { e: RuleEvent; big?: boolean }) {
  const born = e.type === "rule_born";
  const v = Number(e.id.match(/-v(\d+)$/)?.[1] ?? 1);
  if (!big) {
    return (
      <p className={`lesson-line ${born ? "born" : "demoted"}`}>
        {born ? <><b>{v > 1 ? "Fixed habit" : "New habit"}:</b> {habit(e.kind).toLowerCase()}</> : <><b>Mistake caught:</b> a habit cut code the tests needed</>}
      </p>
    );
  }
  return (
    <div className={`lesson ${born ? "born" : "demoted"}`}>
      {born ? (
        <>
          <div className="lesson-h">{v > 1 ? "Habit fixed after a mistake" : "New habit"}</div>
          <div className="lesson-b">{habit(e.kind)}.</div>
          <div className="lesson-s">Learned from {e.support ?? NONE} proven examples. From now on this runs instantly, with no AI.</div>
        </>
      ) : (
        <>
          <div className="lesson-h">Mistake caught</div>
          <div className="lesson-b">A habit cut code the tests needed.</div>
          <div className="lesson-s">It was switched off and sent back to the Expert AI to rewrite.</div>
        </>
      )}
    </div>
  );
}

function Result({ n, label, tone }: { n: string; label: string; tone?: string }) {
  return <div className={`result ${tone ?? ""}`}><div className="result-n">{n}</div><div className="result-l">{label}</div></div>;
}
function Kpi({ label, value }: { label: string; value: string }) {
  return <div className="kpi"><div className="kpi-v">{value}</div><div className="kpi-l">{label}</div></div>;
}

function Chart({ series }: { series: State["series"] }) {
  const W = 1000, H = 240, P = 34;
  if (!series.length) return <p className="dim">The speed of each decision appears here once a run starts.</p>;
  const lo = Math.log10(0.001), hi = Math.log10(30000);
  const y = (ms: number) => H - P - ((Math.log10(Math.max(ms, 0.001)) - lo) / (hi - lo)) * (H - 2 * P);
  const n = series.length;
  const x = (k: number) => P + (k / Math.max(n - 1, 1)) * (W - 2 * P);
  let cum = 0;
  const costPts = series.map((p, k) => { cum += p.cost; return [x(k), cum] as const; });
  const maxCost = cum || 1;
  return (
    <div className="chart">
      <p className="chart-title">
        Time per decision, first to latest (log scale).{" "}
        {STEPS.map((st) => <span key={st.id} className={`c-${st.id}`}>{st.name} </span>)}
        <span className="c-cost">Total spend.</span> <span className="dim">Faint dots are double-checks by the Expert AI.</span>
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="Time per decision chart">
        {[0.001, 1, 1000].map((v) => (
          <g key={v}><line x1={P} x2={W - P} y1={y(v)} y2={y(v)} className="grid" />
            <text x={2} y={y(v) + 4} className="axis">{v >= 1000 ? "1 s" : v >= 1 ? "1 ms" : "1 µs"}</text></g>
        ))}
        <polyline className="cost" points={costPts.map(([px, c]) => `${px},${H - P - (c / maxCost) * (H - 2 * P)}`).join(" ")} />
        {series.map((p, k) => <circle key={p.i + (p.spot ? "s" : "")} cx={x(k)} cy={y(p.ms)} r={p.spot ? 2.5 : 4} className={`dot t-${p.tier} ${p.spot ? "spot" : ""}`} />)}
      </svg>
    </div>
  );
}
