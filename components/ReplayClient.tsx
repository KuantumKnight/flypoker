"use client";

import dynamic from "next/dynamic";
import { Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { EventEnvelope, TableSnapshot } from "@/lib/types";

const ReplayScene = dynamic(() => import("@/components/CasinoScene"), { ssr: false });

type ReplayResponse = { slug: string; mode: string; events: EventEnvelope[]; snapshot: TableSnapshot };

export default function ReplayClient({ slug }: { slug: string }) {
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    const candidates = [
      process.env.NEXT_PUBLIC_API_URL ? `${process.env.NEXT_PUBLIC_API_URL}/v1/replays` : "",
      process.env.NEXT_PUBLIC_REPLAY_API_URL ? `${process.env.NEXT_PUBLIC_REPLAY_API_URL}/replays` : "",
    ].filter((value, index, all): value is string => Boolean(value) && all.indexOf(value) === index);
    const load = async () => {
      let lastError = "Replay unavailable";
      for (const api of candidates) {
        try {
          const response = await fetch(`${api}/${encodeURIComponent(slug)}`);
          if (response.ok) { setReplay(await response.json() as ReplayResponse); return; }
          lastError = `Replay unavailable (${response.status})`;
        } catch (reason) {
          lastError = reason instanceof Error ? reason.message : lastError;
        }
      }
      setError(lastError);
    };
    void load();
  }, [slug]);

  const events = replay?.events ?? [];
  const current = events[Math.min(cursor, Math.max(events.length - 1, 0))];
  const posterBase = process.env.NEXT_PUBLIC_REPLAY_API_URL;
  const visibleEvents = useMemo(() => events.slice(0, cursor + 1).slice(-9).reverse(), [events, cursor]);
  const replaySnapshot = useMemo(() => reconstructSnapshot(replay?.snapshot, events.slice(0, cursor + 1)), [replay?.snapshot, events, cursor]);

  useEffect(() => {
    if (!playing || cursor >= events.length - 1) {
      if (cursor >= events.length - 1) setPlaying(false);
      return;
    }
    const previous = events[cursor];
    const next = events[cursor + 1];
    const recordedDelta = previous && next ? Date.parse(next.serverTime) - Date.parse(previous.serverTime) : 620;
    const delay = Number.isFinite(recordedDelta) && recordedDelta > 0
      ? Math.max(180, Math.min(4000, recordedDelta))
      : 620;
    const timer = window.setTimeout(() => setCursor((value) => value + 1), delay);
    return () => window.clearTimeout(timer);
  }, [playing, cursor, events.length]);

  return <section className="replay-player" aria-label="Replay player">
    {posterBase && replay && <img className="replay-poster" src={`${posterBase}/replays/${encodeURIComponent(replay.slug)}.svg`} alt="Generated Fly Poker replay poster" />}
    <div className="replay-scene"><ReplayScene players={replaySnapshot.players} currentActor={replaySnapshot.current_actor} lastEvent={current ? readableType(current.type) : undefined} street={replaySnapshot.street} board={replaySnapshot.board} pot={replaySnapshot.pot} reducedMotion /></div>
    <div className="replay-player-head"><div><span className="panel-kicker">EVENT RECONSTRUCTION / {replay?.mode ?? "LOADING"}</span><strong>{current ? readableType(current.type) : error ?? "Loading event journal…"}</strong></div><span className="mono">{events.length ? `${cursor + 1} / ${events.length}` : "—"}</span></div>
    <div className="replay-progress"><i style={{ width: `${events.length ? ((cursor + 1) / events.length) * 100 : 0}%` }} /></div>
    <div className="replay-events">{visibleEvents.length ? visibleEvents.map((event) => <div className={`replay-event ${event.sequence === current?.sequence ? "current" : ""}`} key={`${event.handId}-${event.sequence}`}><span className="mono">{String(event.sequence).padStart(4, "0")}</span><strong>{readableType(event.type)}</strong><span>{event.payload.playerId ? String(event.payload.playerId) : event.payload.street ? String(event.payload.street) : "table"}</span></div>) : <div className="replay-empty">The live host has not uploaded this hand yet. Start the API to generate the first journal.</div>}</div>
    <div className="replay-actions"><button className="replay-play" onClick={() => setPlaying((value) => !value)} disabled={!events.length}>{playing ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}{playing ? "PAUSE REPLAY" : "PLAY REPLAY"}</button><button className="replay-reset" onClick={() => { setPlaying(false); setCursor(0); }} disabled={!events.length}><RotateCcw size={14} /> RESET</button></div>
  </section>;
}

function reconstructSnapshot(base: TableSnapshot | undefined, events: EventEnvelope[]): TableSnapshot {
  const snapshot: TableSnapshot = {
    ...(base ?? { mode: "simulated", tournament_id: "replay", hand_id: "replay", deck_seed: 0, hand_number: 0, street: "intermission", board: [], pot: 0, current_actor: null, blind_level: 0, blinds: "10 / 20", players: [], last_event: "Replay", sequence: 0, updated_at: new Date(0).toISOString() }),
    // The API snapshot is the hand's final/current state.  Replays must not
    // use its mutable stacks/cards as their starting point; the event journal
    // is authoritative for the visible hand progression.
    board: [],
    pot: 0,
    current_actor: null,
    street: "intermission",
    players: (base?.players ?? []).map((player) => ({
      ...player,
      chips: 0,
      alive: true,
      hole_cards: [],
      equity: 0,
      activity: 0,
      status: "watching",
    })),
  };
  for (const event of events) {
    const payload = event.payload;
    snapshot.sequence = event.sequence;
    if (event.type === "hand.started") {
      if (typeof payload.handNumber === "number") snapshot.hand_number = payload.handNumber;
      if (typeof payload.blinds === "string") snapshot.blinds = payload.blinds;
      snapshot.street = "preflop";
      snapshot.current_actor = null;
    }
    if (event.type === "cards.dealt" && Array.isArray(payload.players)) {
      snapshot.players = mergeReplayPlayers(snapshot.players, payload.players);
    }
    if (event.type === "actor.thinking" && typeof payload.playerId === "string") {
      snapshot.current_actor = payload.playerId;
      snapshot.players = snapshot.players.map((player) => player.id === payload.playerId ? { ...player, status: "thinking" } : player);
    }
    if (event.type === "street.revealed") {
      if (Array.isArray(payload.board)) snapshot.board = payload.board.map(String);
      if (typeof payload.street === "string") snapshot.street = payload.street as TableSnapshot["street"];
    }
    if (event.type === "action.committed") {
      snapshot.current_actor = typeof payload.playerId === "string" ? payload.playerId : snapshot.current_actor;
      if (Array.isArray(payload.players)) snapshot.players = mergeReplayPlayers(snapshot.players, payload.players);
      if (Array.isArray(payload.board)) snapshot.board = payload.board.map(String);
      if (typeof payload.pot === "number") snapshot.pot = payload.pot;
      if (typeof payload.street === "string") snapshot.street = payload.street as TableSnapshot["street"];
    }
    if (event.type === "showdown.resolved") {
      snapshot.street = "showdown";
      snapshot.current_actor = null;
      if (Array.isArray(payload.board)) snapshot.board = payload.board.map(String);
      if (typeof payload.pot === "number") snapshot.pot = payload.pot;
      if (Array.isArray(payload.players)) snapshot.players = mergeReplayPlayers(snapshot.players, payload.players);
    }
    snapshot.last_event = readableType(event.type);
  }
  return snapshot;
}

function mergeReplayPlayers(current: TableSnapshot["players"], incoming: unknown[]): TableSnapshot["players"] {
  return current.map((player) => {
    const update = incoming.find((item) => typeof item === "object" && item !== null && String((item as Record<string, unknown>).id) === player.id) as Record<string, unknown> | undefined;
    if (!update) return player;
    return {
      ...player,
      chips: typeof update.chips === "number" ? update.chips : player.chips,
      alive: typeof update.alive === "boolean" ? update.alive : player.alive,
      status: typeof update.status === "string" ? update.status : player.status,
      hole_cards: Array.isArray(update.cards) ? update.cards.map(String) : player.hole_cards,
      equity: typeof update.equity === "number" ? update.equity : player.equity,
    };
  });
}

function readableType(type: string) {
  return type.replaceAll(".", " / ").replaceAll("_", " ").toUpperCase();
}
