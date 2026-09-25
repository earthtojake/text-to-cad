import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

/**
 * The other shape ACP allows for the same decision.
 *
 * An agent can send its modes as `modes` — switched by `session/set_mode`,
 * which `session.spec.ts` drives — or as a `mode`-category config option
 * switched by `session/set_config_option`. Both real adapters send both;
 * an adapter that sends only the option would, before this, have had no
 * mode chip at all, and the mode is the app's one permission control. So
 * the fake agent runs here with `--mode-option`: no `modes`, the same list
 * as a config option, and the one chip has to work the same way on both
 * screens.
 */
declare const window: {
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    settings: { set(patch: { theme: string }): Promise<unknown> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;

test.beforeAll(async () => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-mode-option-"));
  project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-mode-option-project-"));
  fs.writeFileSync(path.join(project, "README.md"), "# Scratch\n");
  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: {
      ...process.env,
      NODE_ENV: "test",
      HARDCORE_FAKE_AGENT: fakeAgent,
      HARDCORE_FAKE_AGENT_ARGS: "--mode-option",
    },
  });
  page = await app.firstWindow();
  page.on("pageerror", (error) => console.error(`[renderer] ${error.message}\n${error.stack ?? ""}`));
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), project);
});

test.afterAll(async () => {
  await app?.close();
  for (const dir of [userData, project]) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("an agent that sends its modes as a config option gets the same one chip", async () => {
  const newRow = page.locator("[data-new-session] [data-composer-row]");
  // Drawn from the cached snapshot's `mode` option, on the agent's own auto
  // preset — the probe is what fills it in, so this waits for one.
  await expect(newRow.locator("[data-chip=mode]")).toContainText("Auto", { timeout: 30_000 });
  await newRow.locator("[data-chip=mode]").click();
  const menu = page.getByRole("menu");
  await expect(menu.getByRole("menuitemradio", { name: "Manual", exact: true })).toBeVisible();
  // The note belongs to the mode, not to the shape it arrived in.
  await expect(menu.getByRole("menuitemradio", { name: /Full access/ })).toContainText("Never asks");
  await menu.getByRole("menuitemradio", { name: "Manual", exact: true }).click();
  await expect(newRow.locator("[data-chip=mode]")).toContainText("Manual");

  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("applied");
  await composer.press("Enter");
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 30_000 });
  // Created in Manual, which for this agent means no `set_config_option` for
  // the mode at all: `default` is where it starts.
  const reply = page.locator("[data-turn][data-role=agent]").last();
  await expect(reply).toContainText("in default");
  await expect(reply).not.toContainText("mode:");
  await expect(page.locator("[data-composer-row] [data-chip=mode]")).toContainText("Manual");

  // And the live chip sets the option: full access, and the request that
  // Manual would have shown is never made.
  await page.locator("[data-composer-row] [data-chip=mode]").click();
  await page.getByRole("menu").getByRole("menuitemradio", { name: /Full access/ }).click();
  await expect(page.locator("[data-composer-row] [data-chip=mode]")).toContainText("Full access");
  await composer.fill("permission to run ls");
  await composer.press("Enter");
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 30_000 });
  await expect(page.locator("[data-permission]")).toHaveCount(0);
});
