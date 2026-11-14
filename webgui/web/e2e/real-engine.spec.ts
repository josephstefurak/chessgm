// One test against `python gui.py` exactly as a person runs it, real engine included.
// It only checks that the engine answers; what it answers is the engine's business.

import { clickMove, expect, moves, open, test } from "./helpers";

test("the real engine answers a move and reports its search", async ({ page }) => {
  await open(page);
  await clickMove(page, "a2", "a4"); // 1. a4 is not in the opening book, so it must search
  await expect(moves(page)).toHaveCount(2, { timeout: 15_000 });
  await expect(moves(page).first()).toHaveText("a4");
  await expect(page.getByTestId("engine-facts")).toContainText(/Depth \d+/);
  await expect(page.getByTestId("engine-score")).toContainText(/[+−]?\d+\.\d\d|M\d+/);
  await expect(page.getByTestId("engine-line")).toContainText("1...");
});
