// Sounds cannot be heard in a test, but they can be counted: every sound starts
// at least one audio source, so the test watches the browser's audio engine.

import { expect, open, playLine, test } from "./helpers";

declare global {
  interface Window {
    soundsStarted: number;
  }
}

test("moves make a sound, and muting stops them", async ({ page }) => {
  await page.addInitScript(() => {
    window.soundsStarted = 0;
    for (const node of [AudioBufferSourceNode, OscillatorNode]) {
      const start = node.prototype.start;
      node.prototype.start = function (this: AudioScheduledSourceNode, ...args: [number?]) {
        window.soundsStarted += 1;
        return start.apply(this, args);
      };
    }
  });
  const started = () => page.evaluate(() => window.soundsStarted);

  await open(page);
  expect(await started()).toBe(0); // nothing plays before the reader does anything

  await playLine(page, [["e2", "e4"]]);
  await expect.poll(started).toBe(2); // your move, then the engine's

  await playLine(page, [["d2", "d4"]]);
  await expect.poll(started).toBe(4);

  await page.getByRole("button", { name: "Mute sounds" }).click();
  await playLine(page, [["g1", "f3"]]);
  expect(await started()).toBe(4);

  await page.getByRole("button", { name: "Turn sounds on" }).click();
  await page.getByRole("button", { name: "Resign" }).click();
  await page.getByRole("button", { name: "Confirm resign" }).click();
  await expect(page.getByTestId("result")).toBeVisible();
  await expect.poll(started).toBe(7); // the end-of-game sound: one knock and two tones
});
