import { describe, expect, it } from "vitest";
import { isSnapshot } from "./api/types";
import {
  errorText,
  formatClock,
  formatLine,
  formatNodes,
  formatScore,
  outcomeFor,
  resultHeadline,
  timeControlHint,
  timeControlLabel,
  whiteShare,
} from "./format";
import { DEFAULT_PREFS, parsePrefs } from "./state/prefs";

describe("clock text", () => {
  it("shows minutes and seconds, rounding up so 5:00 lasts a full second", () => {
    expect(formatClock(300_000)).toBe("5:00");
    expect(formatClock(299_001)).toBe("5:00");
    expect(formatClock(299_000)).toBe("4:59");
    expect(formatClock(61_000)).toBe("1:01");
    expect(formatClock(20_000)).toBe("0:20");
  });

  it("shows tenths in the last twenty seconds", () => {
    expect(formatClock(19_999)).toBe("0:19.9");
    expect(formatClock(4_000)).toBe("0:04.0");
    expect(formatClock(950)).toBe("0:00.9");
    expect(formatClock(0)).toBe("0:00.0");
    expect(formatClock(-50)).toBe("0:00.0");
  });

  it("shows hours when there are any", () => {
    expect(formatClock(3_750_000)).toBe("1:02:30");
  });
});

describe("engine numbers", () => {
  it("writes scores from White's side with a real minus sign", () => {
    expect(formatScore({ cp: 34, mate: null })).toBe("+0.34");
    expect(formatScore({ cp: -120, mate: null })).toBe("−1.20");
    expect(formatScore({ cp: 0, mate: null })).toBe("0.00");
    expect(formatScore({ cp: null, mate: 3 })).toBe("M3");
    expect(formatScore({ cp: null, mate: -2 })).toBe("−M2");
    expect(formatScore(null)).toBe("");
  });

  it("turns a score into White's share of the bar", () => {
    expect(whiteShare(null)).toBe(0.5);
    expect(whiteShare({ cp: 0, mate: null })).toBe(0.5);
    expect(whiteShare({ cp: null, mate: 1 })).toBe(1);
    expect(whiteShare({ cp: null, mate: -4 })).toBe(0);
    const pawnUp = whiteShare({ cp: 100, mate: null });
    expect(pawnUp).toBeGreaterThan(0.55);
    expect(pawnUp).toBeLessThan(0.65);
    expect(whiteShare({ cp: -100, mate: null })).toBeCloseTo(1 - pawnUp);
    expect(whiteShare({ cp: 2000, mate: null })).toBeLessThan(1);
  });

  it("numbers a line from where it starts", () => {
    expect(formatLine(0, ["e4", "e5", "Nf3"])).toBe("1. e4 e5 2. Nf3");
    expect(formatLine(1, ["g5"])).toBe("1... g5");
    expect(formatLine(23, ["d5", "c4", "dxc4"])).toBe("12... d5 13. c4 dxc4");
    expect(formatLine(4, [])).toBe("");
  });

  it("shortens node counts", () => {
    expect(formatNodes(950)).toBe("950");
    expect(formatNodes(36_400)).toBe("36k");
    expect(formatNodes(2_340_000)).toBe("2.3M");
  });
});

describe("words", () => {
  it("names time controls", () => {
    expect(timeControlLabel({ id: "5+3", initial_ms: 300_000, increment_ms: 3_000 })).toBe("5 + 3");
    expect(timeControlHint({ id: "5+3", initial_ms: 300_000, increment_ms: 3_000 })).toBe(
      "5 minutes each, plus 3 seconds a move",
    );
    expect(timeControlHint({ id: "10+0", initial_ms: 600_000, increment_ms: 0 })).toBe("10 minutes each");
    expect(timeControlLabel({ id: "0+1", initial_ms: 4_000, increment_ms: 1_000 })).toBe("4s + 1");
    expect(timeControlHint({ id: "0+1", initial_ms: 4_000, increment_ms: 1_000 })).toBe(
      "4 seconds each, plus 1 seconds a move",
    );
  });

  it("tells the result from the reader's side", () => {
    expect(resultHeadline({ winner: "white", reason: "checkmate" }, "white")).toEqual({
      title: "You won",
      detail: "by checkmate",
    });
    expect(resultHeadline({ winner: "white", reason: "timeout" }, "black")).toEqual({
      title: "You lost",
      detail: "on time",
    });
    expect(resultHeadline({ winner: null, reason: "threefold_repetition" }, "black").title).toBe("Draw");
    expect(outcomeFor({ winner: null, reason: "stalemate" }, "white")).toBe("drawn");
  });

  it("has a sentence for every refusal, known or not", () => {
    expect(errorText("illegal_move")).toBe("That move is not legal.");
    expect(errorText("something_new")).toBe("Something went wrong. Try again.");
  });
});

describe("what the browser remembers", () => {
  it("falls back to the defaults for anything missing or malformed", () => {
    expect(parsePrefs(null)).toEqual(DEFAULT_PREFS);
    expect(parsePrefs("not json")).toEqual(DEFAULT_PREFS);
    expect(parsePrefs("[1,2]")).toEqual(DEFAULT_PREFS);
    expect(parsePrefs('{"sound":"yes","newGame":{"human":"green","timeControl":7}}')).toEqual(DEFAULT_PREFS);
    expect(parsePrefs(JSON.stringify({ newGame: { timeControl: "x".repeat(200) } })).newGame.timeControl).toBeNull();
  });

  it("keeps what is valid", () => {
    const saved = { sound: false, enginePanel: false, newGame: { human: "random", timeControl: "5+3" } };
    expect(parsePrefs(JSON.stringify(saved))).toEqual(saved);
  });
});

describe("what the server sends", () => {
  it("is refused unless it has the shape of a snapshot", () => {
    expect(isSnapshot(null)).toBe(false);
    expect(isSnapshot([])).toBe(false);
    expect(isSnapshot({ game_id: "a", version: 1 })).toBe(false);
    expect(isSnapshot({ error: "illegal_move" })).toBe(false);
  });
});
