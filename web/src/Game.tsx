import { useEffect, useState } from "react";
import "./game.css";

type Racer = { name: string; seconds: number | null; correct: boolean };
type Board = { name: string; score: number; rank: number };
type GameState = {
  phase: "lobby" | "question" | "reveal" | "final"; players: { name: string }[];
  answered: number; duration: number; highlight?: number[]; racers?: Racer[]; jev_total_ms?: number; round: number; total: number; seconds_left: number; code?: string; plain?: string;
  answer?: string; why?: string; jev_ms?: number; fastest?: number | null;
  votes?: Record<string, number>; top5: Board[];
  me: { name: string; score: number; rank: number; answered: boolean; choice?: string; seconds?: number | null; points?: number } | null;
};
async function post(path: string, body = {}) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json();
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Check your entry and try again.");
  return data;
}
export default function Game({ hash }: { hash: string }) {
  const host = hash === "#host";
  const [room, setRoom] = useState(() => host ? sessionStorage.getItem("game-room") || "" : hash.split("/")[1] || "");
  const [token, setToken] = useState(() => sessionStorage.getItem("game-host") || "");
  const [player, setPlayer] = useState(() => sessionStorage.getItem("game-player-" + room) || "");
  const [name] = useState(() => ["Turbo", "Cosmic", "Sneaky", "Speedy", "Mighty", "Lucky"][Math.floor(Math.random() * 6)] + " " + ["Linter", "Debugger", "Compiler", "Reviewer", "Parser", "Refactor"][Math.floor(Math.random() * 6)] + " " + Math.floor(Math.random() * 100));
  const [state, setState] = useState<GameState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!room) return;
    let live = true;
    const poll = async () => {
      try {
        const r = await fetch("/api/game/" + room + "?player_id=" + encodeURIComponent(player));
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail);
        if (live) { setState(data); setError(""); }
      } catch (e) { if (live) setError((e as Error).message); }
    };
    poll();
    const id = setInterval(poll, 350);
    return () => { live = false; clearInterval(id); };
  }, [room, player]);
  async function act(action: string, body = {}) {
    setBusy(true); setError("");
    try {
      const result = await post("/api/game/" + (action === "host" ? "host" : room + "/" + action), body);
      if (action === "host") {
        setState(null); setRoom(result.code); setToken(result.host_token);
        sessionStorage.setItem("game-room", result.code); sessionStorage.setItem("game-host", result.host_token);
      }
      if (action === "join") {
        setPlayer(result.player_id); sessionStorage.setItem("game-player-" + room, result.player_id);
      }
      if (action === "answer") setState(s => s && s.me ? { ...s, me: { ...s.me, answered: true, seconds: result.seconds } } : s);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  const sec = (ms: number = 70) => (ms / 1000).toFixed(2);
  const board = <ol className="game-board">{state?.top5.map(p => <li key={p.rank}><span>#{p.rank}</span><b>{p.name}</b><span>{p.score.toLocaleString()}</span></li>)}</ol>;
  const right = state?.me?.choice === state?.answer;
  const timer = <div className="game-clock"><div style={{ transform: "scaleX(" + Math.max(0, (state?.seconds_left || 0) / 8) + ")" }} /></div>;
  if (!host) return <main className={"game game-phone phase-" + state?.phase + (state?.phase === "reveal" ? right ? " is-right" : " is-wrong" : "")}>
    {error && <p role="alert">{error}</p>}
    {!player ? <div className="phone-center"><span>Junk or needed?</span><h1>{name}</h1><button disabled={busy} onClick={() => act("join", { name })}>Join</button></div>
    : !state ? <div className="phone-center">Connecting</div>
    : state.phase === "lobby" ? <div className="phone-center"><h1>{state.me?.name || name}</h1><p>Watch the big screen.</p></div>
    : state.phase === "question" ? <>{timer}{state.me?.answered
      ? <div className="phone-center"><strong className="phone-symbol">✓</strong><h1>Locked in</h1><p>{state.me.seconds?.toFixed(1)} s</p></div>
      : <div className="game-choices"><button className="junk" disabled={busy} onClick={() => act("answer", { player_id: player, choice: "junk" })}>JUNK</button><button className="needed" disabled={busy} onClick={() => act("answer", { player_id: player, choice: "needed" })}>NEEDED</button></div>}</>
    : state.phase === "reveal" ? <div className="phone-center" key={state.round}><strong className="phone-symbol" aria-label={right ? "Correct" : "Wrong"}>{right ? "✓" : "✗"}</strong><p>You: {state.me?.seconds == null ? "No answer" : state.me.seconds.toFixed(1) + " s"} · Jev: {sec(state.jev_ms)} s</p><h1>+{state.me?.points || 0}</h1><strong>Rank #{state.me?.rank}</strong></div>
    : <div className="phone-center"><span>Your rank</span><h1 className="final-rank">#{state.me?.rank}</h1><strong>{state.me?.score.toLocaleString()} points</strong></div>}
  </main>;
  return <main className={"game game-host phase-" + state?.phase}>
    {error && <p role="alert" className="game-error">{error}</p>}
    {!state ? <div className="phone-center"><h1>Junk or needed?</h1><button disabled={busy} onClick={() => act("host")}>{room ? "Create a new room" : "Create a room"}</button></div>
    : state.phase === "lobby" ? <>
      <h1 className="lobby-title">Junk or needed? Scan to play.</h1>
      <div className="game-lobby"><div className="join-panel"><img alt={"Scan to join room " + room} src={"https://api.qrserver.com/v1/create-qr-code/?size=360x360&data=" + encodeURIComponent(location.origin + "/#join/" + room)} /><div className="room-code">{room}</div></div>
      <div className="reviewers"><h2><strong>{state.players.length}</strong> reviewers</h2><div className="game-players">{state.players.map((p, i) => <span key={i}>{p.name}</span>)}</div></div></div>
      <button className="host-control" disabled={busy || !state.players.length} onClick={() => act("start", { host_token: token })}>Start</button>
    </> : state.phase === "question" ? <>
      {timer}<header className="game-round"><span>{state.round} / {state.total}</span><span>{state.answered} / {state.players.length} answered</span><strong role="timer">{Math.ceil(state.seconds_left)} s</strong></header>
      <div className="question-stage"><pre className="game-code"><code>{state.code?.split("\n").map((line, i) => <span key={i} className={state.highlight?.includes(i + 1) ? "suspect" : ""}>{line || " "}</span>)}</code></pre><p className="game-plain">{state.plain}</p></div>
    </> : state.phase === "reveal" ? <section className="game-reveal" key={state.round}>
      <h1 className={"answer-stamp " + state.answer}>{state.answer?.toUpperCase()}</h1>
      <div className="race-lanes"><RaceLane name="Jev" seconds={(state.jev_ms || 70) / 1000} correct jev />{state.racers?.map((r, i) => <RaceLane key={i} {...r} />)}</div>
      <p className="race-times">Jev: {sec(state.jev_ms)} s. Fastest human: {state.fastest == null ? "No answers" : state.fastest.toFixed(1) + " s"}.</p>
      <p className="game-why">{state.why}</p>{board}<button className="host-control" disabled={busy} onClick={() => act("next", { host_token: token })}>{state.round === state.total ? "Podium" : "Next"}</button>
    </section> : <>
      <h1 className="lobby-title">The reviewers</h1><div className="final-stage"><div className="game-podium">{state.top5.slice(0, 3).map(p => <div key={p.rank} className={"place place-" + p.rank}><strong>#{p.rank}</strong><h2>{p.name}</h2><p>{p.score.toLocaleString()}</p></div>)}</div><aside className="jev-finish"><h2>Jev</h2><p>Jev would have scored {state.total}/{state.total} in {sec(state.jev_total_ms)} s total.</p><a href="#">Watch it work</a></aside></div>
      <button className="host-control" disabled={busy} onClick={() => act("host")}>Play again</button>
    </>}
  </main>;
}

function RaceLane({ name, seconds, correct, jev = false }: Racer & { jev?: boolean }) {
  const duration = jev ? .07 : seconds == null ? 1 : Math.min(3, Math.max(1, seconds));
  return <div className={"race-lane " + (jev ? "race-jev" : correct ? "race-correct" : "race-wrong")}>
    <b>{name}</b><div className="race-track"><div className="race-distance" style={{ width: correct ? "100%" : seconds == null ? "5%" : "65%" }}><span className="race-runner" style={{ animationDuration: duration + "s" }}>{correct ? "✓" : "✗"}</span></div></div><span>{seconds == null ? "No answer" : seconds.toFixed(2) + " s"}</span>
  </div>;
}
