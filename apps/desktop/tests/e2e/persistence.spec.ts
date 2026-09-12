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

async function launch(dir = userData): Promise<{ app: ElectronApplication; page: Page }> {
  const app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${dir}`],
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
  const row = first.page.locator("[data-new-session] [data-composer-row]");
  // The model and effort chips appear once the agent has been probed for
  // what it offers (`agentOptions.probe`), which on a first run means the
  // adapter is spawned, asked, and closed.
  await expect(row.locator("[data-chip=model]")).toContainText("Fast", { timeout: 30_000 });
  await expect(row.locator("[data-chip=effort]")).toContainText("Medium");

  // Pick the other model and a different effort. Both are stored against the
  // agent — the model per provider, the effort against the model it was
  // picked under — and the second launch has to come back to them.
  await row.locator("[data-chip=model]").click();
  await first.page.getByRole("menuitemradio", { name: "Smart" }).first().click();
  await expect(row.locator("[data-chip=model]")).toContainText("Smart");
  await row.locator("[data-chip=effort]").click();
  // `exact`, because `Xhigh` is one of Smart's levels and contains this one.
  await first.page.getByRole("menuitemradio", { name: "High", exact: true }).first().click();
  await expect(row.locator("[data-chip=effort]")).toContainText("High");

  const composer = first.page.getByPlaceholder("Do anything");
  await composer.fill("keep this one around");
  await composer.press("Enter");
  const view = first.page.locator("[data-session-view]");
  await expect(view).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });
  await expect(first.page.locator("[data-session-row]")).toContainText("keep this one around");
  // The session was created with the model that was picked, and in the
  // agent's own auto mode rather than the `default` it starts in.
  const liveComposer = first.page.locator("[data-composer]");
  await expect(liveComposer.locator("[data-chip=model]")).toContainText("Smart");
  await expect(liveComposer.locator("[data-chip=effort]")).toContainText("High");
  await expect(liveComposer.locator("[data-chip=mode]")).toContainText("Auto");
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
    // The chips are drawn from the cache this time — no probe, no spawn —
    // and they are on the choice the first launch made.
    const secondStrip = second.page.locator("[data-new-session] [data-composer-row]");
    await expect(secondStrip.locator("[data-chip=model]")).toContainText("Smart");
    await expect(secondStrip.locator("[data-chip=effort]")).toContainText("High");
    // The modes survived with the options (migration 8), so the one
    // permission control is drawn from the cache too — on the agent's own
    // auto preset, because creating a session in it is not somebody
    // choosing it, and nobody chose anything else.
    await expect(secondStrip.locator("[data-chip=mode]")).toContainText("Auto");
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

/**
 * The grain of the memory, which is the thing the person asked for in so many
 * words: reselect a model and the effort and the mode you had are still
 * there. The effort is per model, the mode is per provider.
 *
 * The fake agent's two models do not share their levels — `Fast` stops at
 * High, `Smart` has `Xhigh` — and a model switch puts the agent's own level
 * back to Medium, so `Xhigh` coming back on reselecting `Smart` can only be
 * the app remembering it. One `default_effort` per agent could not: the pick
 * made under `Fast` overwrote it.
 *
 * A model's levels are only ever reported by a session that is on it, so the
 * first half of this runs in a live thread — that is where both models get
 * seen — and the second half is the new-session screen drawing what was
 * learned, across a quit.
 */
/**
 * Open a chip's dropdown and choose a value, waiting for the menu to be gone
 * on both sides. A chip is picked from repeatedly here and each pick
 * re-renders the row it is in, so "the menu is closed" is the state to hold
 * between them rather than something to assume.
 */
async function pick(page: Page, chip: ReturnType<Page["locator"]>, name: string): Promise<void> {
  const menu = page.getByRole("menu");
  await expect(menu).toHaveCount(0);
  await chip.click();
  await expect(menu).toHaveCount(1);
  await menu.getByRole("menuitemradio", { name, exact: true }).first().click();
  await expect(menu).toHaveCount(0);
}

test("the effort is remembered per model, and the mode per provider", async () => {
  test.setTimeout(180_000);
  const data = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-effort-"));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-effort-project-"));
  fs.writeFileSync(path.join(dir, "README.md"), "# Efforts\n");

  const first = await launch(data);
  try {
    await first.page.evaluate((target) => window.hardcore.projects.addPath({ path: target }), dir);
    const row = first.page.locator("[data-new-session] [data-composer-row]");
    await expect(row.locator("[data-chip=model]")).toContainText("Fast", { timeout: 30_000 });

    // The mode, per provider: picked once here, and never touched again.
    // Every model switch below has to leave it alone, and so does the quit.
    await pick(first.page, row.locator("[data-chip=mode]"), "Plan");
    await expect(row.locator("[data-chip=mode]")).toContainText("Plan");

    const composer = first.page.getByPlaceholder("Do anything");
    await composer.fill("hello");
    await composer.press("Enter");
    await expect(first.page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", {
      timeout: 30_000,
    });

    // In the live thread, where the agent reports each model's own levels.
    const live = first.page.locator("[data-composer]");
    await pick(first.page, live.locator("[data-chip=model]"), "Smart");
    await expect(live.locator("[data-chip=model]")).toContainText("Smart");
    await pick(first.page, live.locator("[data-chip=effort]"), "Xhigh");
    await expect(live.locator("[data-chip=effort]")).toContainText("Xhigh");

    // Back to Fast: a different level, and `Xhigh` is not among its own.
    await pick(first.page, live.locator("[data-chip=model]"), "Fast");
    await expect(live.locator("[data-chip=model]")).toContainText("Fast");
    await expect(live.locator("[data-chip=effort]")).toContainText("Medium");
    await live.locator("[data-chip=effort]").click();
    const levels = first.page.getByRole("menu");
    await expect(levels.getByRole("menuitemradio", { name: "Xhigh", exact: true })).toHaveCount(0);
    await levels.getByRole("menuitemradio", { name: "Low", exact: true }).click();
    await expect(levels).toHaveCount(0);
    await expect(live.locator("[data-chip=effort]")).toContainText("Low");
    await expect(live.locator("[data-chip=mode]")).toContainText("Plan");

    // The new-session screen now draws both: the provider's model, the level
    // remembered for it, and the mode nobody has changed.
    await first.page.getByRole("button", { name: "New", exact: true }).click();
    const strip = first.page.locator("[data-new-session] [data-composer-row]");
    await expect(strip.locator("[data-chip=model]")).toContainText("Fast");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Low");
    await expect(strip.locator("[data-chip=mode]")).toContainText("Plan");

    // Switching the model chip swaps the effort chip with it — the level and
    // the list, both that model's — and switching back returns the first.
    await pick(first.page, strip.locator("[data-chip=model]"), "Smart");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Xhigh");
    await expect(strip.locator("[data-chip=mode]")).toContainText("Plan");
    await pick(first.page, strip.locator("[data-chip=model]"), "Fast");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Low");
    await pick(first.page, strip.locator("[data-chip=model]"), "Smart");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Xhigh");
    // The list is Smart's too: the level only it has is on offer.
    await strip.locator("[data-chip=effort]").click();
    await expect(first.page.getByRole("menu").getByRole("menuitemradio", { name: "Xhigh", exact: true })).toHaveCount(1);
    await first.page.keyboard.press("Escape");
  } finally {
    await first.app.close();
  }

  const second = await launch(data);
  try {
    const strip = second.page.locator("[data-new-session] [data-composer-row]");
    // Drawn from the cache — no probe, no spawn — and on all three choices.
    await expect(strip.locator("[data-chip=model]")).toContainText("Smart", { timeout: 30_000 });
    await expect(strip.locator("[data-chip=effort]")).toContainText("Xhigh");
    await expect(strip.locator("[data-chip=mode]")).toContainText("Plan");

    // Both models' levels survived the quit, not just the current one's.
    await pick(second.page, strip.locator("[data-chip=model]"), "Fast");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Low");
    await pick(second.page, strip.locator("[data-chip=model]"), "Smart");
    await expect(strip.locator("[data-chip=effort]")).toContainText("Xhigh");

    // And the session the screen creates is the session the chips described.
    // The fake answers `settings` with what it itself ended up on, so this is
    // the agent's word for what the client sent it, not the app's.
    const composer = second.page.getByPlaceholder("Do anything");
    await composer.fill("settings");
    await composer.press("Enter");
    await expect(second.page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", {
      timeout: 30_000,
    });
    await expect(second.page.locator("[data-turn][data-role=agent]").last()).toContainText(
      "settings: model=smart effort=xhigh",
    );
    await expect(second.page.locator("[data-composer] [data-chip=mode]")).toContainText("Plan");
  } finally {
    await second.app.close();
    for (const target of [data, dir]) {
      fs.rmSync(target, { recursive: true, force: true });
    }
  }
});
