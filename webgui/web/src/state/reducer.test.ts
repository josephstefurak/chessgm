import { describe, expect, it } from "vitest";
import type { Ply, Snapshot } from "../api/types";
import { initialView, orientationOf, positionOf, reduce, soundFor, type View } from "./reducer";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

function ply(number: number, san: string, uci: string, extra: Partial<Ply> = {}): Ply {
  return { ply: number, san, uci, fen: `fen-after-${number}`, check: null, capture: false, clock: null, ...extra };
}

function snapshot(change: Partial<Snapshot> = {}): Snapshot {
  return {
    game_id: "aaaaaaaaaaaaaaaa",
    version: 1,
    human: "white",
    status: "playing",
    result: null,
    turn: "white",
    start_fen: START,
    plies: [],
    legal: { dests: {}, promotions: [] },
    actions: { takeback: false, resign: true },
    time_control: null,
    time_controls: [],
    clock: null,
    engine: {
      state: "idle",
      source: null,
      ply: null,
      depth: null,
      score: null,
      pv_san: [],
      nodes: null,
      ms: null,
      error: null,
    },
    pgn: "",
    ...change,
  };
}

const FOUR = [ply(1, "e4", "e2e4"), ply(2, "e5", "e7e5"), ply(3, "Nf3", "g1f3"), ply(4, "Nc6", "b8c6")];

function viewOf(change: Partial<Snapshot> = {}): View {
  return reduce(initialView, { type: "snapshot", snapshot: snapshot(change) });
}

describe("snapshots", () => {
  it("accepts the first one whatever its version", () => {
    expect(viewOf({ version: 0 }).snapshot?.version).toBe(0);
  });

  it("ignores an older or repeated answer that arrives late", () => {
    const view = viewOf({ version: 5, plies: FOUR });
    expect(reduce(view, { type: "snapshot", snapshot: snapshot({ version: 4 }) })).toBe(view);
    expect(reduce(view, { type: "snapshot", snapshot: snapshot({ version: 5 }) })).toBe(view);
  });

  it("accepts a lower version after a reconnection, because the server may have restarted", () => {
    let view = viewOf({ version: 50, plies: FOUR });
    view = reduce(view, { type: "connection", connected: false });
    expect(reduce(view, { type: "snapshot", snapshot: snapshot({ version: 2 }) })).toBe(view);
    view = reduce(view, { type: "connection", connected: true });
    view = reduce(view, { type: "snapshot", snapshot: snapshot({ version: 2, game_id: "b".repeat(16) }) });
    expect(view.snapshot?.version).toBe(2);
    expect(view.connected).toBe(true);
  });

  it("returns to the live position when a move arrives during review", () => {
    let view = viewOf({ version: 1, plies: FOUR });
    view = reduce(view, { type: "goto", ply: 1 });
    expect(view.viewPly).toBe(1);
    view = reduce(view, {
      type: "snapshot",
      snapshot: snapshot({ version: 2, plies: [...FOUR, ply(5, "Bb5", "f1b5")] }),
    });
    expect(view.viewPly).toBeNull();
  });

  it("keeps the review position when only the engine's thinking changed", () => {
    let view = viewOf({ version: 1, plies: FOUR });
    view = reduce(view, { type: "goto", ply: 2 });
    view = reduce(view, { type: "snapshot", snapshot: snapshot({ version: 2, plies: FOUR }) });
    expect(view.viewPly).toBe(2);
  });

  it("turns the board back for a new game but keeps it flipped within one", () => {
    let view = reduce(viewOf({ version: 1 }), { type: "flip" });
    view = reduce(view, { type: "snapshot", snapshot: snapshot({ version: 2, plies: FOUR }) });
    expect(view.flipped).toBe(true);
    view = reduce(view, { type: "snapshot", snapshot: snapshot({ version: 3, game_id: "c".repeat(16) }) });
    expect(view.flipped).toBe(false);
  });
});

describe("stepping through the game", () => {
  const live = viewOf({ plies: FOUR });

  it("walks back and forward and stops at both ends", () => {
    let view = reduce(live, { type: "step", step: "previous" });
    expect(view.viewPly).toBe(3);
    view = reduce(view, { type: "step", step: "first" });
    expect(view.viewPly).toBe(0);
    expect(reduce(view, { type: "step", step: "previous" }).viewPly).toBe(0);
    view = reduce(view, { type: "step", step: "next" });
    expect(view.viewPly).toBe(1);
    view = reduce(view, { type: "step", step: "last" });
    expect(view.viewPly).toBeNull();
    expect(reduce(view, { type: "step", step: "next" }).viewPly).toBeNull();
  });

  it("clamps a jump and treats the last move as live", () => {
    expect(reduce(live, { type: "goto", ply: -3 }).viewPly).toBe(0);
    expect(reduce(live, { type: "goto", ply: 99 }).viewPly).toBeNull();
    expect(reduce(live, { type: "goto", ply: 4 }).viewPly).toBeNull();
    expect(reduce(live, { type: "goto", ply: 2.9 }).viewPly).toBe(2);
  });

  it("does nothing before the first snapshot", () => {
    expect(reduce(initialView, { type: "step", step: "previous" })).toBe(initialView);
    expect(positionOf(initialView)).toBeNull();
  });
});

describe("the position to draw", () => {
  it("is the last move when live", () => {
    const view = viewOf({ plies: [ply(1, "e4", "e2e4"), ply(2, "Qh4+", "d8h4", { check: "white" })] });
    expect(positionOf(view)).toEqual({
      fen: "fen-after-2",
      ply: 2,
      lastMove: ["d8", "h4"],
      check: "white",
      live: true,
    });
  });

  it("is the starting position at ply 0", () => {
    const view = reduce(viewOf({ plies: FOUR }), { type: "goto", ply: 0 });
    expect(positionOf(view)).toEqual({ fen: START, ply: 0, lastMove: null, check: null, live: false });
  });

  it("keeps only the squares of a promotion move", () => {
    const view = viewOf({ plies: [ply(1, "hxg8=Q", "h7g8q")] });
    expect(positionOf(view)?.lastMove).toEqual(["h7", "g8"]);
  });

  it("faces the human, or the other way when flipped", () => {
    const black = viewOf({ human: "black" });
    expect(orientationOf(black)).toBe("black");
    expect(orientationOf(reduce(black, { type: "flip" }))).toBe("white");
    expect(orientationOf(initialView)).toBe("white");
  });
});

describe("sounds", () => {
  const before = snapshot({ plies: FOUR.slice(0, 2) });

  it("is silent on the first snapshot, a new game and a takeback", () => {
    expect(soundFor(null, before)).toBeNull();
    expect(soundFor(before, snapshot({ game_id: "d".repeat(16), plies: FOUR }))).toBeNull();
    expect(soundFor(snapshot({ plies: FOUR }), before)).toBeNull();
    expect(soundFor(before, snapshot({ plies: FOUR.slice(0, 2), version: 9 }))).toBeNull();
  });

  it("matches the move that was played", () => {
    const next = (last: Ply) => snapshot({ plies: [...FOUR.slice(0, 2), last] });
    expect(soundFor(before, next(ply(3, "Nf3", "g1f3")))).toBe("move");
    expect(soundFor(before, next(ply(3, "exd5", "e4d5", { capture: true })))).toBe("capture");
    expect(soundFor(before, next(ply(3, "Bb5+", "f1b5", { check: "black", capture: true })))).toBe("check");
  });

  it("marks the end of the game, with or without a final move", () => {
    const mate = snapshot({ plies: [...FOUR.slice(0, 2), ply(3, "Qxf7#", "h5f7")], status: "finished" });
    expect(soundFor(before, mate)).toBe("end");
    expect(soundFor(before, snapshot({ plies: FOUR.slice(0, 2), status: "finished" }))).toBe("end");
    expect(soundFor(mate, { ...mate, version: 8 })).toBeNull();
  });
});
