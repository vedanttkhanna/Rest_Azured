import { defineConfig, devices } from "@playwright/test";
const production = process.env.SOLAR_E2E_PRODUCTION === "true";
const local = process.env.SOLAR_E2E_LOCAL === "true";
const port = Number(process.env.SOLAR_E2E_PORT || 5173);
export default defineConfig({
  testDir: "./e2e",
  testMatch: production ? "**/production.spec.ts" : local ? "**/local.spec.ts" : "**/workspace.spec.ts",
  fullyParallel: false,
  outputDir: production ? "test-results/production" : local ? "test-results/local" : "test-results/demo",
  timeout: 45_000,
  use: {
    baseURL: `http://localhost:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "mobile",
      use: {
        ...devices["iPhone 13"],
      },
    },
  ],
  webServer: {
    command: production ? `npm run preview -- --port ${port}` : local ? "npm run dev" : `npm run dev:demo -- --port ${port}`,
    url: `http://localhost:${port}`,
    reuseExistingServer: !process.env.CI,
    timeout: local ? 90_000 : 30_000,
  },
});
