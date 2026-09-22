"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Accessibility, BrainCircuit, Camera, Eye, Info, Maximize2, Radio, Sparkles, Volume2, VolumeX, Wifi, WifiOff } from "lucide-react";
import { useFlyPokerStore } from "@/lib/store";
import { FALLBACK_SNAPSHOT, type FlyPlayer, type LiveMessage, type NeuralTelemetry } from "@/lib/types";

const CasinoScene = dynamic(() => import("@/components/CasinoScene"), { ssr: false, loading: () => <div className="scene-loading">Lighting the felt…</div> });

export default function Home() {
  const [offlineReplay, setOfflineReplay] = useState(false);
  const snapshot = useFlyPokerStore((state) => state.snapshot);
  const connected = useFlyPokerStore((state) => state.connected);
  const viewMode = useFlyPokerStore((state) => state.viewMode);
  const cameraMode = useFlyPokerStore((state) => state.cameraMode);
  const selectedFlyId = useFlyPokerStore((state) => state.selectedFlyId);
  const cleanCinema = useFlyPokerStore((state) => state.cleanCinema);
  const muted = useFlyPokerStore((state) => state.muted);
  const reducedMotion = useFlyPokerStore((state) => state.reducedMotion);
  const setSnapshot = useFlyPokerStore((state) => state.setSnapshot);
  const applyMessage = useFlyPokerStore((state) => state.applyMessage);
  const setConnected = useFlyPokerStore((state) => state.setConnected);
  const setViewMode = useFlyPokerStore((state) => state.setViewMode);
  const cycleCamera = useFlyPokerStore((state) => state.cycleCamera);
  const selectFly = useFlyPokerStore((state) => state.selectFly);
  const toggleCinema = useFlyPokerStore((state) => state.toggleCinema);
  const toggleMuted = useFlyPokerStore((state) => state.toggleMuted);
  const setReducedMotion = useFlyPokerStore((state) => state.setReducedMotion);
  const events = useFlyPokerStore((state) => state.events);
  const decisions = useFlyPokerStore((state) => state.decisions);
  const telemetry = useFlyPokerStore((state) => state.telemetry);
  const selectedFly = useMemo(() => snapshot.players.find((player) => player.id === selectedFlyId) ?? snapshot.players[0], [snapshot.players, selectedFlyId]);

  useTableAudio(events.length ? events[events.length - 1]?.type : undefined, muted);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReducedMotion(query.matches);
    sync();
    query.addEventListener?.("change", sync);
    return () => query.removeEventListener?.("change", sync);
  }, [setReducedMotion]);

  useEffect(() => {
    const loadLatestReplay = () => {
      const replayApi = process.env.NEXT_PUBLIC_REPLAY_API_URL;
      if (!replayApi) return;
      fetch(`${replayApi.replace(/\/$/, "")}/replays/latest`)
        .then((response) => response.ok ? response.json() : null)
        .then((data) => {
          if (data?.snapshot) {
            setSnapshot(data.snapshot as typeof FALLBACK_SNAPSHOT);
            setOfflineReplay(true);
          }
        })
        .catch(() => undefined);
    };
    const apiUrl = process.env.NEXT_PUBLIC_API_URL;
    if (apiUrl) {
      const apiBase = apiUrl.replace(/\/$/, "");
      Promise.all([
        fetch(`${apiBase}/v1/live/snapshot`).then((response) => response.ok ? response.json() : null),
        fetch(`${apiBase}/v1/status`).then((response) => response.ok ? response.json() : null),
      ])
        .then(([data, status]) => status?.status === "offline" ? loadLatestReplay() : data ? setSnapshot(data) : loadLatestReplay())
        .catch(loadLatestReplay);
    } else {
      loadLatestReplay();
    }
    const wsUrl = process.env.NEXT_PUBLIC_LIVE_WS_URL;
    if (!wsUrl) return;
    let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      socket = new WebSocket(wsUrl);
      socket.onopen = () => {
        if (!apiUrl) { setConnected(true); setOfflineReplay(false); return; }
        fetch(`${apiUrl.replace(/\/$/, "")}/v1/status`)
          .then((response) => response.ok ? response.json() : null)
          .then((status) => {
            if (status?.status === "offline") {
              setConnected(false);
              loadLatestReplay();
              socket?.close();
              return;
            }
            setConnected(true);
            setOfflineReplay(false);
          })
          .catch(() => { setConnected(true); setOfflineReplay(false); });
      };
      socket.onmessage = (message) => {
        try { applyMessage(JSON.parse(message.data) as LiveMessage); } catch { /* ignore malformed telemetry */ }
      };
      socket.onclose = () => { setConnected(false); retry = setTimeout(connect, 3500); };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => { if (retry) clearTimeout(retry); socket?.close(); };
  }, [applyMessage, setConnected, setSnapshot]);

  return (
    <main className={`app-shell ${cleanCinema ? "cinema-mode" : ""}`}>
      <div className="film-grain" aria-hidden="true" />
      <header className="topbar">
        <div className="brand-lockup"><Sparkles className="brand-mark" size={16} /><span>FLY / POKER</span><small>AN EXPERIMENT IN WIRING</small></div>
        <div className="live-status"><span className={`live-dot ${connected ? "online" : ""}`} />{connected ? "LIVE TABLE" : offlineReplay ? "LIVE TABLE ASLEEP · REPLAY" : "DEMO TABLE"}<span className="status-divider" />{snapshot.tournament_id}</div>
        <nav className="top-actions" aria-label="Table controls">
          <button className="icon-button" aria-label="Toggle clean cinema mode" onClick={toggleCinema}><Maximize2 size={16} /></button>
          <button className="icon-button" aria-label={`Switch camera, currently ${cameraMode}`} onClick={cycleCamera} title={`Camera: ${cameraMode}`}><Camera size={16} /></button>
          <button className={`icon-button ${reducedMotion ? "active" : ""}`} aria-label={reducedMotion ? "Disable reduced motion" : "Enable reduced motion"} aria-pressed={reducedMotion} onClick={() => setReducedMotion(!reducedMotion)}><Accessibility size={16} /></button>
          <button className="icon-button" aria-label={muted ? "Unmute table" : "Mute table"} onClick={toggleMuted}>{muted ? <VolumeX size={16} /> : <Volume2 size={16} />}</button>
        </nav>
      </header>

      <section className="hero-copy" aria-labelledby="page-title">
        <p className="eyebrow"><Radio size={13} /> TABLE 01 / HAND {String(snapshot.hand_number).padStart(2, "0")}</p>
        <h1 id="page-title">Six minds.<br /><em>One table.</em></h1>
        <p className="lede">A frozen connectome. A live poker table.<br />Watch the wiring make a move.</p>
      </section>

      <section className="table-stage" aria-label="Live poker table">
        <div className="scene-wrap"><CasinoScene players={snapshot.players} currentActor={snapshot.current_actor} lastEvent={snapshot.last_event} street={snapshot.street} board={snapshot.board} pot={snapshot.pot} cameraMode={cameraMode} inspectionMode={viewMode === "inspection"} reducedMotion={reducedMotion} /></div>
        <div className="table-shadow" aria-hidden="true" />
        <div className="table-ui table-ui-left">
          <div className="signal-card" aria-live="polite"><span className="signal-kicker"><BrainCircuit size={13} /> NEURAL SIGNAL</span><strong>{snapshot.last_event}</strong><span className="mono">SEQ {String(snapshot.sequence).padStart(5, "0")} / {snapshot.street.toUpperCase()}</span></div>
        </div>
        <div className="table-ui table-ui-right">
          <div className="pot-card"><span className="signal-kicker">CURRENT POT</span><strong>{snapshot.pot.toLocaleString()} <small>CHIPS</small></strong><span className="mono">BLINDS {snapshot.blinds}</span></div>
        </div>
      </section>

      {!cleanCinema && <>
        <section className="player-rail" aria-label="Players">
          {snapshot.players.map((player) => <PlayerCard key={player.id} player={player} active={snapshot.current_actor === player.id} selected={selectedFlyId === player.id} onClick={() => selectFly(player.id)} />)}
        </section>
        <section className="bottom-deck">
          <div className="deck-tabs" role="tablist" aria-label="Spectator panels">
            <button className={viewMode === "broadcast" ? "active" : ""} onClick={() => setViewMode("broadcast")}><Camera size={15} /> Broadcast</button>
            <button className={viewMode === "inspection" ? "active" : ""} onClick={() => setViewMode("inspection")}><Eye size={15} /> Inspect fly</button>
          </div>
          {viewMode === "inspection" ? <InspectionPanel player={selectedFly} snapshot={snapshot} decision={decisions[selectedFly.id]} telemetry={telemetry[selectedFly.id]} /> : <BroadcastPanel snapshot={snapshot} />}
          <HonestyPanel mode={snapshot.mode} />
        </section>
        <PortfolioNote mode={snapshot.mode} connected={connected} />
      </>}

      <footer className="footer-note"><span><Wifi size={13} /> READ-ONLY SPECTATOR MODE / SIMULATED CHIPS</span><span><Info size={13} /> {snapshot.mode === "flybrain" ? "THE WIRING IS REAL. THE POKER IS ENGINEERED." : "DEVELOPMENT ADAPTER — NO BIOLOGICAL CLAIM"}</span><span>{connected ? "STREAM STABLE" : "LIVE TABLE ASLEEP — SHOWING LAST TABLE STATE"} {connected ? <Wifi size={13} /> : <WifiOff size={13} />}</span></footer>
    </main>
  );
}

function PortfolioNote({ mode, connected }: { mode: "simulated" | "flybrain"; connected: boolean }) {
  return <section className="portfolio-note" aria-label="Project notes">
    <div className="portfolio-note-intro">
      <span className="panel-kicker">PORTFOLIO NOTE / 01</span>
      <h2>Built as a live experiment, documented like a machine.</h2>
      <p>Fly Poker turns a frozen connectome into a spectator sport without pretending biology learned the rules. The wiring is inherited; the poker is engineered, measured, and replayable.</p>
      <a href="https://github.com/KuantumKnight/flypoker" target="_blank" rel="noreferrer">VIEW SOURCE ↗</a>
    </div>
    <div className="portfolio-note-list">
      <div className="portfolio-note-row"><span>01</span><div><strong>WIRING</strong><p>Six independent neural states share one immutable MaleCNS connectome.</p></div><b>{mode === "flybrain" ? "LIVE GPU" : "DEV ADAPTER"}</b></div>
      <div className="portfolio-note-row"><span>02</span><div><strong>RULES</strong><p>PokerKit owns legality, betting rounds, side pots, showdowns, and payouts.</p></div><b>DETERMINISTIC</b></div>
      <div className="portfolio-note-row"><span>03</span><div><strong>ARCHIVE</strong><p>Every hand becomes an event log that can be revisited after the table sleeps.</p></div><b>{connected ? "STREAMING" : "REPLAY READY"}</b></div>
    </div>
  </section>;
}

function useTableAudio(eventType: string | undefined, muted: boolean) {
  const lastEvent = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!eventType || muted || eventType === lastEvent.current) return;
    lastEvent.current = eventType;
    const AudioContextClass = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return;
    const context = new AudioContextClass();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = eventType.includes("showdown") ? "sine" : eventType.includes("cards") ? "square" : "triangle";
    oscillator.frequency.value = eventType.includes("action") ? 180 : eventType.includes("cards") ? 340 : eventType.includes("street") ? 260 : 280;
    gain.gain.setValueAtTime(0.0001, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.035, context.currentTime + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.24);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.25);
    window.setTimeout(() => void context.close(), 400);
  }, [eventType, muted]);

  useEffect(() => {
    if (muted) return;
    const AudioContextClass = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return;
    const context = new AudioContextClass();
    const gain = context.createGain();
    gain.gain.value = 0.006;
    gain.connect(context.destination);
    const low = context.createOscillator();
    const high = context.createOscillator();
    low.type = "sine";
    high.type = "triangle";
    low.frequency.value = 73.42;
    high.frequency.value = 146.83;
    low.connect(gain);
    high.connect(gain);
    low.start();
    high.start();
    void context.resume();
    return () => {
      low.stop();
      high.stop();
      void context.close();
    };
  }, [muted]);
}

function PlayerCard({ player, active, selected, onClick }: { player: FlyPlayer; active: boolean; selected: boolean; onClick: () => void }) {
  return <button className={`player-card ${active ? "active" : ""} ${selected ? "selected" : ""}`} onClick={onClick} style={{ "--accent": player.accent } as CSSProperties} aria-label={`Inspect ${player.name}, ${player.style}`}>
    <span className="player-light" /><span className="player-name">{player.name}</span><span className="player-style">{player.style}</span>
    <span className="player-cards">{player.hole_cards.map((card) => <span key={card} className={card.includes("♥") || card.includes("♦") ? "red-card" : ""}>{card}</span>)}</span>
    <span className="player-meta"><span>{player.chips.toLocaleString()}</span><span>{Math.round(player.equity * 100)}% EQ</span></span>
  </button>;
}

function BroadcastPanel({ snapshot }: { snapshot: typeof FALLBACK_SNAPSHOT }) {
  return <div className="broadcast-panel"><div><span className="panel-kicker">THE HAND</span><strong>{snapshot.board.length ? snapshot.board.join("  ") : "Waiting for the first reveal"}</strong></div><div className="broadcast-copy">Every action is decoded from a frozen connectome and a trained linear readout. The spectators see the cards; the flies only see what the table would show them.</div><a className="replay-link" href={`/replay/${snapshot.tournament_id}-${snapshot.hand_id}`}>Open replay ↗</a></div>;
}

function InspectionPanel({ player, snapshot, decision, telemetry }: { player: FlyPlayer; snapshot: typeof FALLBACK_SNAPSHOT; decision?: { features: Record<string, number>; legalActions: string[]; logits: Record<string, number>; sizing?: string }; telemetry?: NeuralTelemetry }) {
  const features = Object.entries(telemetry?.features ?? decision?.features ?? { LC10a: player.equity, LPLC1: 1 - player.equity * 0.7, LPLC2: player.activity, LC4: Math.min(1, player.activity * 0.8) });
  const legalActions = decision?.legalActions.length ? decision.legalActions : ["fold", "call", "raise"];
  const logits = Object.entries(decision?.logits ?? {});
  const activity = telemetry?.activity ?? player.activity;
  const regions = telemetry?.regions ?? { sensory: player.equity, central: player.activity, drives: 1 - player.equity, motor: activity };
  const populations = telemetry?.stimulatedPopulations ?? ["LC10a", "LPLC1", "LPLC2", "LC4"];
  const sampledCount = telemetry?.sampledNeuronCount ?? 12000;
  return <div className="inspection-panel"><div className="inspection-heading"><div><span className="panel-kicker">INSPECTING / {player.name.toUpperCase()}</span><strong>{player.style}</strong><p className="inspection-stack">STACK {player.chips.toLocaleString()} · EQUITY {Math.round(player.equity * 100)}%</p></div><span className="inspection-live"><span className="live-dot online" /> {telemetry?.mode === "flybrain" ? "MALECNS LIVE" : "LIVE"}</span></div><div className="inspection-grid"><div><span className="data-label">PUBLIC STATISTICS</span><p>VPIP <strong>{Math.round(player.vpip * 100)}%</strong><br />PFR <strong>{Math.round(player.pfr * 100)}%</strong><br />AGGRESSION <strong>{Math.round(player.aggression * 100)}%</strong></p><span className="data-label sub-label">CURRENT TELL</span><p>{player.tell}</p><span className="data-label sub-label">LEGAL ACTION MASK</span><div className="legal-mask">{legalActions.map((action) => <b key={action}>{action.toUpperCase()}</b>)}</div><span className="data-label sub-label">STIMULATED POPULATIONS</span><div className="legal-mask">{populations.map((population) => <b key={population}>{population}</b>)}</div></div><div><span className="data-label">ENCODED FEATURE PULSES</span><div className="activity-bars">{features.map(([label, value]) => <span key={label}><i style={{ width: `${Math.max(18, Number(value) * 100)}%` }} /><b>{label}</b></span>)}</div><span className="data-label sub-label">LIVE CNS SAMPLE / ~{sampledCount.toLocaleString()} POSITIONS</span><BrainSample activity={activity} regions={regions} sampledSpikes={telemetry?.sampledSpikes ?? []} /></div><div><span className="data-label">READOUT TELEMETRY</span><p>Chosen action: <strong>{player.status.toUpperCase()}</strong><br />Sizing: <strong>{decision?.sizing ?? "LEGAL CLAMP"}</strong><br />Logits: <strong>{logits.length ? logits.map(([name, value]) => `${name} ${Number(value).toFixed(2)}`).join(" · ") : "waiting"}</strong><br />Descending view: <strong>~{sampledCount.toLocaleString()} sampled positions</strong></p><span className="model-note">Sampled activity from the {snapshot.mode === "flybrain" ? "MaleCNS" : "development adapter"}; never the full brain matrix.</span></div></div></div>;
}

function BrainSample({ activity, regions, sampledSpikes }: { activity: number; regions: Record<string, number>; sampledSpikes: number[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const points = useMemo(() => {
    const generated: Array<{ x: number; y: number; region: "optic" | "central" | "descending" | "motor" }> = [];
    let seed = 0x9e3779b9;
    const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return (seed >>> 8) / 0xffffff; };
    for (let index = 0; index < 12000; index += 1) {
      const band = index / 12000;
      let region: "optic" | "central" | "descending" | "motor";
      let x = 0;
      let y = 0;
      if (band < 0.68) {
        const right = band >= 0.34;
        const angle = random() * Math.PI * 2;
        const radius = Math.sqrt(random());
        x = (right ? 358 : 122) + Math.cos(angle) * radius * 94;
        y = 69 + Math.sin(angle) * radius * 53;
        region = "optic";
      } else if (band < 0.84) {
        x = 240 + (random() - 0.5) * 66;
        y = 55 + random() * 73;
        region = "central";
      } else if (band < 0.94) {
        x = 240 + (random() - 0.5) * 32;
        y = 112 + random() * 61;
        region = "descending";
      } else {
        x = 240 + (random() - 0.5) * 88;
        y = 169 + (random() - 0.5) * 18;
        region = "motor";
      }
      generated.push({ x, y, region });
    }
    return generated;
  }, []);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const width = 480;
    const height = 205;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);
    const regionActivity = {
      optic: Math.max(0, Math.min(1, Number(regions.sensory ?? activity))),
      central: Math.max(0, Math.min(1, Number(regions.central ?? activity))),
      descending: Math.max(0, Math.min(1, Number(regions.drives ?? activity))),
      motor: Math.max(0, Math.min(1, Number(regions.motor ?? activity))),
    };
    const colors = { optic: [99, 219, 195], central: [242, 197, 107], descending: [229, 143, 176], motor: [155, 138, 251] } as const;
    context.strokeStyle = "rgba(173,225,215,.2)";
    context.lineWidth = 0.8;
    context.beginPath();
    context.moveTo(211, 70); context.bezierCurveTo(224, 75, 225, 87, 240, 93); context.bezierCurveTo(255, 87, 256, 75, 269, 70);
    context.moveTo(240, 94); context.bezierCurveTo(236, 123, 240, 145, 240, 188);
    context.stroke();
    for (const point of points) {
      const [red, green, blue] = colors[point.region];
      context.fillStyle = `rgba(${red},${green},${blue},${0.09 + regionActivity[point.region] * 0.34})`;
      context.fillRect(point.x, point.y, 1.05, 1.05);
    }
    context.shadowBlur = 7;
    context.shadowColor = "#f2c56b";
    context.fillStyle = "rgba(255,244,191,.98)";
    for (const neuronId of sampledSpikes) {
      const index = Math.max(0, Math.min(points.length - 1, Math.floor(Math.abs(neuronId) * points.length / 166700)));
      const point = points[index];
      if (point) context.fillRect(point.x - 1.2, point.y - 1.2, 3.4, 3.4);
    }
    context.shadowBlur = 0;
  }, [activity, points, regions, sampledSpikes]);
  return <div className="brain-map-wrap"><canvas ref={canvasRef} className="brain-sample-canvas" role="img" aria-label="Live sampled activity view of approximately 12,000 neuron positions from the full MaleCNS network" /><div className="brain-map-caption"><span>● LIVE FIRING / {sampledSpikes.length} SPIKES</span><span>MALECNS · SAMPLE PROJECTION</span></div><div className="brain-legend"><span><i className="legend-optic" />OPTIC LOBES</span><span><i className="legend-central" />CENTRAL COMPLEX</span><span><i className="legend-descending" />DESCENDING</span><span><i className="legend-motor" />MOTOR</span></div></div>;
}

function HonestyPanel({ mode }: { mode: "simulated" | "flybrain" }) {
  return <details className="honesty-panel"><summary><Info size={14} /> WHAT IS REAL? <span>{mode === "flybrain" ? "MALECNS RUNTIME" : "DEVELOPMENT ADAPTER"}</span></summary><div className="honesty-copy"><p><strong>Real:</strong> the MaleCNS wiring and LIF network when the optional host is enabled, plus the PokerKit rules engine and recorded event protocol.</p><p><strong>Engineered:</strong> poker inputs are feature-detector pulses, and poker strategy lives in trained linear readouts. Per-fly seeded neural states and separate readout variants create the six profiles.</p><p><strong>Not claimed:</strong> this is not evidence that biological flies understand poker. The current browser build is explicitly marked simulated until the data, CUDA runtime, and readout manifest pass the readiness probe.</p><p className="model-credit">Scene assets: <a href="https://opengameart.org/content/spy-fly" target="_blank" rel="noreferrer">Spy Fly by sunburn</a> (CC BY 3.0) and <a href="https://opengameart.org/content/poker-pack" target="_blank" rel="noreferrer">Poker Pack by mehrasaur</a> (CC0).</p></div></details>;
}
