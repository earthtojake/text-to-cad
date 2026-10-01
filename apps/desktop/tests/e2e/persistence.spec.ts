import fs from "node:fs";
import path from "node:path";

import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import type { TextToCadApi } from "../../src/shared/ipc";
import { launch, scratch, type Launched } from "./launch";

/**
 * What a quit and a relaunch keep, and what opening a session then costs —
 * two launches against ONE user-data directory, which is the only way to test
 * either.
 *
 * The first launch is quit through `app.quit()` (Playwright's `close`), the
 * way a person quits: every `before-quit` teardown runs, the database close
 * included. It leaves behind a project, two sessions, the model, effort and
 * mode the person picked (the effort per model, the mode per provider), an
 * agent-given title, and a Light theme under an OS in dark.
 *
 * The second launch has to come back to all of it: the window's first frame
 * in the stored theme; the rows; the chips drawn from the cache with no probe;
 * the transcript replayed through `session/load` (the fake agent answers that
 * with an "earlier prompt" / "earlier reply" pair, so the reply is the proof).
 * And opening a session is cheap (README, "Opening a session"): the first one
 * adopts an adapter the warm pool spawned before it was asked (`warm=yes` in
 * main's timing line); switching between two live sessions never shows the
 * spinner; and a disconnected one paints its transcript from sqlite while it
 * reconnects behind it. `--load-delay` holds the fake's `session/load` for a
 * second and a bit, which is what a real adapter takes, so the reconnect is a
 * state that can be seen.
 */

declare const window: { textToCad: TextToCadApi };

const LOAD_DELAY = "--load-delay 1200";

let userData: string;
let project: string;
let titled: string;
let launchedIds: string[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  userData = scratch("persist");
  project = scratch("persist-project");
  fs.writeFileSync(path.join(project, "README.md"), "# Persist\n");
});

test.afterAll(() => {
  for (const dir of [userData, project]) fs.rmSync(dir, { recursive: true, force: true });
});

/**
 * The app on the shared profile. Pre-warming is on for the second launch — it is under test —
 * and it warms a project's CAD runtime as well as its agents, so the runtime is pointed
 * nowhere: this spec starts no viewer and no daemon.
 */
function start(options: { prewarm?: boolean; fakeArgs?: string } = {}): Promise<Launched> {
  return launch({
    userData,
    fakeArgs: options.fakeArgs,
    env: {
      CAD_DESKTOP_PYTHON: "/nowhere/python",
      CADGEN_DAEMON: "0",
      ...(options.prewarm ? { TEXT_TO_CAD_PREWARM: "1" } : {}),
    },
  });
}

test("the first launch: a project, two sessions, the chips a person picked, a title and a theme", async () => {
  const { app, page } = await start();
  try {
    await page.emulateMedia({ colorScheme: "dark" });
    // Every provider answers with the same fake models; pin the one under test so this
    // machine's installed agents cannot change whose preferences are restored.
    await page.evaluate(() => window.textToCad.settings.set({ defaultAgentId: "claude-code" }));
    const added = await page.evaluate((dir) => window.textToCad.projects.addPath({ path: dir }), project);
    await expect(page.getByRole("heading", { name: `What should we build in ${path.basename(project)}?` })).toBeVisible();
    const row = page.locator("[data-new-session] [data-composer-row]");
    // The chips appear once the agent has been probed, which on a first run spawns it.
    await expect(row.locator("[data-chip=model]")).toContainText("Fast", { timeout: 30_000 });
    await expect(row.locator("[data-chip=effort]")).toContainText("Medium");

    // The mode, per provider: picked once here and never touched again. Every model switch
    // below has to leave it alone, and so does the quit.
    await pick(page, row.locator("[data-chip=mode]"), "Plan");
    const composer = page.getByPlaceholder("Do anything");
    await composer.fill("hello");
    await composer.press("Enter");
    await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 30_000 });

    // A model's levels are only reported by a session on it, so the efforts are picked in the
    // live thread. The fake's two models do not share their levels — Fast stops at High,
    // Smart has Xhigh — and a model switch puts the agent's own level back to Medium, so Xhigh
    // coming back on reselecting Smart can only be the app remembering it.
    const live = page.locator("[data-composer]");
    await pick(page, live.locator("[data-chip=model]"), "Smart");
    await pick(page, live.locator("[data-chip=effort]"), "Xhigh");
    await pick(page, live.locator("[data-chip=model]"), "Fast");
    await expect(live.locator("[data-chip=effort]")).toContainText("Medium");
    await live.locator("[data-chip=effort]").click();
    await expect(page.getByRole("menu").getByRole("menuitemradio", { name: "Xhigh", exact: true })).toHaveCount(0);
    await page.getByRole("menu").getByRole("menuitemradio", { name: "Low", exact: true }).click();
    await expect(live.locator("[data-chip=effort]")).toContainText("Low");
    await expect(live.locator("[data-chip=mode]")).toContainText("Plan");
    // The new-session screen draws what was learned: the model the thread was left on, the
    // level remembered for it, and the mode nobody changed; switching the model chip swaps the
    // effort chip with it. (The second launch checks the same after a restart.)
    await page.getByRole("button", { name: "New", exact: true }).click();
    const strip = page.locator("[data-new-session] [data-composer-row]");
    await expect(strip.locator("[data-chip=model]")).toContainText("Fast");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Low");
    await expect(strip.locator("[data-chip=mode]")).toContainText("Plan");
    await pick(page, strip.locator("[data-chip=model]"), "Smart");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Xhigh");

    // A second session, titled by its agent: the sidebar and the header follow.
    titled = (await page.evaluate((projectId) => window.textToCad.sessions.create({ projectId, agentId: "claude-code", gitMode: "none" }), added.id)).id;
    await page.locator(`[data-session-row="${titled}"]`).getByRole("button").first().click();
    await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
    await agentTitle(page, titled, "Design the gripper");
    await expect(page.locator(`[data-session-row="${titled}"]`)).toContainText("Design the gripper");
    await expect(page.locator("[data-session-title]")).toHaveText("Design the gripper");

    const sessions = await page.evaluate(() => window.textToCad.sessions.list({}));
    expect(sessions).toHaveLength(2);
    expect(sessions.every((session) => session.acpSessionId !== null)).toBe(true);
    launchedIds = sessions.map((session) => session.id).sort();
    // Light, under an OS in dark: the sharpest version of the restart below.
    await page.evaluate(() => window.textToCad.settings.set({ theme: "light" }));
  } finally {
    await app.close();
  }
});

test("the second launch comes back to all of it, and opening its sessions is cheap", async () => {
  test.setTimeout(120_000);
  const { app, page, lines } = await start({ prewarm: true, fakeArgs: LOAD_DELAY });
  try {
    // The window's own first frame is main's, painted from the same settings row: a restart
    // that applied the theme from an effect would show the OS's dark ground first.
    expect(await windowBackground(app), "the empty frame is the light ground").toBe("#ffffff");
    await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);

    // The project, its rows, and chips drawn from the cache — no probe, no spawn — on all three
    // choices, with both models' levels.
    await expect(page.getByText(path.basename(project)).first()).toBeVisible();
    await expect(page.locator("[data-session-row]")).toHaveCount(2);
    expect((await page.evaluate(() => window.textToCad.sessions.list({}))).map((session) => session.id).sort()).toEqual(launchedIds);
    const strip = page.locator("[data-new-session] [data-composer-row]");
    await expect(strip.locator("[data-chip=model]")).toContainText("Smart");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Xhigh");
    await expect(strip.locator("[data-chip=mode]")).toContainText("Plan");
    await pick(page, strip.locator("[data-chip=model]"), "Fast");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Low");
    await pick(page, strip.locator("[data-chip=model]"), "Smart");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Xhigh");

    // The warm pool: the index says which agents are worth an idle adapter, and main says on
    // stdout when one is up. A session opened now adopts it — no spawn and no `initialize` on
    // the critical path, which is what `warm=yes` means — and the pool puts up another.
    const sessions = await page.evaluate(() => window.textToCad.sessions.list({}));
    const first = sessions.find((session) => session.id !== titled)!;
    const warmed = `[acp] ${first.agentId} warmed in `;
    const warmedCount = () => lines.filter((line) => line.includes(warmed)).length;
    await expect.poll(warmedCount, { timeout: 60_000 }).toBeGreaterThanOrEqual(1);

    // The new-session screen's session is the one its chips described: the fake answers
    // `settings` with what it ended up on — the agent's word, not the app's. (Before any
    // session/load: the fake's load answers with no config options, and a load that does so
    // replaces the cached snapshot the chips are drawn from.)
    const composer = page.getByPlaceholder("Do anything");
    await composer.fill("settings");
    await composer.press("Enter");
    await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 30_000 });
    await expect(page.locator("[data-turn][data-role=agent]").last()).toContainText("settings: model=smart effort=xhigh");
    await expect(page.locator("[data-composer] [data-chip=mode]")).toContainText("Plan");
    expect(lines.find((line) => /\[acp\] create /.test(line))).toContain("warm=yes");

    // The first session opened adopts the next warm adapter, and replays its transcript.
    await expect.poll(warmedCount, { timeout: 60_000 }).toBeGreaterThanOrEqual(2);
    const firstRow = page.locator(`[data-session-row="${first.id}"]`);
    const titledRow = page.locator(`[data-session-row="${titled}"]`);
    await firstRow.click();
    await expect(page.getByText("earlier reply")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
    expect(lines.find((line) => /\[acp\] load /.test(line))).toContain("warm=yes");

    // The agent's title survived, as the agent's; a person's rename then outranks the agent.
    await titledRow.click();
    await expect(page.locator("[data-session-title]")).toHaveText("Design the gripper");
    await expect(page.getByText("earlier reply")).toBeVisible({ timeout: 30_000 });
    expect(await page.evaluate((id) => window.textToCad.sessions.get({ id }), titled)).toMatchObject({ title: "Design the gripper", titleSource: "agent" });
    await page.locator("[data-session-title]").click();
    const editor = page.locator("[data-session-header]").getByRole("textbox", { name: "Session title" });
    await editor.fill("My gripper task");
    await editor.press("Enter");
    await expect.poll(() => page.evaluate((id) => window.textToCad.sessions.get({ id }), titled)).toMatchObject({ title: "My gripper task", titleSource: "user" });
    await agentTitle(page, titled, "Agent replacement title");
    await expect(page.locator("[data-session-title]")).toHaveText("My gripper task");
    await expect(titledRow).toContainText("My gripper task");

    // Both adapters are up now (a session no longer on screen keeps its adapter), so switching
    // between them is a paint: never the loading screen, never a reconnect.
    for (let round = 0; round < 3; round += 1) {
      for (const row of [firstRow, titledRow]) {
        await row.click();
        await expect(page.locator("[data-session-view]")).toBeVisible();
        await expect(page.locator("[data-connecting]")).toHaveCount(0);
        await expect(page.locator("[data-reconnecting]")).toHaveCount(0);
      }
    }

    // Take one adapter away, the way the header's menu does: main kills it and the renderer
    // forgets the state, leaving the snapshot as the only thing anybody has. Going back paints
    // the transcript from it while the reconnect is still a line in the composer's row — before
    // the held `session/load` can have answered — with no loading screen, and a prompt could
    // already be queued.
    await firstRow.click();
    await page.getByRole("button", { name: "Session actions" }).click();
    await page.getByRole("menuitem", { name: "Disconnect agent" }).click();
    await titledRow.click();
    await expect(page.locator("[data-session-title]")).toHaveText("My gripper task");
    await firstRow.click();
    await expect(page.locator("[data-reconnecting]")).toBeVisible();
    await expect(page.locator("[data-turn][data-role=user]").first()).toBeVisible();
    await expect(page.locator("[data-reconnecting]")).toBeVisible();
    await expect(page.locator("[data-connecting]")).toHaveCount(0);
    await expect(page.getByPlaceholder("Do anything")).toBeEnabled();
    // ...and the live state replaces the picture, replayed once: the replay's events are
    // dropped while the snapshot is on screen, or every turn would arrive twice.
    await expect(page.locator("[data-reconnecting]")).toHaveCount(0, { timeout: 30_000 });
    await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
    await expect(page.getByText("earlier prompt")).toHaveCount(1);

  } finally {
    await app.close();
  }
});

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Open a chip's dropdown and choose a value, the menu gone on both sides: each pick re-renders
 * the row. The new-session menu groups the providers, so a label that appears more than once
 * is taken from Claude Code's group rather than whichever comes first.
 */
async function pick(page: Page, chip: Locator, name: string): Promise<void> {
  const menu = page.getByRole("menu");
  await expect(menu).toHaveCount(0);
  await chip.click();
  await expect(menu).toHaveCount(1);
  const choices = menu.getByRole("menuitemradio", { name, exact: true });
  if ((await choices.count()) > 1) {
    await menu.locator('[data-slot="dropdown-menu-radio-group"] > div')
      .filter({ has: page.getByText("Claude Code", { exact: true }) })
      .getByRole("menuitemradio", { name, exact: true }).click();
  } else {
    await choices.click();
  }
  await expect(menu).toHaveCount(0);
  await expect(chip).toContainText(name);
}

async function agentTitle(page: Page, id: string, title: string): Promise<void> {
  await page.evaluate(({ id, title }) => window.textToCad.sessions.prompt({
    id, content: [{ type: "text", text: `session-title ${JSON.stringify({ title })}` }],
  }), { id, title });
}

/** The window's own ground, as Electron reports it: `#rrggbb`, lower case. */
async function windowBackground(app: ElectronApplication): Promise<string> {
  return String(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.getBackgroundColor()) || "").toLowerCase();
}
