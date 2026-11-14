// Looking back through the game, taking it away as PGN or FEN, and the engine panel.

import { readFile } from "node:fs/promises";
import { boardPieces, clickMove, expect, moves, open, playLine, test } from "./helpers";

const AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1";

test("arrow keys step through the game and the board is read-only meanwhile", async ({ page }) => {
  await open(page);
  await playLine(page, [
    ["e2", "e4"],
    ["d2", "d4"],
  ]);
  const current = page.locator(".moves__move[aria-current='step']");
  await expect(current).toHaveText("h6"); // 1. e4 g5 2. d4 h6

  await page.keyboard.press("ArrowLeft");
  await expect(current).toHaveText("d4");
  await expect(page.getByText("Looking at move 3 of 4")).toBeVisible();
  const earlier = await boardPieces(page);
  expect([earlier.d4, earlier.h7, earlier.h6]).toEqual(["white pawn", "black pawn", undefined]);

  await clickMove(page, "g1", "f3"); // nothing moves while looking back
  await expect(moves(page)).toHaveCount(4);
  await expect(page.locator("cg-board square.move-dest")).toHaveCount(0);

  await page.keyboard.press("Home");
  await expect(current).toHaveCount(0);
  await expect(page.getByText("Looking at move 0 of 4")).toBeVisible();
  await expect(page.getByRole("button", { name: "Previous move" })).toBeDisabled();

  await page.keyboard.press("ArrowRight");
  await expect(current).toHaveText("e4");
  await page.getByRole("button", { name: "Copy FEN" }).click();
  await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(AFTER_E4);

  await page.keyboard.press("End");
  await expect(page.getByText(/Looking at move/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Next move" })).toBeDisabled();
});

test("clicking a move shows that position, and a new move returns to the game", async ({ page }) => {
  await open(page);
  await playLine(page, [
    ["e2", "e4"],
    ["d2", "d4"],
  ]);
  await moves(page).first().click();
  await expect(page.getByText("Looking at move 1 of 4")).toBeVisible();
  await page.getByRole("button", { name: "Back to the game" }).click();
  await expect(page.getByText(/Looking at move/)).toHaveCount(0);
  await clickMove(page, "g1", "f3");
  await expect(moves(page)).toHaveCount(6);
});

test("the game can be copied and downloaded as PGN", async ({ page }) => {
  await open(page);
  await playLine(page, [["e2", "e4"]]);

  await page.getByRole("button", { name: "Copy PGN" }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain('[White "Human"]');
  expect(copied).toContain('[Black "chessgm"]');
  expect(copied.trim().endsWith("1. e4 g5 *")).toBe(true);

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Download PGN" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("chessgm-game.pgn");
  const saved = await readFile(await download.path(), "utf8");
  expect(saved).toBe(copied);
});

test("the engine panel shows the search from White's side and can be hidden for good", async ({ page }) => {
  await open(page);
  await expect(page.getByText("The engine's view of the game appears here")).toBeVisible();
  await playLine(page, [["e2", "e4"]]);

  // The scripted engine reports +0.34 for itself; it is Black, so White sees -0.34.
  await expect(page.getByTestId("engine-score")).toContainText("−0.34");
  await expect(page.getByTestId("engine-facts")).toContainText("Depth 5");
  await expect(page.getByTestId("engine-line")).toHaveText("1... g5");
  await expect(page.getByRole("img", { name: /Evaluation −0\.34/ })).toBeVisible();

  await page.getByRole("button", { name: "Hide", exact: true }).click();
  await expect(page.getByRole("region", { name: "Engine" })).toHaveCount(0);
  await expect(page.locator(".eval-bar")).toHaveCount(0);

  await page.reload();
  await expect(page.locator("cg-board piece").first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Engine" })).toHaveCount(0);

  await page.getByRole("button", { name: "Show engine analysis" }).click();
  await expect(page.getByRole("region", { name: "Engine" })).toBeVisible();
});

test("the sound switch is remembered", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Mute sounds" }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "Turn sounds on" })).toBeVisible();
  await page.getByRole("button", { name: "Turn sounds on" }).click();
  await expect(page.getByRole("button", { name: "Mute sounds" })).toBeVisible();
});

test("a second tab follows the same game", async ({ page, context }) => {
  await open(page);
  const other = await context.newPage();
  await other.goto("/");
  await playLine(page, [["e2", "e4"]]);
  await expect(other.getByTestId("moves").locator(".moves__move")).toHaveText(["e4", "g5"]);
  await other.close();
});
