// The page itself: how it is drawn, how it fits, and what the server sends with it.

import { expect, open, pixel, squareCentre, test } from "./helpers";

function rgb(text: string): [number, number, number] {
  const hex = text.trim().replace("#", "");
  return [0, 2, 4].map((at) => parseInt(hex.slice(at, at + 2), 16)) as [number, number, number];
}

test("the squares are the theme's colours, with a dark square in each player's left corner", async ({ page }) => {
  await open(page);
  const [light, dark] = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    return [style.getPropertyValue("--board-light"), style.getPropertyValue("--board-dark")];
  });
  const size = ((await page.locator("cg-board").boundingBox())?.width ?? 0) / 8;
  const colourOf = async (square: string) => {
    const centre = await squareCentre(page, square);
    // Sample the edge of the square, clear of any piece or coordinate label.
    return pixel(page, Math.round(centre.x - size * 0.4), Math.round(centre.y));
  };
  expect(await colourOf("a1")).toEqual(rgb(dark ?? ""));
  expect(await colourOf("h8")).toEqual(rgb(dark ?? ""));
  expect(await colourOf("h1")).toEqual(rgb(light ?? ""));
  expect(await colourOf("a8")).toEqual(rgb(light ?? ""));
  expect(await colourOf("d1")).toEqual(rgb(light ?? "")); // the white queen starts on her own colour
});

test("the whole board fits a laptop screen without scrolling", async ({ page }) => {
  await open(page);
  const fits = await page.evaluate(() => ({
    scrollsDown: document.documentElement.scrollHeight > window.innerHeight,
    scrollsAcross: document.documentElement.scrollWidth > window.innerWidth,
  }));
  expect(fits).toEqual({ scrollsDown: false, scrollsAcross: false });
  const board = await page.locator("cg-board").boundingBox();
  expect(board?.width).toBeGreaterThan(450);
  expect(board?.width).toBeCloseTo(board?.height ?? 0, 0);
});

for (const viewport of [
  { width: 390, height: 844 },
  { width: 820, height: 600 },
]) {
  test(`a ${viewport.width} by ${viewport.height} window stacks the page and keeps the board on screen`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await open(page);
    const board = await page.locator("cg-board").boundingBox();
    if (board === null) throw new Error("no board");
    expect(board.x).toBeGreaterThanOrEqual(0);
    expect(board.x + board.width).toBeLessThanOrEqual(viewport.width);
    expect(board.y + board.height).toBeLessThanOrEqual(viewport.height);
    expect(board.width).toBeGreaterThanOrEqual(280);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
    await expect(page.getByRole("button", { name: "New game" })).toBeVisible();
  });
}

test("the page is served with its security headers and loads nothing from elsewhere", async ({
  page,
  baseURL,
}) => {
  const elsewhere: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.protocol !== "data:" && url.origin !== baseURL) elsewhere.push(request.url());
  });
  const response = await page.goto("/");
  await expect(page.locator("cg-board piece").first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);

  const headers = response?.headers() ?? {};
  expect(headers["content-security-policy"]).toContain("script-src 'self'");
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["cache-control"]).toBe("no-store");
  expect(elsewhere).toEqual([]);

  const fonts = await page.evaluate(() =>
    ["Newsreader Variable", "Geist Variable", "Geist Mono Variable"].map((family) =>
      document.fonts.check(`16px "${family}"`),
    ),
  );
  expect(fonts).toEqual([true, true, true]);
});

test("the page can be used from the keyboard", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "New game" }).focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "New game" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("radio", { name: "White" })).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(dialog.getByRole("radio", { name: "Black" })).toBeChecked();
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId("caption")).toHaveText("Untimed · You play Black");
});
