import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

/**
 * One real Codex session through the built app (plan §13, P2's gate). Not
 * part of `npm run e2e`: it needs a signed-in `codex` on the machine and
 * spends real tokens, so it runs only with `HARDCORE_E2E_CODEX=1`. The
 * screenshot it writes, `session-codex.png`, is the one to compare against
 * the Codex reference.
 */
declare const window: {
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    settings: { set(patch: { theme?: string; defaultAgentId?: string }): Promise<unknown> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");

test.skip(!process.env.HARDCORE_E2E_CODEX, "set HARDCORE_E2E_CODEX=1 to run a real Codex session");

let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;

test.beforeAll(async () => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-codex-"));
  project = fs.mkdtempSync(path.join("/private/tmp", "hardcore-codex-scratch-"));
  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test" },
  });
  page = await app.firstWindow();
  page.on("pageerror", (error) => console.error(`[renderer] ${error.message}`));
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark", defaultAgentId: "codex" }));
  await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), project);
});

test.afterAll(async () => {
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
});

test("Codex writes a file, runs a command and answers", async () => {
  test.setTimeout(240_000);
  await expect(page.locator("[data-chip=agent]")).toContainText("Codex");
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill(
    "Create a file named hello.txt containing the single line 'hello from codex', then run ls -la and tell me what you see. Keep the answer to two sentences.",
  );
  await composer.press("Enter");

  const view = page.locator("[data-session-view]");
  await expect(view).toBeVisible({ timeout: 60_000 });
  await expect(page.locator("[data-activity-row], [data-activity-group]").first()).toBeVisible({ timeout: 120_000 });
  await shoot("session-codex-streaming.png");
  await expect(view).toHaveAttribute("data-session-status", "idle", { timeout: 180_000 });
  await expect(page.locator("[data-chip=model]")).toBeVisible();
  await expect(page.locator("[data-part=usage]").last()).toContainText("tokens");
  await expect(page.locator("[data-context-footer]")).toContainText("context");
  await shoot("session-codex.png");

  // The command Codex ran is one row with its text inline; expanding it
  // shows what the terminal printed.
  const rows = page.locator("[data-activity-row]");
  await expect(rows.first()).toBeVisible();
  const exec = page.locator("[data-activity-row][data-status=completed]").filter({ hasText: "hello" });
  // Codex decides how it does the job; one command, two, or a write tool.
  // The row that names hello.txt expands to the terminal or the diff.
  if ((await exec.count()) > 0) {
    await exec.first().getByRole("button").first().click();
    await expect(page.locator("[data-tool-detail]").first()).toContainText("hello");
    await shoot("session-codex-expanded.png");
  }
  expect(fs.existsSync(path.join(project, "hello.txt"))).toBe(true);
});

async function shoot(name: string) {
  await page.screenshot({ path: path.join(screenshots, name), animations: "disabled" });
}
