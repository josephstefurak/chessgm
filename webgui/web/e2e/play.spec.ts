// Playing a game: moving, the engine's reply, takeback, resigning, starting again.
// The engine here is scripted: as Black it prefers g5, h6, a6, a5 in that order.

import { boardPieces, clickMove, dragMove, expect, moves, open, playLine, test } from "./helpers";

test("a clicked move is played and the engine answers", async ({ page }) => {
  await open(page);
  await expect(page.getByTestId("caption")).toHaveText("Untimed · You play White");
  await expect(page.getByText("Your move. White plays first.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Take back" })).toBeDisabled();

  await clickMove(page, "e2", "e4");
  await expect(moves(page)).toHaveText(["e4", "g5"]);
  const board = await boardPieces(page);
  expect(board.e4).toBe("white pawn");
  expect(board.g5).toBe("black pawn");
  expect(board.e2).toBeUndefined();
  expect(board.g7).toBeUndefined();
  expect(Object.keys(board)).toHaveLength(32);
  await expect(page.locator(".strip__status", { hasText: "Your move" })).toBeVisible();
  await expect(page.getByTestId("announcer")).toHaveText("Black played g5.");
  await expect(page.getByRole("button", { name: "Take back" })).toBeEnabled();
});

test("a dragged move is played", async ({ page }) => {
  await open(page);
  await dragMove(page, "g1", "f3");
  await expect(moves(page)).toHaveText(["Nf3", "g5"]);
});

test("legal destinations are shown and an illegal square does nothing", async ({ page }) => {
  await open(page);
  const { squareCentre } = await import("./helpers");
  const e2 = await squareCentre(page, "e2");
  await page.mouse.click(e2.x, e2.y);
  await expect(page.locator("cg-board square.move-dest")).toHaveCount(2); // e3 and e4
  const e6 = await squareCentre(page, "e6");
  await page.mouse.click(e6.x, e6.y);
  await expect(page.locator("cg-board square.move-dest")).toHaveCount(0);
  await expect(page.getByText("Your move. White plays first.")).toBeVisible();
});

test("the last move and a check are highlighted", async ({ page }) => {
  await open(page);
  await playLine(page, [["e2", "e4"]]);
  await expect(page.locator("cg-board square.last-move")).toHaveCount(2);
  await clickMove(page, "d1", "h5");
  await expect(moves(page)).toHaveCount(4);
  await clickMove(page, "h5", "f7"); // Qxf7+ (the king can take: no bishop behind it)
  await expect(moves(page).nth(4)).toHaveText("Qxf7+");
});

test("takeback undoes the engine's reply and your move", async ({ page }) => {
  await open(page);
  await playLine(page, [
    ["e2", "e4"],
    ["d2", "d4"],
  ]);
  await expect(moves(page)).toHaveCount(4);
  await page.getByRole("button", { name: "Take back" }).click();
  await expect(moves(page)).toHaveText(["e4", "g5"]);
  await page.getByRole("button", { name: "Take back" }).click();
  await expect(page.getByText("Your move. White plays first.")).toBeVisible();
  const board = await boardPieces(page);
  expect([board.e2, board.g7, board.e4, board.g5]).toEqual(["white pawn", "black pawn", undefined, undefined]);
  await clickMove(page, "d2", "d4"); // the board still works after a takeback
  await expect(moves(page)).toHaveText(["d4", "g5"]);
});

test("resigning asks once more, then ends the game", async ({ page }) => {
  await open(page);
  await playLine(page, [["e2", "e4"]]);
  await page.getByRole("button", { name: "Resign" }).click();
  await expect(page.getByTestId("result")).toHaveCount(0); // one click is not enough
  await page.getByRole("button", { name: "Confirm resign" }).click();

  const result = page.getByTestId("result");
  await expect(result).toContainText("You lost");
  await expect(result).toContainText("by resignation");
  await expect(page.getByRole("button", { name: "Resign" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Take back" })).toBeDisabled();
  await expect(page.getByTestId("announcer")).toHaveText("You lost by resignation.");

  await result.getByRole("button", { name: "Rematch" }).click();
  await expect(page.getByTestId("result")).toHaveCount(0);
  await expect(page.getByText("Your move. White plays first.")).toBeVisible();
});

test("checkmate ends the game in your favour", async ({ page }) => {
  await open(page);
  await playLine(page, [
    ["e2", "e4"],
    ["d1", "h5"],
    ["f1", "c4"],
  ]);
  await clickMove(page, "h5", "f7");
  await expect(moves(page).last()).toHaveText("Qxf7#");
  const result = page.getByTestId("result");
  await expect(result).toContainText("You won");
  await expect(result).toContainText("by checkmate");
  await expect(page.locator("cg-board square.check")).toHaveCount(1);
  const board = await boardPieces(page);
  expect(board.f7).toBe("white queen"); // the captured pawn is gone and the queen stands there
  expect(board.h5).toBeUndefined();
  expect(Object.keys(board)).toHaveLength(31);
});

test("promotion asks for a piece", async ({ page }) => {
  await open(page);
  await playLine(page, [
    ["h2", "h4"],
    ["h4", "g5"],
    ["g5", "h6"],
    ["h6", "h7"],
  ]);
  await clickMove(page, "h7", "g8");
  const picker = page.getByRole("dialog", { name: "Choose a piece to promote to" });
  await expect(picker.getByRole("button")).toHaveText(["", "", "", ""]);
  await expect(picker.getByRole("button", { name: "Queen" })).toBeFocused();
  await expect(moves(page)).toHaveCount(8); // nothing is played until a piece is chosen

  await page.keyboard.press("Escape"); // changing your mind puts the pawn back
  await expect(picker).toHaveCount(0);
  await expect(moves(page)).toHaveCount(8);

  await clickMove(page, "h7", "g8");
  await picker.getByRole("button", { name: "Knight" }).click();
  await expect(moves(page).nth(8)).toHaveText("hxg8=N");
  await expect.poll(async () => (await boardPieces(page)).g8).toBe("white knight");
  expect((await boardPieces(page)).h7).toBeUndefined();
});

test("a new game as Black turns the board and the engine opens", async ({ page }) => {
  await open(page);
  await playLine(page, [["e2", "e4"]]);
  await page.getByRole("button", { name: "New game" }).click();
  const dialog = page.getByRole("dialog", { name: "New game" });
  await expect(dialog.getByText("Starting a new game ends the one in progress.")).toBeVisible();
  await dialog.getByRole("radio", { name: "Black" }).check();
  await dialog.getByRole("button", { name: "Start game" }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByTestId("caption")).toHaveText("Untimed · You play Black");
  await expect(page.locator(".cg-wrap")).toHaveClass(/orientation-black/);
  await expect(moves(page)).toHaveText(["e4"]);
  await clickMove(page, "e7", "e5");
  await expect(moves(page)).toHaveCount(3);

  // The dialog remembers what was chosen.
  await page.getByRole("button", { name: "New game" }).click();
  await expect(dialog.getByRole("radio", { name: "Black" })).toBeChecked();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("flipping the board swaps the two sides", async ({ page }) => {
  await open(page);
  await expect(page.locator(".strip__name").first()).toHaveText("chessgm");
  await page.getByRole("button", { name: "Flip board" }).click();
  await expect(page.locator(".cg-wrap")).toHaveClass(/orientation-black/);
  await expect(page.locator(".strip__name").first()).toHaveText("You");
  await page.keyboard.press("f");
  await expect(page.locator(".cg-wrap")).toHaveClass(/orientation-white/);
});
