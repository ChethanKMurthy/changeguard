import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

/**
 * End-to-end tests against a real engine and a production build of the web app.
 *
 *   npm run build && npm run test:e2e
 *
 * Locally, already-running servers on the same ports are reused.
 */
const PORT = Number(process.env.E2E_PORT ?? 3100);
const ENGINE_PORT = Number(process.env.E2E_ENGINE_PORT ?? 8100);
const DATABASE = process.env.E2E_DATABASE ?? path.join(os.tmpdir(), `changeguard-e2e-${process.pid}.db`);

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /mobile\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /mobile\.spec\.ts/ },
  ],
  webServer: [
    {
      command: `uv run uvicorn changeguard.api.app:create_default_app --factory --host 127.0.0.1 --port ${ENGINE_PORT}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${ENGINE_PORT}/api/v1/health`,
      env: { CHANGEGUARD_DATABASE_PATH: DATABASE, CHANGEGUARD_RATE_LIMIT_PER_MINUTE: "200" },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `npx next start --hostname 127.0.0.1 --port ${PORT}`,
      url: `http://127.0.0.1:${PORT}`,
      env: { CHANGEGUARD_API_URL: `http://127.0.0.1:${ENGINE_PORT}`, NEXT_TELEMETRY_DISABLED: "1" },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
