import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

/**
 * The session UI against the fake agent (plan §12): new session → prompt →
 * streaming rows → permission answered → completed, then the other states
 * — cancelled, errored, resumed, signed out — each screenshotted into
 * `__screenshots__/session-*.png`. Look at them.
 *
 * `HARDCORE_FAKE_AGENT` makes main launch `tests/fake-agent` in place of
 * every adapter; the `showcase` prompt is the fake's Codex-shaped turn.
 */
declare const window: {
  innerWidth: number;
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    settings: { set(patch: { theme: string }): Promise<unknown> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;
let signedOutProject: string;

test.beforeAll(async () => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-session-"));
  project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-scratch-"));
  fs.writeFileSync(path.join(project, "README.md"), "# Scratch\n\nA place to try things.\n");
  signedOutProject = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-signed-out-"));
  fs.writeFileSync(path.join(signedOutProject, ".fake-auth-required"), "");

  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: fakeAgent },
  });
  page = await app.firstWindow();
  // A renderer exception would otherwise show up as an empty page and a
  // timeout three assertions later.
  page.on("pageerror", (error) => {
    console.error(`[renderer] ${error.message}\n${error.stack ?? ""}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      console.error(`[renderer:${message.type()}] ${message.text()}`);
    }
  });
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate((value) => window.hardcore.settings.set({ theme: value }), "dark");
  await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), project);
});

test.afterAll(async () => {
  await app?.close();
  for (const dir of [userData, project, signedOutProject]) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("a new session runs a Codex-shaped turn through every state", async () => {
  const projectName = path.basename(project);
  await expect(page.getByRole("heading", { name: `What should we build in ${projectName}?` })).toBeVisible();
  // The agent chip fills in once the detector has probed; sending before
  // that would have nothing to launch. The new-session context — project,
  // git mode, agent — is a strip above the composer (Codex); the composer's
  // own row holds approval.
  const strip = page.locator("[data-context-strip]");
  await expect(strip.locator("[data-chip=project]")).toContainText(projectName);
  // Two choices behind the git chip, and a scratch directory that is not a
  // repository still runs: Local (plan §9).
  await expect(strip.locator("[data-chip=git-mode]")).toContainText("Local");
  // The model and the effort, before there is a session — the chips the
  // agent dropdown was replaced by. They appear once the agent has been
  // probed for what it offers, which on a first run spawns the adapter.
  await expect(strip.locator("[data-chip=model]")).toContainText("Fast", { timeout: 30_000 });
  await expect(strip.locator("[data-chip=effort]")).toContainText("Medium");
  await expect(strip.locator("[data-chip=agent]")).toHaveCount(0);
  await expect(page.locator("[data-composer] [data-chip=approval]")).toContainText("Ask");
  // The heading, the line under it, the strip and an empty box — nothing else.
  await expect(page.locator("[data-new-session] button", { hasText: "Explore this project" })).toHaveCount(0);
  await shoot("session-new.png");

  // The model menu is grouped by provider — one group per agent that
  // answered, `HARDCORE_FAKE_AGENT` making every installed one answer the
  // same two models — and lists names alone, with no paragraph under each.
  await strip.locator("[data-chip=model]").click();
  const menu = page.getByRole("menu");
  await expect(menu.getByRole("menuitemradio", { name: "Fast", exact: true }).first()).toBeVisible();
  await expect(menu.getByRole("menuitemradio", { name: "Smart", exact: true }).first()).toBeVisible();
  await expect(menu.getByText("Claude Code", { exact: true })).toBeVisible();
  // Names only: an item is one line, so it is no taller than one row of text.
  const item = menu.getByRole("menuitemradio").first();
  expect((await item.boundingBox())!.height).toBeLessThan(36);
  await shoot("session-new-model-menu.png");
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await setTheme("light");
  await shoot("session-new-light.png");
  await setTheme("dark");

  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("showcase: write a greeting script and tidy up");
  await composer.press("Enter");

  // The session exists, the sidebar lists it under the project with a
  // spinner, and the title is the prompt.
  const view = page.locator("[data-session-view]");
  await expect(view).toBeVisible();
  const row = page.locator("[data-session-row]");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("showcase: write a greeting script and tidy up");
  await expect(page.locator("[data-session-title]")).toContainText("showcase: write a greeting script");

  // Streaming: the thought, the first activity rows, the status line, and
  // stop in place of send.
  await expect(page.locator("[data-activity-row], [data-activity-group]").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  await expect(page.locator("[data-status-line]")).toBeVisible();
  await shoot("session-streaming.png");

  // Waiting: the permission card with one action per option.
  const permission = page.locator("[data-permission][data-outcome=pending]");
  await expect(permission).toBeVisible();
  await expect(permission).toContainText("Delete the build directory?");
  await expect(permission.getByRole("button", { name: "Yes", exact: true })).toBeVisible();
  await expect(permission.getByRole("button", { name: "Yes, always" })).toBeVisible();
  await expect(permission.getByRole("button", { name: "No", exact: true })).toBeVisible();
  await expect(page.locator("[data-status-line]")).toContainText("Waiting for your approval");
  await expect(row).toHaveAttribute("data-status", "waiting");
  await shoot("session-permission.png");
  await permission.getByRole("button", { name: "Yes", exact: true }).click();
  await expect(page.locator("[data-permission][data-outcome=selected]")).toContainText("Allowed");

  // Completed: prose, the folded rows, the subagent, the plan card, the
  // files-changed pill, the usage chip; send is back.
  await expect(view).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });
  await expect(page.getByText("the stale build directory is gone")).toBeVisible();
  await expect(page.locator("[data-subagent]")).toContainText("Docs checker finished");
  await expect(page.locator("[data-plan-card]")).toContainText("3 of 3 done");
  await expect(page.locator("[data-files-changed]")).toContainText("2 files changed");
  await expect(page.locator("[data-files-changed]")).toContainText("+8 −0");
  await expect(page.locator("[data-part=usage]")).toContainText("tokens");
  await expect(page.getByRole("button", { name: "Submit" })).toBeVisible();
  await expect(row).toHaveAttribute("data-status", "idle");
  await shoot("session-completed.png");

  // The composer is one row at the default session width (Codex's): `+` and
  // approval on the left, the model, the effort and the options glyph on the
  // right, nothing wrapped. The fake agent exposes a model and an effort, so
  // the right-hand chips are there to measure.
  const composerRow = page.locator("[data-composer]");
  await expect(composerRow.locator("[data-chip=model]")).toContainText("Fast");
  await expect(composerRow.locator("[data-chip=effort]")).toContainText("Medium");
  // No options chip and no microphone: the first was somebody else's plugin
  // agents behind a settings glyph, the second a button that never worked.
  await expect(composerRow.locator("[data-chip=options]")).toHaveCount(0);
  await expect(composerRow.getByRole("button", { name: /voice/i })).toHaveCount(0);
  // And the session started in the agent's own auto mode, not its default.
  await expect(composerRow.locator("[data-chip=mode]")).toContainText("Auto");
  // How full the context is sits ABOVE the box, so typing cannot move it.
  const contextLine = page.locator("[data-context-line]");
  await expect(contextLine).toContainText("% context");
  await expect(contextLine).not.toContainText("$");
  const lineBox = (await contextLine.boundingBox())!;
  const boxTop = (await composerRow.boundingBox())!.y;
  expect(lineBox.y + lineBox.height).toBeLessThanOrEqual(boxTop + 1);
  await expectOneRowComposer();
  // And still one row at the three window sizes the layout is designed for.
  for (const [width, height] of [[1280, 800], [1680, 1050]] as const) {
    await resizeWindow(width, height);
    await expectOneRowComposer();
    await expectPaneWidths();
    await shoot(`session-${width}x${height}.png`);
  }
  await resizeWindow(1440, 900);
  await expectPaneWidths();

  // Model and effort are two dropdowns, not two groups in one menu: each
  // sets its own config option and the other stays where it was.
  await composerRow.locator("[data-chip=effort]").click();
  await page.getByRole("menuitemradio", { name: "High" }).click();
  await expect(composerRow.locator("[data-chip=effort]")).toContainText("High");
  await expect(composerRow.locator("[data-chip=model]")).toContainText("Fast");

  // Folding: the consecutive reads, edits and commands are one line.
  const group = page.locator("[data-activity-group]").first();
  await expect(group).toContainText("Read 2 files, edited 2 files, ran 2 commands");
  await group.getByRole("button").first().click();
  const editRow = page.locator("[data-activity-row=sc-edit-1]");
  await expect(editRow).toContainText("Edited hello.py");
  await expect(editRow).toContainText("+6 −0");
  await editRow.getByRole("button").first().click();
  await expect(page.locator("[data-testid=diff-view]")).toBeVisible({ timeout: 20_000 });
  const execRow = page.locator("[data-activity-row=sc-exec-1]");
  await expect(execRow).toContainText("python hello.py");
  await execRow.getByRole("button").first().click();
  await expect(page.locator("[data-tool-detail]").filter({ hasText: "hello from the fake agent" }).last()).toBeVisible();
  await shoot("session-expanded.png");
  await setTheme("light");
  await shoot("session-expanded-light.png");
  await setTheme("dark");
});

test("the + is a menu of the three ways something gets into a prompt", async () => {
  const plus = page.locator("[data-composer]").getByRole("button", { name: "Add to this prompt" });
  await plus.click();
  const menu = page.getByRole("menu");
  await expect(menu.getByRole("menuitem", { name: "Attach files…" })).toBeVisible();
  await expect(menu.getByRole("menuitem", { name: "Attach image…" })).toBeVisible();
  // No CAD file is open in this suite, so the capture is disabled rather
  // than missing: the answer to "why can I not do that" should be visible.
  const capture = menu.getByRole("menuitem", { name: "Capture from viewer" });
  await expect(capture).toBeVisible();
  await expect(capture).toHaveAttribute("data-disabled", "");
  await shoot("session-attach-menu.png");
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
});

/**
 * The same turn again in light, for the states that only exist mid-turn:
 * streaming and the permission card. A theme switch after the fact cannot
 * show them, so the fake runs its showcase once more.
 */
test("the streaming and permission states render in light", async () => {
  await page.getByRole("button", { name: "New chat" }).click();
  await expect(page.getByRole("heading", { name: /What should we build in/ })).toBeVisible();
  await setTheme("light");
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("showcase: the same script, in light");
  await composer.press("Enter");

  await expect(page.locator("[data-activity-row], [data-activity-group]").first()).toBeVisible();
  await expect(page.locator("[data-status-line]")).toBeVisible();
  await shoot("session-streaming-light.png");

  const permission = page.locator("[data-permission][data-outcome=pending]");
  await expect(permission).toBeVisible();
  await shoot("session-permission-light.png");
  await permission.getByRole("button", { name: "Yes", exact: true }).click();
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });
  await shoot("session-completed-light.png");
  await setTheme("dark");
  // Back to the first session, which the rest of the file drives — and this
  // one deleted, so the sidebar holds exactly the row those tests expect.
  const light = page.locator("[data-session-row]").filter({ hasText: "in light" });
  await light.getByRole("button", { name: /actions$/ }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await expect(page.locator("[data-session-row]")).toHaveCount(1);
  await page.locator("[data-session-row]").click();
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
});

test("stop cancels the running turn", async () => {
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("slow");
  await composer.press("Enter");
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  await expect(page.locator("[data-turn][data-role=agent]").last()).toContainText("working");
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.locator("[data-stopped]")).toBeVisible();
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
  await shoot("session-cancelled.png");
});

test("a queued prompt goes out when the turn ends", async () => {
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("slow");
  await composer.press("Enter");
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  await page.getByPlaceholder("Send another message — it goes next").fill("thought and then ok");
  await page.keyboard.press("Enter");
  await expect(page.getByText("1 queued prompt")).toBeVisible();
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.getByText("1 queued prompt")).toBeHidden();
  await expect(page.locator("[data-turn][data-role=user]").last()).toContainText("thought and then ok");
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });
});

test("a crashed agent is an inline error with retry, and reconnecting resumes the history", async () => {
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("crash");
  await composer.press("Enter");
  await expect(page.locator("[data-part=error]")).toBeVisible();
  await expect(page.locator("[data-part=error]")).toContainText("exited");
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.locator("[data-session-row]")).toHaveAttribute("data-status", "error");
  await shoot("session-error.png");

  await page.getByRole("button", { name: "Reconnect" }).click();
  // The fake's `session/load` replays one earlier exchange.
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
  await expect(page.locator("[data-turn][data-role=user]").first()).toContainText("earlier prompt");
  await expect(page.getByText("earlier reply")).toBeVisible();
  await shoot("session-resumed.png");
});

test("the sidebar renames and archives a session", async () => {
  const row = page.locator("[data-session-row]");
  await row.getByRole("button", { name: /actions$/ }).click();
  await page.getByRole("menuitem", { name: "Rename" }).click();
  const input = page.getByLabel("Session title");
  await input.fill("Greeting script");
  await input.press("Enter");
  await expect(row).toContainText("Greeting script");
  await expect(page.locator("[data-session-title]")).toContainText("Greeting script");

  await row.click({ button: "right" });
  await page.getByRole("menuitem", { name: "Archive" }).click();
  await expect(row).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /What should we build in/ })).toBeVisible();
});

test("a signed-out agent asks to sign in", async () => {
  await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), signedOutProject);
  await page.locator("[data-chip=project]").click();
  await page.getByRole("menuitemradio", { name: path.basename(signedOutProject) }).click();
  await expect(page.getByRole("heading", { name: `What should we build in ${path.basename(signedOutProject)}?` })).toBeVisible();
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("hello");
  await composer.press("Enter");
  const auth = page.locator("[data-auth-prompt]");
  await expect(auth).toBeVisible();
  await expect(auth).toContainText("Sign in to");
  await expect(auth.getByRole("button", { name: /Sign in/ })).toBeVisible();
  await expect(page.locator("[data-session-row]")).toHaveCount(0);
  await shoot("session-auth.png");
});

async function shoot(name: string) {
  await page.screenshot({ path: path.join(screenshots, name), animations: "disabled" });
}

async function setTheme(theme: "dark" | "light") {
  await page.evaluate((value) => window.hardcore.settings.set({ theme: value }), theme);
  await expect(page.locator("html")).toHaveClass(theme === "dark" ? /\bdark\b/ : /^(?!.*\bdark\b).*$/);
}

async function resizeWindow(width: number, height: number) {
  await app.evaluate(
    ({ BrowserWindow }, size) => {
      const [win] = BrowserWindow.getAllWindows();
      win?.setSize(size.width, size.height);
    },
    { width, height },
  );
  await expect.poll(() => page.evaluate(() => window.innerWidth)).toBe(width);
  // The panels lay out on the next frame.
  await page.waitForTimeout(150);
}

/** The composer's footer is one line: every chip shares the send button's row. */
async function expectOneRowComposer() {
  const send = page.locator("[data-composer] button[aria-label=\"Submit\"], [data-composer] button[aria-label=\"Stop\"]").first();
  const sendBox = await send.boundingBox();
  expect(sendBox).not.toBeNull();
  for (const chip of await page.locator("[data-composer] [data-chip]").all()) {
    const box = await chip.boundingBox();
    expect(box, "a chip is off the send button's row").not.toBeNull();
    expect(Math.abs((box!.y + box!.height / 2) - (sendBox!.y + sendBox!.height / 2))).toBeLessThan(6);
  }
}

/**
 * The shell's contract with the explorer closed, which is how it starts: a
 * 230px sidebar and the session taking the rest of the window. The explorer
 * opens when something opens in it (`tests/e2e/explorer.spec.ts`).
 */
async function expectPaneWidths() {
  const widths = await page.locator("[data-panel]").evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().width));
  expect(widths).toHaveLength(3);
  expect(Math.abs(widths[0]! - 230), `sidebar ${widths[0]}`).toBeLessThanOrEqual(1);
  expect(widths[2]!, `explorer ${widths[2]}`).toBe(0);
  expect(widths[1]!, `session ${widths[1]}`).toBeGreaterThanOrEqual(559);
  expect(Math.abs(widths[0]! + widths[1]! - await page.evaluate(() => window.innerWidth))).toBeLessThanOrEqual(3);
}
