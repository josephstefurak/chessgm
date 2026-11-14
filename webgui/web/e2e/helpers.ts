import { inflateSync } from "node:zlib";
import { expect, test as base, type Page } from "@playwright/test";

type Colour = "white" | "black";

/**
 * Every test gets a page that fails the test if the browser reports any error:
 * an exception, a failed request, or a content-security-policy violation
 * (which the browser logs as a console error).
 */
export const test = base.extend<{ problems: string[] }>({
  problems: [
    async ({ page }, use) => {
      const problems: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") problems.push(`console: ${message.text()}`);
      });
      page.on("pageerror", (error) => problems.push(`exception: ${error.message}`));
      await use(problems);
      expect(problems, "the browser reported errors").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/** Start a fresh game through the API, as the page itself would. */
export async function newGame(page: Page, human: Colour = "white", timeControl: string | null = null) {
  const origin = base.info().project.use.baseURL;
  if (origin === undefined) throw new Error("no baseURL configured");
  const response = await page.request.post("/api/game", {
    data: { human, time_control: timeControl },
    headers: { origin },
  });
  expect(response.status()).toBe(200);
}

/** Open the page on a brand-new game. */
export async function open(page: Page, human: Colour = "white", timeControl: string | null = null) {
  await newGame(page, human, timeControl);
  await page.goto("/");
  await expect(page.locator("cg-board piece").first()).toBeVisible();
}

/** Where a square is on screen. Chessground draws no element per square. */
export async function squareCentre(page: Page, square: string): Promise<{ x: number; y: number }> {
  const box = await page.locator("cg-board").boundingBox();
  if (box === null) throw new Error("the board is not on the page");
  const flipped = (await page.locator(".cg-wrap").getAttribute("class"))?.includes("orientation-black") ?? false;
  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]) - 1;
  const column = flipped ? 7 - file : file;
  const row = flipped ? rank : 7 - rank;
  const size = box.width / 8;
  return { x: box.x + (column + 0.5) * size, y: box.y + (row + 0.5) * size };
}

/** Move by clicking the piece and then its destination. */
export async function clickMove(page: Page, from: string, to: string) {
  const start = await squareCentre(page, from);
  const end = await squareCentre(page, to);
  await page.mouse.click(start.x, start.y);
  await page.mouse.click(end.x, end.y);
}

/** Move by dragging the piece. */
export async function dragMove(page: Page, from: string, to: string) {
  const start = await squareCentre(page, from);
  const end = await squareCentre(page, to);
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move((start.x + end.x) / 2, (start.y + end.y) / 2, { steps: 4 });
  await page.mouse.move(end.x, end.y, { steps: 4 });
  await page.mouse.up();
}

/**
 * What is standing on each square, read from where chessground actually drew the
 * pieces: { e4: "white pawn", ... }. This is the board the reader sees, which the
 * move list alone does not prove.
 */
export async function boardPieces(page: Page): Promise<Record<string, string>> {
  return page.evaluate(() => {
    const wrap = document.querySelector(".cg-wrap");
    const board = document.querySelector("cg-board");
    if (wrap === null || board === null) return {};
    const flipped = wrap.classList.contains("orientation-black");
    const box = board.getBoundingClientRect();
    const size = box.width / 8;
    const found: Record<string, string> = {};
    for (const piece of board.querySelectorAll("piece:not(.ghost):not(.fading)")) {
      const rect = piece.getBoundingClientRect();
      const column = Math.floor((rect.left + rect.width / 2 - box.left) / size);
      const row = Math.floor((rect.top + rect.height / 2 - box.top) / size);
      const file = flipped ? 7 - column : column;
      const rank = flipped ? row + 1 : 8 - row;
      found[String.fromCharCode(97 + file) + rank] = piece.className.replace(/\b(anim|dragging)\b/g, "").trim();
    }
    return found;
  });
}

export function moves(page: Page) {
  return page.getByTestId("moves").locator(".moves__move");
}

/** Play the human's moves in turn, waiting for the engine's reply after each. */
export async function playLine(page: Page, line: [string, string][]) {
  for (const [from, to] of line) {
    const before = await moves(page).count();
    await clickMove(page, from, to);
    await expect(moves(page)).toHaveCount(before + 2);
  }
}

/** The colour of one screen pixel, read from a one-pixel screenshot. */
export async function pixel(page: Page, x: number, y: number): Promise<[number, number, number]> {
  const png = await page.screenshot({ clip: { x, y, width: 1, height: 1 }, scale: "css" });
  // A PNG is an 8-byte signature and then chunks: length, type, data, checksum.
  const parts: Buffer[] = [];
  for (let offset = 8; offset < png.length; ) {
    const length = png.readUInt32BE(offset);
    if (png.toString("latin1", offset + 4, offset + 8) === "IDAT") {
      parts.push(png.subarray(offset + 8, offset + 8 + length));
    }
    offset += length + 12;
  }
  // One row of one pixel: a filter byte (irrelevant with no neighbours), then R, G, B.
  const row = inflateSync(Buffer.concat(parts));
  return [row[1] ?? 0, row[2] ?? 0, row[3] ?? 0];
}
