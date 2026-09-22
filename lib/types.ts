// The wire contract is generated from services/api/flypoker/models.py. The UI
// aliases below add presentation-only types. Live state is intentionally
// nullable: an offline host must never be replaced with fabricated cards or
// neural telemetry.
import type { EventEnvelope as ProtocolEventEnvelope } from "./protocol.generated";

export type {
  EventEnvelope as ProtocolEventEnvelope,
  EventMessage as ProtocolEventMessage,
  StatusMessage as ProtocolStatusMessage,
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
  | { kind: "event"; event: EventEnvelope }
  | { kind: "status"; status: LiveStatus };

export type LiveStatus = {
  status: "live" | "starting" | "offline";
  mode: "flybrain" | "simulated" | "offline";
  runtimeNote?: string;
};
