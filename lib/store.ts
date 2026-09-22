"use client";

import { create } from "zustand";
import type { DecisionTelemetry, EventEnvelope, FlyPlayer, LiveMessage, NeuralTelemetry, TableSnapshot } from "./types";
import { FALLBACK_SNAPSHOT } from "./types";

type ViewMode = "broadcast" | "inspection";
export type CameraMode = "broadcast" | "table" | "macro";

type FlyPokerStore = {
  snapshot: TableSnapshot;
  connected: boolean;
  viewMode: ViewMode;
  cameraMode: CameraMode;
  selectedFlyId: string;
  cleanCinema: boolean;
  muted: boolean;
  reducedMotion: boolean;
  events: EventEnvelope[];
  telemetry: Record<string, NeuralTelemetry>;
  decisions: Record<string, DecisionTelemetry>;
  setSnapshot: (snapshot: TableSnapshot) => void;
  applyMessage: (message: LiveMessage) => void;
  setConnected: (connected: boolean) => void;
  setViewMode: (viewMode: ViewMode) => void;
  cycleCamera: () => void;
  selectFly: (id: string) => void;
  toggleCinema: () => void;
  toggleMuted: () => void;
  setReducedMotion: (value: boolean) => void;
};

export const useFlyPokerStore = create<FlyPokerStore>((set) => ({
  snapshot: FALLBACK_SNAPSHOT,
  connected: false,
  viewMode: "broadcast",
  cameraMode: "broadcast",
  selectedFlyId: "vesper",
  cleanCinema: false,
  muted: true,
  reducedMotion: false,
  events: [],
  telemetry: {},
  decisions: {},
  setSnapshot: (snapshot) => set({ snapshot }),
  applyMessage: (message) => {
    if (message.kind === "snapshot") {
      set({ snapshot: message.snapshot });
      return;
    }
    const event = message.event;
    set((state) => {
      // Reconnects can replay the last few frames; keep the visual state
      // monotonic so snapshot-to-event handoff never jumps backwards.
      if (event.sequence <= state.snapshot.sequence) return state;
      const nextSnapshot = { ...state.snapshot };
      const payload = event.payload;
      if (event.type === "street.revealed" && Array.isArray(payload.board)) {
        nextSnapshot.board = payload.board as string[];
        nextSnapshot.street = payload.street as TableSnapshot["street"];
      }
      if (event.type === "system.status" && (payload.mode === "flybrain" || payload.mode === "simulated")) {
        nextSnapshot.mode = payload.mode;
      }
      if (event.type === "cards.dealt" && Array.isArray(payload.players)) {
        const dealt = payload.players as Array<{ id?: unknown; cards?: unknown; equity?: unknown; chips?: unknown; alive?: unknown; status?: unknown }>;
        nextSnapshot.players = nextSnapshot.players.map((player) => {
          const update = dealt.find((item) => String(item.id) === player.id);
          return update ? { ...player, hole_cards: Array.isArray(update.cards) ? update.cards.map(String) : [], equity: Number(update.equity ?? player.equity), chips: Number(update.chips ?? player.chips), alive: Boolean(update.alive ?? player.alive), status: String(update.status ?? player.status) } : player;
        });
      }
      if (event.type === "actor.thinking" || event.type === "action.committed") {
        nextSnapshot.current_actor = String(payload.playerId ?? "");
      }
      if (event.type === "action.committed") {
        const playerId = String(payload.playerId ?? "");
        nextSnapshot.players = nextSnapshot.players.map((player) =>
          player.id === playerId ? { ...player, status: String(payload.action ?? "watching"), activity: 0.72 } : player,
        );
        if (Array.isArray(payload.players)) {
          const publicPlayers = payload.players as Array<{ id?: unknown; chips?: unknown; alive?: unknown; status?: unknown }>;
          nextSnapshot.players = nextSnapshot.players.map((player) => {
            const update = publicPlayers.find((item) => String(item.id) === player.id);
            return update ? { ...player, chips: Number(update.chips ?? player.chips), alive: Boolean(update.alive ?? player.alive), status: String(update.status ?? player.status) } : player;
          });
        }
        if (typeof payload.pot === "number") nextSnapshot.pot = payload.pot;
      }
      if (event.type === "showdown.resolved") {
        nextSnapshot.street = "showdown";
        nextSnapshot.current_actor = null;
      }
      if (event.type === "brain.reset") {
        nextSnapshot.street = "intermission";
        nextSnapshot.current_actor = null;
      }
      if (typeof payload.street === "string") nextSnapshot.street = payload.street as TableSnapshot["street"];
      if (typeof payload.board !== "undefined" && Array.isArray(payload.board)) nextSnapshot.board = payload.board as string[];
      nextSnapshot.last_event = humanizeEvent(event);
      nextSnapshot.sequence = event.sequence;
      const playerId = String(payload.playerId ?? "");
      const priorDecision = state.decisions[playerId] ?? { features: {}, legalActions: [], logits: {} };
      const decisions = { ...state.decisions };
      if (event.type === "actor.thinking") {
        decisions[playerId] = {
          ...priorDecision,
          features: (payload.features ?? {}) as Record<string, number>,
          legalActions: Array.isArray(payload.legalActions) ? payload.legalActions.map(String) : [],
        };
      }
      if (event.type === "action.committed") {
        decisions[playerId] = {
          ...priorDecision,
          logits: (payload.logits ?? {}) as Record<string, number>,
          sizing: typeof payload.sizing === "string" ? payload.sizing : priorDecision.sizing,
        };
      }
      return {
        snapshot: nextSnapshot,
        events: [...state.events, event].slice(-80),
        decisions,
        telemetry: event.type === "brain.telemetry" && payload.playerId
          ? { ...state.telemetry, [String(payload.playerId)]: payload as unknown as NeuralTelemetry }
          : state.telemetry,
      };
    });
  },
  setConnected: (connected) => set({ connected }),
  setViewMode: (viewMode) => set({ viewMode }),
  cycleCamera: () => set((state) => ({ cameraMode: state.cameraMode === "broadcast" ? "table" : state.cameraMode === "table" ? "macro" : "broadcast" })),
  selectFly: (selectedFlyId) => set({ selectedFlyId, viewMode: "inspection" }),
  toggleCinema: () => set((state) => ({ cleanCinema: !state.cleanCinema })),
  toggleMuted: () => set((state) => ({ muted: !state.muted })),
  setReducedMotion: (reducedMotion) => set({ reducedMotion }),
}));

function humanizeEvent(event: EventEnvelope): string {
  const p = event.payload;
  if (event.type === "brain.reset") return "Six neural states reinitialized from the last completed hand.";
  if (event.type === "actor.thinking") return String(p.playerId ?? "A fly") + " is reading the table.";
  if (event.type === "action.committed") return `${String(p.playerId ?? "A fly")} chooses ${String(p.action ?? "wait")}.`;
  if (event.type === "street.revealed") return `The ${String(p.street ?? "next")} arrives.`;
  if (event.type === "showdown.resolved") {
    const winners = Array.isArray(p.winnerIds) ? p.winnerIds.map(String) : [String(p.winnerId ?? "A fly")];
    return winners.length > 1 ? `${winners.join(" and ")} split the pot.` : `${winners[0]} takes the pot.`;
  }
  if (event.type === "champion") return `${String(p.winnerId ?? "A fly")} claims the table.`;
  if (event.type === "elimination") return `${String(p.playerId ?? "A fly")} leaves the felt.`;
  if (event.type === "tournament.completed") return "The tournament is complete. Intermission begins.";
  return event.type.replaceAll(".", " ");
}
