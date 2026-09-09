import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

/**
 * Opening a session, and what it costs (README, "Opening a session").
 *
 * Clicking a session used to be a spinner for the two and a half seconds a
 * spawn, an `initialize` and a `session/load` take. Three mechanisms stand
 * between the click and the transcript now, and this spec is each of them
 * from the outside:
 *
 *   1. the snapshot — a disconnected session paints its transcript from
 *      sqlite at once, with `Reconnecting…` in the composer's row rather
 *      than a loading screen, and the live state replaces it when it lands
 *   2. the keep-alive — switching between two sessions closes neither, so
 *      the spinner never comes back for either of them
 *   3. the warm pool — the first session opened after a launch adopts an
 *      adapter that was spawned before it was asked for, which the timing
 *      log reports as `warm=yes`
 *
 * The fake agent is instant, and an instant reconnect is a state nobody can
 * look at — so `--load-delay` holds its `session/load` for a second and a
 * bit, which is what a real adapter takes.
 */
declare const window: {
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    sessions: { list(input: Record<string, never>): Promise<{ id: string; title: string }[]> };
    settings: { set(patch: { theme: string }): Promise<unknown> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

/** How long the fake agent holds `session/load`, so the reconnect is visible. */
const LOAD_DELAY_MS = 1_200;

/** What "paints at once" means: a frame or two, not a spawn. */
const PAINT_BUDGET_MS = 300;

type Launched = { app: ElectronApplication; page: Page; lines: string[] };

async function launch(options: {
  userData: string;
  fakeArgs?: string;
  prewarm?: boolean;
}): Promise<Launched> {
  const lines: string[] = [];
  const app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${options.userData}`],
    env: {
      ...process.env,
      NODE_ENV: "test",
      HARDCORE_FAKE_AGENT: fakeAgent,
      ...(options.fakeArgs ? { HARDCORE_FAKE_AGENT_ARGS: options.fakeArgs } : {}),
      ...(options.prewarm ? { HARDCORE_PREWARM: "1" } : {}),
    },
  });
  // Main's timing line is the only place the phases of a load are said
  // (src/main/acp/timing.ts), and it is what the warm assertion reads.
  app.process().stdout?.on("data", (chunk: Buffer) => lines.push(...String(chunk).split("\n")));
  app.process().stderr?.on("data", (chunk: Buffer) => lines.push(...String(chunk).split("\n")));
  const page = await app.firstWindow();
  page.on("pageerror", (error) => {
    console.error(`[renderer] ${error.message}\n${error.stack ?? ""}`);
  });
  await page.waitForLoadState("domcontentloaded");
  return { app, page, lines };
}

/** Start a thread with one prompt, and answer with its row id. */
async function newThread(page: Page, prompt: string): Promise<string> {
  const before = await page.evaluate(() => window.hardcore.sessions.list({}));
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill(prompt);
  await composer.press("Enter");
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", {
    timeout: 30_000,
  });
  const after = await page.evaluate(() => window.hardcore.sessions.list({}));
  const created = after.find((session) => !before.some((old) => old.id === session.id));
  if (!created) {
    throw new Error("no session was created");
  }
  return created.id;
}

test.describe("opening a session", () => {
  let app: ElectronApplication;
  let page: Page;
  let userData: string;
  let project: string;

  test.beforeAll(async () => {
    userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-reconnect-"));
    project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-reconnect-project-"));
    fs.writeFileSync(path.join(project, "README.md"), "# Reconnect\n");
    ({ app, page } = await launch({ userData, fakeArgs: `--load-delay ${LOAD_DELAY_MS}` }));
    await page.evaluate((value) => window.hardcore.settings.set({ theme: value }), "dark");
    await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), project);
    await expect(page.getByRole("heading", { name: /What should we build in/ })).toBeVisible();
    // The composer sends nothing until the agent has been probed for what it
    // offers, which on a first run spawns the adapter.
    await expect(page.locator("[data-new-session] [data-chip=model]")).toContainText("Fast", {
      timeout: 30_000,
    });
  });

  test.afterAll(async () => {
    await app?.close();
    for (const dir of [userData, project]) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  test("a disconnected session paints its transcript at once and reconnects behind it", async () => {
    test.setTimeout(180_000);
    const first = await newThread(page, "first message here");
    await page.getByRole("button", { name: "New", exact: true }).click();
    const second = await newThread(page, "second message here");

    const firstRow = page.locator(`[data-session-row="${first}"]`);
    const secondRow = page.locator(`[data-session-row="${second}"]`);

    // The adapter of the session that is no longer on screen is still there
    // (src/main/acp/live.ts), so going back to it is a paint and no more.
    await firstRow.click();
    await expect(page.locator("[data-turn][data-role=user]").first()).toContainText("first message here");
    await expect(page.locator("[data-connecting]")).toHaveCount(0);
    await expect(page.locator("[data-reconnecting]")).toHaveCount(0);

    // Now take the adapter away, the way the header's menu does: main kills
    // it and the renderer forgets the state, which leaves the snapshot as
    // the only thing anybody has.
    await page.getByRole("button", { name: "Session actions" }).click();
    await page.getByRole("menuitem", { name: "Disconnect agent" }).click();
    await secondRow.click();
    await expect(page.locator("[data-turn][data-role=user]").first()).toContainText("second message here");

    // The click this whole change is about. The transcript comes off the
    // disk inside a frame or two, the reconnect is a line in the composer's
    // row, and there is no loading screen anywhere.
    const started = Date.now();
    await firstRow.click();
    await expect(page.locator("[data-turn][data-role=user]").first()).toContainText("first message here");
    const painted = Date.now() - started;
    expect(painted).toBeLessThan(PAINT_BUDGET_MS);
    await expect(page.locator("[data-connecting]")).toHaveCount(0);
    await expect(page.locator("[data-reconnecting]")).toBeVisible();
    // The composer is not blocked by a reconnect: a prompt sent now is
    // queued against the load.
    await expect(page.getByPlaceholder("Do anything")).toBeEnabled();

    // …and the live state replaces the picture. The fake agent's
    // `session/load` replays a pair of its own, so the pair's arrival is the
    // proof the load landed rather than the snapshot still being on screen.
    await expect(page.getByText("earlier reply")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("[data-reconnecting]")).toHaveCount(0);
    await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
    // Replayed once: the reducer events of a replay are dropped while the
    // snapshot is on screen, or every turn would arrive twice.
    await expect(page.getByText("earlier prompt")).toHaveCount(1);
  });

  test("switching between two sessions never shows the spinner", async () => {
    test.setTimeout(120_000);
    const sessions = await page.evaluate(() => window.hardcore.sessions.list({}));
    expect(sessions.length).toBeGreaterThanOrEqual(2);
    const rows = sessions.slice(0, 2).map((session) => page.locator(`[data-session-row="${session.id}"]`));

    for (let round = 0; round < 5; round += 1) {
      for (const row of rows) {
        await row.click();
        await expect(page.locator("[data-session-view]")).toBeVisible();
        // Neither the loading screen nor a reconnect: both adapters are up.
        await expect(page.locator("[data-connecting]")).toHaveCount(0);
        await expect(page.locator("[data-reconnecting]")).toHaveCount(0);
      }
    }
  });
});

/**
 * The warm pool, which only exists on the second launch onwards: the index
 * is what says which agents are worth an idle adapter, and a first launch
 * has no sessions in it. So this is two launches against one user-data
 * directory — one to leave a session behind, one to open it — and the
 * assertion is main's own timing line.
 */
test("the first session opened after a launch adopts the warm adapter", async () => {
  test.setTimeout(180_000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-warm-"));
  const project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-warm-project-"));
  fs.writeFileSync(path.join(project, "README.md"), "# Warm\n");

  const first = await launch({ userData });
  try {
    await first.page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), project);
    await expect(first.page.locator("[data-new-session] [data-chip=model]")).toContainText("Fast", {
      timeout: 30_000,
    });
    await newThread(first.page, "leave me here");
  } finally {
    await first.app.close();
  }

  const second = await launch({ userData, prewarm: true });
  try {
    const row = second.page.locator("[data-session-row]").first();
    await expect(row).toContainText("leave me here", { timeout: 30_000 });
    // The pre-warm is delayed so it does not compete with the first paint,
    // and it says so on stdout when the adapter is up.
    await expect
      .poll(() => second.lines.some((line) => /\[acp\] claude-code warmed in /.test(line)), {
        timeout: 60_000,
      })
      .toBe(true);

    await row.click();
    await expect(second.page.getByText("earlier reply")).toBeVisible({ timeout: 30_000 });
    // The load adopted the idle adapter: no spawn and no `initialize` were
    // paid for on the critical path, which is what `warm=yes` means.
    const load = second.lines.find((line) => /\[acp\] load /.test(line));
    expect(load).toBeDefined();
    expect(load).toContain("warm=yes");
    // And the pool put another one up behind it, for the next session.
    await expect
      .poll(() => second.lines.filter((line) => /\[acp\] claude-code warmed in /.test(line)).length, {
        timeout: 60_000,
      })
      .toBeGreaterThanOrEqual(2);
  } finally {
    await second.app.close();
    for (const dir of [userData, project]) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }
});
