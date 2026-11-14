// Words and numbers as the reader sees them. Presentation only.

import type { Colour, GameResult, Reason, Score, TimeControl } from "./api/types";

const TENTHS_BELOW_MS = 20_000;

/** 5:03, 0:19.4 under twenty seconds, 1:02:30 past the hour. */
export function formatClock(ms: number): string {
  const clamped = Math.max(0, ms);
  if (clamped < TENTHS_BELOW_MS) {
    const tenths = Math.floor(clamped / 100);
    return `0:${String(Math.floor(tenths / 10)).padStart(2, "0")}.${tenths % 10}`;
  }
  const total = Math.ceil(clamped / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}` : `${minutes}:${seconds}`;
}

export const LOW_TIME_MS = 20_000;

/** +0.34, −1.20, M3 (White mates), −M2 (Black mates). */
export function formatScore(score: Score | null): string {
  if (score === null) return "";
  if (score.mate !== null) return `${score.mate < 0 ? "−" : ""}M${Math.abs(score.mate)}`;
  const pawns = (score.cp ?? 0) / 100;
  const sign = pawns > 0 ? "+" : pawns < 0 ? "−" : "";
  return `${sign}${Math.abs(pawns).toFixed(2)}`;
}

/**
 * Share of the eval bar given to White, 0 to 1. The curve is the usual one for
 * turning centipawns into winning chances, so a pawn up is visible but a queen
 * up does not look ten times more decided than a rook up.
 */
export function whiteShare(score: Score | null): number {
  if (score === null) return 0.5;
  if (score.mate !== null) return score.mate > 0 ? 1 : 0;
  return 1 / (1 + Math.exp(-0.00368208 * (score.cp ?? 0)));
}

/** Number a line of moves: "12. Nf3 d5 13. c4" or "12... d5 13. c4". */
export function formatLine(pliesPlayed: number, sans: readonly string[]): string {
  const parts: string[] = [];
  sans.forEach((san, index) => {
    const ply = pliesPlayed + index;
    const number = Math.floor(ply / 2) + 1;
    if (ply % 2 === 0) parts.push(`${number}.`);
    else if (index === 0) parts.push(`${number}...`);
    parts.push(san);
  });
  return parts.join(" ");
}

export function formatNodes(nodes: number): string {
  if (nodes >= 1_000_000) return `${(nodes / 1_000_000).toFixed(1)}M`;
  if (nodes >= 1_000) return `${Math.round(nodes / 1_000)}k`;
  return String(nodes);
}

/** "5 + 3" in minutes and seconds; a control shorter than whole minutes is given in seconds. */
export function timeControlLabel(control: TimeControl): string {
  const increment = control.increment_ms / 1000;
  const wholeMinutes = control.initial_ms % 60_000 === 0;
  const initial = wholeMinutes ? String(control.initial_ms / 60_000) : `${control.initial_ms / 1000}s`;
  return `${initial} + ${increment}`;
}

export function timeControlHint(control: TimeControl): string {
  const wholeMinutes = control.initial_ms % 60_000 === 0;
  const initial = wholeMinutes
    ? `${control.initial_ms / 60_000} minutes`
    : `${control.initial_ms / 1000} seconds`;
  const increment = control.increment_ms / 1000;
  return increment > 0 ? `${initial} each, plus ${increment} seconds a move` : `${initial} each`;
}

const REASONS: Record<Reason, string> = {
  checkmate: "by checkmate",
  stalemate: "by stalemate",
  insufficient_material: "by insufficient material",
  threefold_repetition: "by threefold repetition",
  fifty_moves: "by the fifty-move rule",
  fivefold_repetition: "by fivefold repetition",
  seventyfive_moves: "by the seventy-five-move rule",
  resignation: "by resignation",
  timeout: "on time",
  timeout_insufficient_material: "time ran out, but there is not enough material to mate",
};

export type Outcome = "won" | "lost" | "drawn";

export function outcomeFor(result: GameResult, human: Colour): Outcome {
  if (result.winner === null) return "drawn";
  return result.winner === human ? "won" : "lost";
}

export function resultHeadline(result: GameResult, human: Colour): { title: string; detail: string } {
  const title = { won: "You won", lost: "You lost", drawn: "Draw" }[outcomeFor(result, human)];
  return { title, detail: REASONS[result.reason] };
}

const ERRORS: Record<string, string> = {
  network: "The game server is not answering. Is gui.py still running?",
  illegal_move: "That move is not legal.",
  not_your_turn: "It is not your turn yet.",
  game_over: "This game is over.",
  stale_position: "The position changed before that arrived. Try again.",
  stale_game: "A new game was started elsewhere.",
  nothing_to_take_back: "There is nothing to take back.",
};

export function errorText(code: string): string {
  return ERRORS[code] ?? "Something went wrong. Try again.";
}

export function colourName(colour: Colour): string {
  return colour === "white" ? "White" : "Black";
}
