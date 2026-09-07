import { defineConfig } from "@playwright/test";

/**
 * Electron end-to-end. `_electron.launch` runs the built app — `npm run build`
 * has to have happened first — against a throwaway user-data directory, so the
 * suite never reads or writes the developer's own projects and settings.
 *
 * No `projects` and no browsers: nothing here uses a Playwright browser, so
 * `npx playwright install` is not a prerequisite.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  // Electron's first launch pays for the window, the database and the bundle.
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? "list" : [["list"]],
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  use: {
    trace: "retain-on-failure",
  },
});
