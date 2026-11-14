import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

// Browser tests run against the production build (`npm run build` first), served
// by the real Python server. Two servers are started:
//   scripted: the shipped server code with a scripted engine, so replies are exact
//   real:     `python gui.py` exactly as a person runs it, for one smoke test
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const condaPython = "/opt/anaconda3/envs/lichessbot/bin/python";
const python = process.env.CHESSGM_PYTHON ?? (existsSync(condaPython) ? condaPython : "python");

const SCRIPTED_PORT = 8791;
const REAL_PORT = 8792;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1, // one server holds one game
  forbidOnly: true,
  retries: 0,
  reporter: [["list"]],
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    ...devices["Desktop Chrome"],
    viewport: { width: 1280, height: 800 },
    permissions: ["clipboard-read", "clipboard-write"],
    reducedMotion: "reduce",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "scripted",
      testIgnore: /real-engine\.spec\.ts/,
      use: { baseURL: `http://127.0.0.1:${SCRIPTED_PORT}` },
    },
    {
      name: "real-engine",
      testMatch: /real-engine\.spec\.ts/,
      use: { baseURL: `http://127.0.0.1:${REAL_PORT}` },
    },
  ],
  webServer: [
    {
      command: `${python} -m tests.gui.e2e_server --port ${SCRIPTED_PORT}`,
      cwd: repoRoot,
      url: `http://127.0.0.1:${SCRIPTED_PORT}/api/state`,
      reuseExistingServer: false,
    },
    {
      command: `${python} gui.py --port ${REAL_PORT} --time 0.2 --no-browser`,
      cwd: repoRoot,
      url: `http://127.0.0.1:${REAL_PORT}/api/state`,
      reuseExistingServer: false,
    },
  ],
});
