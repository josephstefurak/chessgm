// Timed games. The test server offers one extra control, "0+1": four seconds
// each and a second a move, short enough to watch a flag fall.

import { expect, moves, open, playLine, test } from "./helpers";

test("the time controls are offered and a timed game shows both clocks", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("timer")).toHaveCount(0); // untimed: no clocks at all

  await page.getByRole("button", { name: "New game" }).click();
  const dialog = page.getByRole("dialog", { name: "New game" });
  await expect(dialog.getByText("No clocks. The engine takes a second or two per move.")).toBeVisible();
  await dialog.getByRole("radio", { name: "5 + 3" }).check();
  await expect(dialog.getByText("5 minutes each, plus 3 seconds a move")).toBeVisible();
  await dialog.getByRole("button", { name: "Start game" }).click();

  await expect(page.getByTestId("caption")).toHaveText("5 + 3 · You play White");
  await expect(page.getByTestId("clock-you")).toHaveText("5:00");
  await expect(page.getByTestId("clock-engine")).toHaveText("5:00");
  await expect(page.getByTestId("clock-you")).toHaveAttribute("data-running", "false");

  // Each side's clock first runs on its second move.
  await playLine(page, [["e2", "e4"]]);
  await expect(page.getByTestId("clock-you")).toHaveAttribute("data-running", "true");
  await expect(page.getByTestId("clock-you")).not.toHaveText("5:00");
});

test("running out of time loses the game", async ({ page }) => {
  await open(page, "white", "0+1");
  await expect(page.getByTestId("clock-you")).toHaveText("0:04.0");
  await playLine(page, [["e2", "e4"]]);
  await expect(page.getByTestId("clock-you")).toHaveAttribute("data-low", "true");

  const result = page.getByTestId("result");
  await expect(result).toContainText("You lost", { timeout: 8_000 });
  await expect(result).toContainText("on time");
  await expect(page.getByTestId("clock-you")).toHaveText("0:00.0");
  await expect(moves(page)).toHaveCount(2);
});
