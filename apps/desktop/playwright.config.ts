import { defineConfig } from "@playwright/test";

/**
 * Electron end-to-end. `_electron.launch` runs the built app — `npm run build`
 * has to have happened first — against a throwaway user-data directory, so the
 * suite never reads or writes the developer's own projects and settings.
 *
 * No `projects` and no browsers: nothing here uses a Playwright browser, so
 * `npx playwright install` is not a prerequisite.
 */
/**
 * The suite's windows are never shown.
 *
 * Every spec launches the real app, and each launch used to put a window over
 * whatever the person at this machine was doing — a dozen of them per run,
 * stealing the screen if not the focus. `HARDCORE_E2E_HIDDEN` tells main to
 * skip `show()` altogether (`ready-to-show` in src/main/index.ts): Playwright
 * drives the renderer over the DevTools protocol, which needs a live web
 * contents and not a visible window, so screenshots, bounding boxes, the
 * mouse, the keyboard and `toBeVisible()` all work exactly as before — the
 * screenshots are taken by Chromium, not by the compositor on screen.
 *
 * Set here rather than in each spec's `env` because the specs spread
 * `process.env`, and set only when unset: `HARDCORE_E2E_HIDDEN=0 npm run e2e`
 * shows the windows again, which is how you watch a spec fail.
 */
process.env.HARDCORE_E2E_HIDDEN ??= "1";

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
