import { useEffect, useState } from "react";
import "./game.css";

type Board = { name: string; score: number; rank: number };
type GameState = {
  phase: "lobby" | "question" | "reveal" | "final"; players: { name: string }[];
  round: number; total: number; seconds_left: number; code?: string; plain?: string;
  answer?: string; why?: string; jev_ms?: number; fastest?: number | null;
  votes?: Record<string, number>; top5: Board[];
  me: { score: number; rank: number; answered: boolean; choice?: string; seconds?: number | null; points?: number } | null;
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
  const [name, setName] = useState("");
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
        setRoom(result.code); setToken(result.host_token);
        sessionStorage.setItem("game-room", result.code); sessionStorage.setItem("game-host", result.host_token);
      }
      if (action === "join") {
        setPlayer(result.player_id); sessionStorage.setItem("game-player-" + room, result.player_id);
      }
      if (action === "answer") setState(s => s && s.me ? { ...s, me: { ...s.me, answered: true } } : s);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const sec = (ms: number = 70) => (ms / 1000).toFixed(2);
  const leaderboard = <ol className="game-board">{state?.top5.map(p => <li key={p.rank}><b>{p.rank}. {p.name}</b><span>{p.score.toLocaleString()} pts</span></li>)}</ol>;
  return <main className={"game " + (host ? "game-host" : "game-phone")}>
    <header className="game-header"><a href="#">Muscle Memory</a><span>{room ? "Room " + room : "Live game"}</span></header>
    <h1>Junk or Needed?</h1>
    <p className="game-intro">Can you spot the code worth keeping?</p>
    {error && <p role="alert" className="game-error">{error}</p>}
    {host && !room && <button disabled={busy} onClick={() => act("host")}>Create a room</button>}
    {host && room && !state && <button disabled={busy} onClick={() => act("host")}>Create a new room</button>}
    {!host && !player && <form onSubmit={e => { e.preventDefault(); act("join", { name }); }}>
      <label htmlFor="player-name">Your name</label>
      <input id="player-name" maxLength={24} required value={name} onChange={e => setName(e.target.value)} autoComplete="nickname" />
      <button disabled={busy || !name.trim()}>Join</button>
    </form>}
    {(host || player) && state?.phase === "lobby" && <>
      {host ? <div className="game-lobby"><div><p>Scan to join, then pick your side.</p><div className="room-code">{room}</div><a className="join-url" href={"#join/" + room}>{location.origin}/#join/{room}</a></div>
        <img width="240" height="240" alt={"Scan to join room " + room} src={"https://api.qrserver.com/v1/create-qr-code/?size=360x360&data=" + encodeURIComponent(location.origin + "/#join/" + room)} /></div>
        : <h2>You're in.</h2>}
      <h2>{state.players.length} {state.players.length === 1 ? "player" : "players"} ready</h2>
      <div className="game-players">{state.players.map((p, i) => <span key={i}>{p.name}</span>)}</div>
      {host ? <button disabled={busy || !state.players.length} onClick={() => act("start", { host_token: token })}>Start</button> : <p>Watch the big screen. Your buttons will appear here.</p>}
    </>}
    {(host || player) && state && (state.phase === "question" || state.phase === "reveal") && <>
      <div className="game-round"><span>Round {state.round} of {state.total}</span>{state.phase === "question" && <strong role="timer">{Math.ceil(state.seconds_left)} s</strong>}</div>
      <pre className="game-code"><code>{state.code}</code></pre><p className="game-plain">{state.plain}</p>
      {state.phase === "question" && <>
        <div className="game-clock"><div style={{ width: (state.seconds_left * 10) + "%" }} /></div>
        {!host && (state.me?.answered ? <h2>Answer locked. Watch the screen!</h2> : <div className="game-choices">
          <button className="junk" disabled={busy} onClick={() => act("answer", { player_id: player, choice: "junk" })}>Junk</button>
          <button className="needed" disabled={busy} onClick={() => act("answer", { player_id: player, choice: "needed" })}>Needed</button>
        </div>)}
        {host && <p className="game-plain">Junk or Needed? Choose on your phone.</p>}
      </>}
      {state.phase === "reveal" && <section className="game-reveal">
        <h2>{!host ? (state.me?.choice === state.answer ? "Right!" : state.me?.choice ? "Wrong!" : "Time ran out!") + " " : ""}{state.answer === "junk" ? "Junk" : "Needed"}</h2>
        <p className="game-plain">{state.why}</p>
        {host ? <>
          <div className="game-votes"><span className="junk">Junk {state.votes?.junk}%</span><span className="needed">Needed {state.votes?.needed}%</span></div>
          <p>Jev: {sec(state.jev_ms)} s vs fastest human: {state.fastest == null ? "No answers" : state.fastest.toFixed(1) + " s"}</p>
          {leaderboard}<button disabled={busy} onClick={() => act("next", { host_token: token })}>{state.round === state.total ? "See podium" : "Next"}</button>
        </> : <>
          <p>You: {state.me?.seconds == null ? "No answer" : state.me.seconds.toFixed(1) + " s"} · Jev: {sec(state.jev_ms)} s</p>
          <div className="game-points">+{state.me?.points || 0} points</div>
          <p>{state.me?.score.toLocaleString()} total points · Rank {state.me?.rank}</p><p>Get ready for the next round.</p>
        </>}
      </section>}
    </>}
    {(host || player) && state?.phase === "final" && <>
      <h2>That's a wrap!</h2>
      <div className="game-podium">{state.top5.slice(0, 3).map(p => <div key={p.rank} className={"place place-" + p.rank}><strong>{p.rank === 1 ? "Winner" : "#" + p.rank}</strong><h2>{p.name}</h2><p>{p.score.toLocaleString()} pts</p></div>)}</div>
      {!host && <p className="game-plain">You finished #{state.me?.rank} with {state.me?.score.toLocaleString()} points.</p>}
      {leaderboard}{host && <button disabled={busy} onClick={() => act("host")}>Play again</button>}
    </>}
  </main>;
}
