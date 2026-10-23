import { defineConfig } from "@playwright/test";

// Drives the real stack (compose) through a real browser. Uses the machine's installed Chrome so no browser download
// is needed; set E2E_CHANNEL= (empty) after `npx playwright install chromium` to use the bundled Chromium instead.
export default defineConfig({
  testDir: ".",
  timeout: 180_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8443",
    channel: process.env.E2E_CHANNEL === undefined ? "chrome" : process.env.E2E_CHANNEL || undefined,
    viewport: { width: 1440, height: 900 },
    colorScheme: "light",
    acceptDownloads: true,
    trace: "retain-on-failure",
  },
});
