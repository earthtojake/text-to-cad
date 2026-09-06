import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

/**
 * What a restart keeps: the project, the session row, and the transcript
 * behind it. The app is launched twice against ONE user-data directory; the
 * second launch has to list what the first one made, and selecting the
 * session has to replay its transcript through `session/load` — the fake
 * agent answers that with an "earlier prompt" / "earlier reply" pair, so
 * the reply's presence is the proof the load happened.
 *
 * The first launch is quit through `app.quit()` (Playwright's `close`), the
 * way a person quits: every teardown in `before-quit` runs, including the
 * database close. A launch that was killed instead would test sqlite's WAL
 * recovery, which is not the thing that lost Jake's projects.
 */
declare const window: {
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    sessions: { list(input: Record<string, never>): Promise<Array<{ id: string; title: string; acpSessionId: string | null }>> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

let userData: string;
let project: string;

test.beforeAll(() => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-persist-"));
  project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-persist-project-"));
  fs.writeFileSync(path.join(project, "README.md"), "# Persist\n");
});

test.afterAll(() => {
  for (const dir of [userData, project]) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

async function launch(): Promise<{ app: ElectronApplication; page: Page }> {
  const app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: fakeAgent },
  });
  const page = await app.firstWindow();
  page.on("pageerror", (error) => {
    console.error(`[renderer] ${error.message}\n${error.stack ?? ""}`);
  });
  await page.waitForLoadState("domcontentloaded");
  return { app, page };
}

test("a project and its session survive a quit and a relaunch", async () => {
  test.setTimeout(120_000);
  const projectName = path.basename(project);

  // First launch: a project, one prompt to the fake agent.
  const first = await launch();
  await first.page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), project);
  await expect(first.page.getByRole("heading", { name: `What should we build in ${projectName}?` })).toBeVisible();
  const strip = first.page.locator("[data-context-strip]");
  await expect(strip.locator("[data-chip=agent]")).not.toContainText("Choose an agent");
  const composer = first.page.getByPlaceholder("Do anything");
  await composer.fill("keep this one around");
  await composer.press("Enter");
  const view = first.page.locator("[data-session-view]");
  await expect(view).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });
  await expect(first.page.locator("[data-session-row]")).toContainText("keep this one around");
  const before = await first.page.evaluate(() => window.hardcore.sessions.list({}));
  expect(before).toHaveLength(1);
  expect(before[0]?.acpSessionId).not.toBeNull();

  // The same way a person quits: app.quit(), every before-quit hook, the
  // database closed on the way out.
  await first.app.close();

  // Second launch, same user-data directory.
  const second = await launch();
  try {
    // The project is back, and the session row under it.
    await expect(second.page.getByText(projectName).first()).toBeVisible();
    const row = second.page.locator("[data-session-row]");
    await expect(row).toHaveCount(1);
    await expect(row).toContainText("keep this one around");
    const after = await second.page.evaluate(() => window.hardcore.sessions.list({}));
    expect(after.map((session) => session.id)).toEqual(before.map((session) => session.id));

    // Selecting it resumes the transcript: `session/load` replays it, and the
    // fake agent's replay is the pair below.
    await row.click();
    await expect(second.page.locator("[data-session-view]")).toBeVisible();
    await expect(second.page.getByText("earlier reply")).toBeVisible({ timeout: 20_000 });
    await expect(second.page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
  } finally {
    await second.app.close();
  }
});
