import { useEffect, useState } from "react";

type Tier = "reflex" | "jev" | "gemini";
type Decision = {
  i: number; tier: Tier; kind: string; verdict: "cut" | "keep"; latency_ms: number;
  reason: string; snippet: string; safe: boolean | null; rule_id: string | null; agent: string;
};
type State = {
  running: boolean;
  prs: { total: number; done: number; rejected: number; current: string | null };
  tiers: Record<Tier, number>; cut: number; kept: number; unsafe_cuts: number;
  timer_ms: number | null; recent: Decision[];
  series: { i: number; tier: Tier; ms: number; cost: number; spot: boolean }[];
  cost_usd: number; tokens: number;
  lines: { before: number; after: number }; holdout: { before: number; after: number };
  agents: Record<string, { prs: number; before: number; after: number }>;
  kinds: Record<string, { cut: number; keep: number }>;
  rule_events: { type: string; id: string; kind: string; regex?: string; message?: string; support?: number; why?: string; snippet?: string }[];
};
type Rules = { files: Record<string, string>; log: string[] };
type Tiger = { available: boolean; rows?: number; raw_ms?: number; cagg_ms?: number; hybrid_ms?: number; compression?: number | null; hybrid?: [string, string, string, number][] };

const TIERS: { id: Tier; name: string; sub: string }[] = [
  { id: "gemini", name: "System 2", sub: "Gemini · thinks it through" },
  { id: "jev", name: "System 1", sub: "Jev · gut call" },
  { id: "reflex", name: "Reflex", sub: "learned rule · no model" },
];

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

const fmtMs = (ms: number | null) =>
  ms == null ? "—" : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : ms >= 1 ? `${ms.toFixed(0)} ms` : `${(ms * 1000).toFixed(0)} µs`;
const fmtCost = (c: number | null) => (c == null ? "—" : `$${c.toFixed(4)}`);
const pct = (a: number, b: number) => (b ? Math.round((1 - a / b) * 100) : 0);
const fmtX = (n: number | null) => (n == null ? "—" : `${n >= 10 ? n.toFixed(0) : n.toFixed(1)}×`);

function tierAvg(series: State["series"], tier: Tier, skipSpot: boolean) {
  const rows = series.filter((p) => p.tier === tier && !(skipSpot && p.spot));
  if (!rows.length) return { ms: null as number | null, cost: null as number | null };
  return {
    ms: rows.reduce((a, p) => a + p.ms, 0) / rows.length,
    cost: rows.reduce((a, p) => a + p.cost, 0) / rows.length,
  };
}

export default function App() {
  const s = usePoll<State>("/api/state", 700);
  const rules = usePoll<Rules>("/api/rules", 2000);
  const tiger = usePoll<Tiger>("/api/tiger", 4000);
  if (!s) return <div className="empty">Waiting for the factory… start <code>python -m factory.run</code></div>;

  const timerTier = s.recent[0]?.tier ?? "gemini";
  const total = s.tiers.reflex + s.tiers.jev + s.tiers.gemini;
  const newest = s.rule_events[0];

  const jev = tierAvg(s.series, "jev", true);
  const gemini = tierAvg(s.series, "gemini", false);
  const faster = jev.ms != null && gemini.ms != null && jev.ms > 0 ? gemini.ms / jev.ms : null;
  const cheaper = jev.cost != null && gemini.cost != null && jev.cost > 0 ? gemini.cost / jev.cost : null;

  return (
    <div className="page">
      <header>
        <div>
          <h1>Muscle Memory</h1>
          <p className="tag">A software factory that turns slow thinking into reflexes</p>
        </div>
        <div className={`live ${s.running ? "on" : ""}`}>{s.running ? "● LIVE" : "idle"}</div>
      </header>

      <section className="headlines">
        <div className={`headline ${s.holdout.after <= s.holdout.before ? "good" : "cut"}`}>
          <div className="headline-n">{s.holdout.before} → {s.holdout.after}</div>
          <div className="headline-l">hidden-test failures</div>
        </div>
        <div className={`headline ${s.unsafe_cuts === 0 ? "good" : "cut"}`}>
          <div className="headline-n">{s.unsafe_cuts}</div>
          <div className="headline-l">unsafe cuts shipped</div>
        </div>
      </section>

      <section className="strip">
        <Step n={Object.keys(s.agents).length || "—"} label="coding agents" />
        <Arrow />
        <Step n={`${s.prs.done}/${s.prs.total}`} label={`PRs through the gate${s.prs.rejected ? ` · ${s.prs.rejected} failed tests` : ""}`} />
        <Arrow />
        <Step n={s.cut} label="slop cut" accent="cut" />
        <Step n={s.kept} label="kept" />
        <Arrow />
        <Step n={`${pct(s.lines.after, s.lines.before)}%`} label={`less code · ${s.lines.before}→${s.lines.after} lines`} accent="good" />
      </section>

      <section className="hero">
        <div className={`timer t-${timerTier}`}>
          <div className="timer-label">time per decision (last 8)</div>
          <div className="timer-num">{fmtMs(s.timer_ms)}</div>
          <div className="mix">
            {TIERS.map((t) => (
              <div key={t.id} className={`mixbar t-${t.id}`} style={{ flex: s.tiers[t.id] || 0.0001 }} title={t.name} />
            ))}
          </div>
          <div className="mix-legend">
            {TIERS.map((t) => <span key={t.id} className={`c-${t.id}`}>{t.name} {total ? Math.round((s.tiers[t.id] / total) * 100) : 0}%</span>)}
          </div>
        </div>
        <Chart series={s.series} />
        <div className="kpis">
          <Kpi label="spend" value={`$${s.cost_usd.toFixed(4)}`} />
          <Kpi label="tokens" value={s.tokens.toLocaleString()} />
        </div>
      </section>

      <section className="s1s2">
        <h2>System 1 vs System 2</h2>
        <div className="s1s2-grid">
          <div className="s1s2-col c-jev">
            <div className="s1s2-name">System 1 · Jev</div>
            <div className="s1s2-n">{fmtMs(jev.ms)}</div>
            <div className="s1s2-l">avg latency</div>
            <div className="s1s2-n sm">{fmtCost(jev.cost)}</div>
            <div className="s1s2-l">avg cost / decision</div>
          </div>
          <div className="s1s2-col c-gemini">
            <div className="s1s2-name">System 2 · Gemini</div>
            <div className="s1s2-n">{fmtMs(gemini.ms)}</div>
            <div className="s1s2-l">avg latency</div>
            <div className="s1s2-n sm">{fmtCost(gemini.cost)}</div>
            <div className="s1s2-l">avg cost / decision</div>
          </div>
          <div className="s1s2-punch">
            Jev is <b className="c-jev">{fmtX(faster)}</b> faster,{" "}
            <b className="c-jev">{fmtX(cheaper)}</b> cheaper.
          </div>
        </div>
      </section>

      {newest && (
        <section key={newest.id + newest.type} className={`banner ${newest.type === "rule_born" ? "born" : "demoted"}`}>
          {newest.type === "rule_born"
            ? <>New reflex learned: <b>{newest.id}</b> from {newest.support} verified calls. <code>{newest.regex}</code></>
            : <>Reflex <b>{newest.id}</b> over-cut and broke a test. Demoted, sent back to System 2.</>}
        </section>
      )}

      <section className="lanes">
        {TIERS.map((t) => (
          <div key={t.id} className={`lane t-${t.id}`}>
            <div className="lane-head">
              <div><b>{t.name}</b><span>{t.sub}</span></div>
              <div className="lane-count">{s.tiers[t.id]}</div>
            </div>
            <div className="cards">
              {s.recent.filter((d) => d.tier === t.id).slice(0, 6).map((d) => (
                <div key={d.i} className="card">
                  <div className="card-top">
                    <span className={`pill ${d.verdict}`}>{d.verdict.toUpperCase()}</span>
                    <span className="kind">{d.kind.replace("_", " ")}</span>
                    <span className="ms">{fmtMs(d.latency_ms)}</span>
                  </div>
                  <pre>{d.snippet.split("\n").slice(0, 3).join("\n")}</pre>
                  <div className="reason">{d.rule_id ? `${d.rule_id}: ` : ""}{d.reason}{d.safe === false && d.verdict === "cut" ? " · ✗ broke tests, reverted" : ""}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className="bottom">
        <div className="panel rules">
          <h2>rules/ — what the factory learned</h2>
          {rules && Object.keys(rules.files).length === 0 && <p className="dim">No reflexes yet. Needs 5 verified calls of one kind.</p>}
          {rules && Object.entries(rules.files).map(([name, text]) => (
            <pre key={name} className={text.includes("active: false") ? "inactive" : ""}><b>{name}</b>{"\n"}{text}</pre>
          ))}
          {rules && rules.log.length > 0 && <><h3>git log -- rules/</h3><pre className="log">{rules.log.join("\n")}</pre></>}
        </div>
        <div className="panel">
          <h2>Who writes the slop</h2>
          <table>
            <thead><tr><th>agent</th><th>PRs</th><th>lines</th><th>cut</th></tr></thead>
            <tbody>
              {Object.entries(s.agents).map(([a, v]) => (
                <tr key={a}><td>{a}</td><td>{v.prs}</td><td>{v.before}→{v.after}</td><td>{pct(v.after, v.before)}%</td></tr>
              ))}
            </tbody>
          </table>
          <table>
            <thead><tr><th>slop kind</th><th>cut</th><th>kept</th></tr></thead>
            <tbody>
              {Object.entries(s.kinds).map(([k, v]) => <tr key={k}><td>{k.replace("_", " ")}</td><td>{v.cut}</td><td>{v.keep}</td></tr>)}
            </tbody>
          </table>
        </div>
        <div className="panel">
          <h2>Tiger Data</h2>
          {!tiger?.available ? <p className="dim">Set DATABASE_URL to show live Tiger stats.</p> : (
            <>
              <Kpi label="decisions stored" value={String(tiger.rows)} />
              <Kpi label="raw query" value={fmtMs(tiger.raw_ms ?? null)} />
              <Kpi label="continuous aggregate" value={fmtMs(tiger.cagg_ms ?? null)} />
              <Kpi label="compression" value={tiger.compression ? `${tiger.compression.toFixed(1)}×` : "pending"} />
              <h3>nearest past decisions to the newest hunk (pgvector + time, {fmtMs(tiger.hybrid_ms ?? null)})</h3>
              <table><tbody>
                {tiger.hybrid?.map((r, i) => <tr key={i}><td>{r[0].replace("_", " ")}</td><td className={`c-${r[1]}`}>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>)}
              </tbody></table>
            </>
          )}
        </div>
      </section>
    </div>
  );
}

function Step({ n, label, accent }: { n: number | string; label: string; accent?: string }) {
  return <div className={`step ${accent ?? ""}`}><div className="step-n">{n}</div><div className="step-l">{label}</div></div>;
}
const Arrow = () => <div className="arrow">→</div>;
function Kpi({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return <div className={`kpi ${good ? "good" : ""}`}><div className="kpi-v">{value}</div><div className="kpi-l">{label}</div></div>;
}

function Chart({ series }: { series: State["series"] }) {
  const W = 520, H = 200, P = 28;
  if (!series.length) return <div className="chart dim">latency per decision appears here</div>;
  const lo = Math.log10(0.001), hi = Math.log10(30000);
  const y = (ms: number) => H - P - ((Math.log10(Math.max(ms, 0.001)) - lo) / (hi - lo)) * (H - 2 * P);
  const n = series.length;
  const x = (k: number) => P + (k / Math.max(n - 1, 1)) * (W - 2 * P);
  let cum = 0;
  const costPts = series.map((p, k) => { cum += p.cost; return [x(k), cum] as const; });
  const maxCost = cum || 1;
  return (
    <div className="chart">
      <div className="chart-title">latency per decision (log) · <span className="c-cost">cumulative spend</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        {[0.001, 1, 1000].map((v) => (
          <g key={v}><line x1={P} x2={W - P} y1={y(v)} y2={y(v)} className="grid" />
            <text x={2} y={y(v) + 4} className="axis">{v >= 1000 ? "1s" : v >= 1 ? "1ms" : "1µs"}</text></g>
        ))}
        <polyline className="cost" points={costPts.map(([px, c]) => `${px},${H - P - (c / maxCost) * (H - 2 * P)}`).join(" ")} />
        {series.map((p, k) => <circle key={p.i + (p.spot ? "s" : "")} cx={x(k)} cy={y(p.ms)} r={p.spot ? 2 : 3.5} className={`dot t-${p.tier} ${p.spot ? "spot" : ""}`} />)}
      </svg>
    </div>
  );
}
