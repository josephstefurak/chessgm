// The wire format. Mirrors webgui/server/schemas.py by hand: change both together.

export type Colour = "white" | "black";
export type ColourChoice = Colour | "random";

export type Reason =
  | "checkmate"
  | "stalemate"
  | "insufficient_material"
  | "threefold_repetition"
  | "fifty_moves"
  | "fivefold_repetition"
  | "seventyfive_moves"
  | "resignation"
  | "timeout"
  | "timeout_insufficient_material";

export interface TimeControl {
  id: string;
  initial_ms: number;
  increment_ms: number;
}

export interface ClockPair {
  white_ms: number;
  black_ms: number;
}

export interface Clock extends ClockPair {
  running: Colour | null;
}

export interface Ply {
  ply: number;
  san: string;
  uci: string;
  fen: string;
  check: Colour | null;
  capture: boolean;
  clock: ClockPair | null;
}

/** From White's point of view. Exactly one of the two is set. */
export interface Score {
  cp: number | null;
  mate: number | null;
}

export interface EngineStatus {
  state: "idle" | "thinking" | "error";
  source: "book" | "search" | null;
  ply: number | null;
  depth: number | null;
  score: Score | null;
  pv_san: string[];
  nodes: number | null;
  ms: number | null;
  error: string | null;
}

export interface GameResult {
  winner: Colour | null;
  reason: Reason;
}

export interface Snapshot {
  game_id: string;
  version: number;
  human: Colour;
  status: "playing" | "finished";
  result: GameResult | null;
  turn: Colour;
  start_fen: string;
  plies: Ply[];
  legal: { dests: Record<string, string[]>; promotions: string[] };
  actions: { takeback: boolean; resign: boolean };
  time_control: string | null;
  time_controls: TimeControl[];
  clock: Clock | null;
  engine: EngineStatus;
  pgn: string;
}

export type PromotionPiece = "q" | "r" | "b" | "n";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * A structural check on what the server sent, so a mismatch between the two
 * sides fails here, loudly, instead of as a blank board somewhere else.
 */
export function isSnapshot(value: unknown): value is Snapshot {
  if (!isRecord(value)) return false;
  const { legal, actions, engine } = value;
  return (
    typeof value.game_id === "string" &&
    typeof value.version === "number" &&
    (value.human === "white" || value.human === "black") &&
    (value.turn === "white" || value.turn === "black") &&
    (value.status === "playing" || value.status === "finished") &&
    typeof value.start_fen === "string" &&
    typeof value.pgn === "string" &&
    Array.isArray(value.plies) &&
    Array.isArray(value.time_controls) &&
    isRecord(legal) &&
    isRecord(legal.dests) &&
    Array.isArray(legal.promotions) &&
    isRecord(actions) &&
    isRecord(engine) &&
    Array.isArray(engine.pv_san)
  );
}
