// View state: which game we are showing and how the reader is looking at it.
// Nothing here knows the rules of chess; positions come ready-made from the server.

import type { Colour, Snapshot } from "../api/types";

export interface View {
  snapshot: Snapshot | null;
  /** The ply being reviewed (0 is the starting position), or null when following the game. */
  viewPly: number | null;
  flipped: boolean;
  connected: boolean;
  /** True until the first snapshot after a (re)connection, which is always accepted. */
  awaitingFirst: boolean;
}

export type Step = "first" | "previous" | "next" | "last";

export type Action =
  | { type: "snapshot"; snapshot: Snapshot }
  | { type: "connection"; connected: boolean }
  | { type: "step"; step: Step }
  | { type: "goto"; ply: number }
  | { type: "flip" };

export const initialView: View = {
  snapshot: null,
  viewPly: null,
  flipped: false,
  connected: false,
  awaitingFirst: true,
};

function goto(view: View, ply: number): View {
  if (view.snapshot === null) return view;
  const last = view.snapshot.plies.length;
  const clamped = Math.max(0, Math.min(last, Math.trunc(ply)));
  return { ...view, viewPly: clamped === last ? null : clamped };
}

export function reduce(view: View, action: Action): View {
  switch (action.type) {
    case "connection":
      // A reconnection may be to a restarted server whose versions start again from
      // zero, so the next snapshot must not be compared with the one we hold.
      return { ...view, connected: action.connected, awaitingFirst: view.awaitingFirst || action.connected };

    case "snapshot": {
      const current = view.snapshot;
      const next = action.snapshot;
      if (current !== null && !view.awaitingFirst && next.version <= current.version) {
        return view; // an older answer arriving late
      }
      const sameGame = current !== null && current.game_id === next.game_id;
      const moved = !sameGame || current.plies.length !== next.plies.length;
      return {
        ...view,
        snapshot: next,
        awaitingFirst: false,
        // A new move, a takeback or a new game always brings the reader back to the board.
        viewPly: moved ? null : view.viewPly,
        flipped: sameGame ? view.flipped : false,
      };
    }

    case "step": {
      if (view.snapshot === null) return view;
      const last = view.snapshot.plies.length;
      const at = view.viewPly ?? last;
      const target = { first: 0, previous: at - 1, next: at + 1, last }[action.step];
      return goto(view, target);
    }

    case "goto":
      return goto(view, action.ply);

    case "flip":
      return { ...view, flipped: !view.flipped };
  }
}

export interface Position {
  fen: string;
  ply: number;
  lastMove: [string, string] | null;
  check: Colour | null;
  live: boolean;
}

/** The position to draw: the one being reviewed, or the current one. */
export function positionOf(view: View): Position | null {
  const snapshot = view.snapshot;
  if (snapshot === null) return null;
  const ply = view.viewPly ?? snapshot.plies.length;
  const record = ply > 0 ? snapshot.plies[ply - 1] : undefined;
  return {
    fen: record?.fen ?? snapshot.start_fen,
    ply,
    lastMove: record ? [record.uci.slice(0, 2), record.uci.slice(2, 4)] : null,
    check: record?.check ?? null,
    live: view.viewPly === null,
  };
}

export function orientationOf(view: View): Colour {
  const human = view.snapshot?.human ?? "white";
  if (!view.flipped) return human;
  return human === "white" ? "black" : "white";
}

export type SoundName = "move" | "capture" | "check" | "end";

/** Which sound, if any, the change from one snapshot to the next deserves. */
export function soundFor(previous: Snapshot | null, next: Snapshot): SoundName | null {
  if (previous === null || previous.game_id !== next.game_id) return null;
  const ended = previous.status === "playing" && next.status === "finished";
  if (next.plies.length > previous.plies.length) {
    const last = next.plies[next.plies.length - 1];
    if (ended) return "end";
    if (last?.check) return "check";
    return last?.capture ? "capture" : "move";
  }
  return ended ? "end" : null;
}
