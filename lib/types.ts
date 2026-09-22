// The wire contract is generated from services/api/flypoker/models.py.  The
// UI aliases below add the narrower presentation types and fallback fixtures.
import type { EventEnvelope as ProtocolEventEnvelope } from "./protocol.generated";

export type {
  EventEnvelope as ProtocolEventEnvelope,
  EventMessage as ProtocolEventMessage,
  FlyProfile as ProtocolFlyProfile,
  SnapshotMessage as ProtocolSnapshotMessage,
  StatusResponse as ProtocolStatusResponse,
  TableSnapshot as ProtocolTableSnapshot,
} from "./protocol.generated";

export type Street = "intermission" | "preflop" | "flop" | "turn" | "river" | "showdown";

export type FlyPlayer = {
  id: string;
  name: string;
  style: string;
  accent: string;
  chips: number;
  seat: number;
  alive: boolean;
  hole_cards: string[];
  equity: number;
  activity: number;
  vpip: number;
  pfr: number;
  aggression: number;
  tell: string;
  status: string;
};

export type TableSnapshot = {
  mode: "simulated" | "flybrain";
  tournament_id: string;
  hand_id: string;
  deck_seed: number;
  hand_number: number;
  street: Street;
  board: string[];
  pot: number;
  current_actor: string | null;
  blind_level: number;
  blinds: string;
  players: FlyPlayer[];
  last_event: string;
  sequence: number;
  updated_at: string;
};

export type EventEnvelope = ProtocolEventEnvelope;

export type NeuralTelemetry = {
  playerId: string;
  mode?: "simulated" | "flybrain";
  activity: number;
  regions: Record<string, number>;
  sampledSpikes: number[];
  sampledNeuronCount?: number;
  features?: Record<string, number>;
  stimulatedPopulations?: string[];
};

export type DecisionTelemetry = {
  features: Record<string, number>;
  legalActions: string[];
  logits: Record<string, number>;
  sizing?: string;
};

export type LiveMessage =
  | { kind: "snapshot"; snapshot: TableSnapshot; sequence: number }
  | { kind: "event"; event: EventEnvelope };

export const FALLBACK_PLAYERS: FlyPlayer[] = [
  { id: "vesper", name: "Vesper", style: "tight-aggressive", accent: "#e9c46a", chips: 2000, seat: 0, alive: true, hole_cards: ["A♠", "Q♦"], equity: 0.61, activity: 0.63, vpip: 0.566, pfr: 0.293, aggression: 0.519, tell: "A single antenna sweep before a sharp raise.", status: "watching" },
  { id: "sugar", name: "Sugar", style: "loose-aggressive", accent: "#f4a261", chips: 2000, seat: 1, alive: true, hole_cards: ["8♥", "7♥"], equity: 0.39, activity: 0.32, vpip: 0.852, pfr: 0.636, aggression: 0.746, tell: "Her wings buzz when the pot smells sweet.", status: "watching" },
  { id: "knuckles", name: "Knuckles", style: "short-stack pressure", accent: "#e76f51", chips: 2000, seat: 2, alive: true, hole_cards: ["K♣", "J♣"], equity: 0.48, activity: 0.48, vpip: 0.869, pfr: 0.632, aggression: 0.728, tell: "A restless foreleg taps the felt.", status: "watching" },
  { id: "velvet", name: "Velvet", style: "trap-heavy", accent: "#b56576", chips: 2000, seat: 3, alive: true, hole_cards: ["9♣", "9♦"], equity: 0.52, activity: 0.23, vpip: 0.601, pfr: 0.069, aggression: 0.115, tell: "She grooms slowly when the table thinks she is weak.", status: "watching" },
  { id: "static", name: "Static", style: "high-variance", accent: "#72efdd", chips: 2000, seat: 4, alive: true, hole_cards: ["5♠", "2♠"], equity: 0.22, activity: 0.69, vpip: 0.897, pfr: 0.752, aggression: 0.838, tell: "A bright tremor travels through both wings.", status: "watching" },
  { id: "hex", name: "Hex", style: "balanced / pot-odds", accent: "#9b8afb", chips: 2000, seat: 5, alive: true, hole_cards: ["A♥", "T♣"], equity: 0.56, activity: 0.41, vpip: 0.647, pfr: 0.227, aggression: 0.351, tell: "Both antennae settle into a precise, quiet line.", status: "watching" },
];

export const FALLBACK_SNAPSHOT: TableSnapshot = {
  mode: "simulated",
  tournament_id: "tourney-demo",
  hand_id: "hand-0017",
  deck_seed: 0,
  hand_number: 17,
  street: "flop",
  board: ["K♦", "7♣", "2♥"],
  pot: 460,
  current_actor: "vesper",
  blind_level: 2,
  blinds: "25 / 50",
  players: FALLBACK_PLAYERS,
  last_event: "Vesper reads the room before moving a wing.",
  sequence: 142,
  updated_at: new Date().toISOString(),
};
