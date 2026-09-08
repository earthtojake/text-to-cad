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
/**
 * The renderer globals this file's `page.evaluate` calls reach for, declared
 * the way the other suites declare theirs: the e2e tsconfig has no `dom`
 * lib, on purpose — a spec that could see the whole DOM API would be a spec
 * that forgot which side of the bridge it is on.
 */
declare const document: { querySelectorAll(selectors: string): Iterable<object>; };
declare function getComputedStyle(element: object): {
  userSelect: string;
  lineHeight: string;
  paddingTop: string;
  paddingBottom: string;
};

declare const window: {
  innerWidth: number;
  /** What a drag actually selected. */
  getSelection(): { toString(): string; removeAllRanges(): void } | null;
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
  // git mode — is a strip ABOVE the box; `+`, the mode, the model and the
  // effort are in the row UNDER it, the same row a live session has.
  const strip = page.locator("[data-context-strip]");
  const actionRow = page.locator("[data-new-session] [data-composer-row]");
  await expect(strip.locator("[data-chip=project]")).toContainText(projectName);
  // Two choices behind the git chip, and a scratch directory that is not a
  // repository still runs: Local (plan §9).
  await expect(strip.locator("[data-chip=git-mode]")).toContainText("Local");
  // The model and the effort, before there is a session — the chips the
  // agent dropdown was replaced by. They appear once the agent has been
  // probed for what it offers, which on a first run spawns the adapter.
  await expect(actionRow.locator("[data-chip=model]")).toContainText("Fast", { timeout: 30_000 });
  await expect(actionRow.locator("[data-chip=effort]")).toContainText("Medium");
  await expect(strip.locator("[data-chip=agent]")).toHaveCount(0);
  // The mode: the app's one permission control, here as in a live thread,
  // preselected at the agent's own auto preset. Nothing is left of the
  // second, app-side approval level it replaced.
  await expect(actionRow.locator("[data-chip=mode]")).toContainText("Auto");
  await expect(page.locator("[data-chip=approval]")).toHaveCount(0);
  await expect(page.getByText("Approve for me")).toHaveCount(0);
  await expect(page.getByText("Ask", { exact: true })).toHaveCount(0);
  await expect(page.locator("[data-composer] form [data-chip]")).toHaveCount(0);
  {
    // Strip above the box, row below it: the same shape as a live session's.
    const stripBox = (await strip.boundingBox())!;
    const box = (await page.locator("[data-composer] form").boundingBox())!;
    const rowBox = (await page.locator("[data-composer-row]").boundingBox())!;
    expect(stripBox.y + stripBox.height).toBeLessThanOrEqual(box.y + 1);
    expect(rowBox.y).toBeGreaterThanOrEqual(box.y + box.height - 1);
  }
  await expectNoChevrons();
  // No ring before there is a turn to have used anything.
  await expect(page.locator("[data-context-trigger]")).toHaveCount(0);
  // The heading, the line under it, the strip and an empty box — nothing else.
  await expect(page.locator("[data-new-session] button", { hasText: "Explore this project" })).toHaveCount(0);
  await shoot("session-new.png");

  // The model menu is grouped by provider — one group per agent that
  // answered, `HARDCORE_FAKE_AGENT` making every installed one answer the
  // same two models — and lists names alone, with no paragraph under each.
  await actionRow.locator("[data-chip=model]").click();
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

  // Completed: prose, the folded rows, the subagent, the plan card; send is
  // back. No pill above the box and no chip at the end of the turn: the
  // files-changed pill and the per-turn token count are both gone — the
  // first said what the review tab says, the second put a number nobody
  // reads mid-thread into the transcript once per turn.
  await expect(view).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });
  await expect(page.getByText("the stale build directory is gone")).toBeVisible();
  await expect(page.locator("[data-subagent]")).toContainText("Docs checker finished");
  await expect(page.locator("[data-plan-card]")).toContainText("3 of 3 done");
  await expect(page.locator("[data-files-changed]")).toHaveCount(0);
  await expect(page.locator("[data-part=usage]")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Submit" })).toBeVisible();
  await expect(row).toHaveAttribute("data-status", "idle");
  await shoot("session-completed.png");

  // The composer's row is one line UNDER the box: `+` and the mode on the
  // left, the model, the effort and the context ring on the right, nothing
  // wrapped. The fake agent exposes a model and an effort, so the
  // right-hand chips are there to measure.
  const composerArea = page.locator("[data-composer]");
  const chipRow = page.locator("[data-composer-row]");
  await expect(chipRow.locator("[data-chip=model]")).toContainText("Fast");
  await expect(chipRow.locator("[data-chip=effort]")).toContainText("Medium");
  // No options chip and no microphone: the first was somebody else's plugin
  // agents behind a settings glyph, the second a button that never worked.
  await expect(composerArea.locator("[data-chip=options]")).toHaveCount(0);
  await expect(composerArea.getByRole("button", { name: /voice/i })).toHaveCount(0);
  // And the session started in the agent's own auto mode, not its default.
  await expect(chipRow.locator("[data-chip=mode]")).toContainText("Auto");
  // The box holds the sentence and send; everything else is below it.
  const inputBox = (await composerArea.locator("form").boundingBox())!;
  const chipRowBox = (await chipRow.boundingBox())!;
  expect(chipRowBox.y).toBeGreaterThanOrEqual(inputBox.y + inputBox.height - 1);
  await expect(composerArea.locator("form [data-chip]")).toHaveCount(0);
  // Every chip is an icon and a label. No chevron: six of them in two rows
  // say the same thing about six controls that are visibly the same control.
  await expectNoChevrons();

  // How full the window is, as a ring at the end of the row rather than a
  // line of text above the box.
  const ring = page.locator("[data-context-trigger]");
  await expect(ring).toHaveAttribute("aria-label", /^Context \d+% used$/);
  await expect(ring).toHaveAttribute("title", /^[\d.]+k? \/ [\d.]+k? \(\d+%\)$/);

  // Clicking it opens the breakdown, and it STAYS open — hover does nothing
  // and moving away does not take it back. The window as a bar with its
  // numbers, then the session's token accounting behind `See detailed
  // breakdown`, which is where the per-turn chip's information went. The
  // fake agent sends no categories, as neither real adapter does.
  await ring.click();
  const popover = page.locator("[data-context-popover]");
  await expect(popover).toBeVisible();
  await expect(popover.locator("[data-context-window]")).toContainText("/");
  await expect(popover.locator("[data-context-bar]")).toBeVisible();
  await expect(popover.locator("[data-context-tokens]")).toHaveCount(0);
  await page.mouse.move(20, 20);
  await expect(popover).toBeVisible();
  await popover.locator("[data-context-detail-toggle]").click();
  await expect(popover.locator("[data-context-token-row=input]")).toContainText("Fresh input");
  await expect(popover.locator("[data-context-token-row=cache-read]")).toContainText("Cache reads");
  await expect(popover.locator("[data-context-token-row=output]")).toContainText("Output");
  await expect(popover.locator("[data-context-categories]")).toHaveCount(0);
  // The fake agent reported no plan limits either, so nothing claims to
  // know about the account's.
  await expect(popover.locator("[data-rate-limits]")).toHaveCount(0);
  await expect(popover).not.toContainText("$");
  // Folded away again, which is where the next test expects to find it.
  await popover.locator("[data-context-detail-toggle]").click();
  await expect(popover.locator("[data-context-tokens]")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(popover).toBeHidden();
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
  await chipRow.locator("[data-chip=effort]").click();
  await page.getByRole("menuitemradio", { name: "High", exact: true }).click();
  await expect(chipRow.locator("[data-chip=effort]")).toContainText("High");
  await expect(chipRow.locator("[data-chip=model]")).toContainText("Fast");

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

/**
 * The transcript is a document: a drag across an agent's reply selects it.
 *
 * It did not, and the reason was one line in `styles/globals.css` — `body {
 * user-select: none }`, written for a window of chrome — so every word an
 * agent produced was a word nobody could copy. The drag is a real mouse
 * drag rather than `selectAllChildren`, because a programmatic range
 * succeeds against `user-select: none` and would have passed the whole time
 * this was broken.
 */
test("text in an agent's message can be selected with the mouse", async () => {
  const prose = page.locator("[data-part=text]").first();
  await expect(prose).toBeVisible();
  const box = (await prose.boundingBox())!;
  await page.mouse.move(box.x + 2, box.y + 8);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width - 4, box.y + box.height - 6, { steps: 16 });
  await page.mouse.up();
  const selected = await page.evaluate(() => window.getSelection()?.toString() ?? "");
  expect(selected.trim().length, "nothing was selected in the agent's prose").toBeGreaterThan(0);
  // It is the agent's words, not a stray label from somewhere else.
  expect(await prose.innerText()).toContain(selected.trim().split("\n")[0]!.trim());

  // Left cleared, so the screenshots after this are not a picture of a
  // highlight.
  await page.evaluate(() => window.getSelection()?.removeAllRanges());

  // The rest of the document, asserted rather than dragged over: a summary
  // line and the code in a fenced block are inside buttons and `<pre>`, and
  // a drag that starts and ends inside one button is also a *click* on it —
  // this test would fold the transcript's rows shut behind itself.
  expect(await selectability("[data-activity-row] button, [data-activity-group] button")).toBe("text");
  expect(await selectability("[data-part=text] pre, [data-part=text] code")).toBe("text");
});

/**
 * The categories, when an agent sends any. Neither shipping adapter does —
 * Claude's `usage_update` is used/size/cost, Codex's is used/size — so the
 * fake agent is the only place the `_meta.contextBreakdown` shape exists,
 * and this is the only place the coloured segments are drawn.
 */
test("the context panel breaks the window down when the agent sends categories", async () => {
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("context");
  await composer.press("Enter");
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });

  const ring = page.locator("[data-context-trigger]");
  await ring.click();
  const popover = page.locator("[data-context-popover]");
  await expect(popover).toBeVisible();
  // Folded, the way the last test left it. The bar at the top is segmented
  // by the categories; naming them is the breakdown.
  await expect(popover.locator("[data-context-detail]")).toHaveCount(0);
  await popover.locator("[data-context-detail-toggle]").click();
  const categories = popover.locator("[data-context-categories]");
  await expect(categories.locator("[data-context-category=system_prompt]")).toContainText("System prompt");
  await expect(categories.locator("[data-context-category=messages]")).toContainText("Messages");
  await expect(categories.locator("[data-context-category=mcp_tools]")).toContainText("MCP tools");
  // Two turns now: the session column adds them up, the last-turn column is
  // the small one just finished.
  await expect(popover.locator("[data-context-token-row=cache-write]")).toContainText("Cache writes");
  // Closing and opening it again finds it where it was left.
  await page.keyboard.press("Escape");
  await expect(popover).toBeHidden();
  await ring.click();
  await expect(popover.locator("[data-context-detail]")).toBeVisible();
  await settled();
  await shoot("session-context.png");
  await setTheme("light");
  await shoot("session-context-light.png");
  await setTheme("dark");
  await page.keyboard.press("Escape");
  await expect(popover).toBeHidden();
});

/**
 * The account's plan limits, which only the Claude adapter reports — it
 * forwards the SDK's `rate_limit_event` as a `usage_update` carrying
 * `_meta._claude/rateLimit`, one limit type per event. The fake agent sends
 * three on the word `limits`, in the SDK's own units, so this exercises the
 * reducer's normalisation as well as the rows.
 */
test("the context panel lists the account's plan limits", async () => {
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("limits");
  await composer.press("Enter");
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });

  await page.locator("[data-context-trigger]").click();
  const popover = page.locator("[data-context-popover]");
  await expect(popover).toBeVisible();
  const limits = popover.locator("[data-rate-limits]");
  await expect(limits).toContainText("Plan usage limits");
  // In the order they bite, each with the reset it named and its share.
  await expect(limits.locator("[data-rate-limit=five_hour]")).toContainText("5-hour limit");
  await expect(limits.locator("[data-rate-limit=five_hour]")).toContainText("Resets in 4 hr 5 min");
  await expect(limits.locator("[data-rate-limit=five_hour]")).toContainText("17%");
  await expect(limits.locator("[data-rate-limit=seven_day]")).toContainText("Weekly · all models");
  // Three days out is a weekday and a clock time, not sixty-odd hours.
  await expect(limits.locator("[data-rate-limit=seven_day]")).toContainText(/Resets \w{3} \d{1,2}:\d{2} (AM|PM)/);
  await expect(limits.locator("[data-rate-limit=seven_day_opus]")).toContainText("Weekly · Opus");
  await expect(limits.locator("[data-rate-limit=seven_day_opus]")).toContainText("96%");
  await expect(limits.locator("[data-rate-limit-overage]")).toContainText("Using overage");
  // Radix fades and scales the panel in. `animations: "disabled"` finishes
  // an animation rather than skipping it, so a screenshot taken the instant
  // the assertions pass catches it half-transparent and two-thirds size.
  await settled();
  await shoot("session-context-limits.png");
  await setTheme("light");
  await shoot("session-context-limits-light.png");
  await setTheme("dark");
  await page.keyboard.press("Escape");
  await expect(popover).toBeHidden();
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
 * The box is one row until there is more than one row to show, and it stops
 * growing at eight.
 *
 * Measured against its own line height rather than a pixel constant: the
 * question is "is this box one line of text tall", and a `min-h` a person
 * bumps to 3rem is exactly the mistake this catches. Send is on that row,
 * centred on it, because a button on a second row inside the box makes the
 * smallest composer twice as tall as the sentence in it.
 */
test("the composer starts at one row, grows, and caps at eight", async () => {
  const input = page.locator("[data-composer-input]");
  await expect(input).toBeVisible();
  const rows = () =>
    input.evaluate((node) => {
      const style = getComputedStyle(node);
      const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
      const line = parseFloat(style.lineHeight);
      return {
        line,
        text: node.clientHeight - padding,
        scrolls: node.scrollHeight > node.clientHeight + 1,
      };
    });

  const empty = await rows();
  expect(Math.abs(empty.text - empty.line), `empty box is ${empty.text}px of text`).toBeLessThanOrEqual(4);
  expect(empty.scrolls).toBe(false);

  // Send shares that row, centred on it.
  const submit = page.locator("[data-composer] form button[type=submit]");
  const [inputBox, submitBox] = await Promise.all([input.boundingBox(), submit.boundingBox()]);
  expect(Math.abs((submitBox!.y + submitBox!.height / 2) - (inputBox!.y + inputBox!.height / 2))).toBeLessThan(4);

  // Five lines: five rows of text, no scrolling.
  await input.click();
  await type(5);
  const five = await rows();
  expect(Math.round(five.text / five.line)).toBe(5);
  expect(five.scrolls).toBe(false);

  // Twenty: eight rows, and the rest is scrolled inside.
  await type(15);
  const twenty = await rows();
  expect(Math.round(twenty.text / twenty.line)).toBe(8);
  expect(twenty.scrolls).toBe(true);

  // Twenty Shift+Enters made twenty lines and sent nothing: the last turn is
  // still the one the test before this left there. (That Enter *does* send is
  // every other test in this file.)
  await expect(page.locator("[data-turn][data-role=user]").last()).not.toContainText("line 19");
  await expect(page.locator("[data-composer] form [data-chip]")).toHaveCount(0);

  // Emptied, it is one row again — the min is a floor, not a remembered
  // height.
  await page.keyboard.press(process.platform === "darwin" ? "Meta+a" : "Control+a");
  await page.keyboard.press("Backspace");
  await expect(input).toHaveText("");
  const after = await rows();
  expect(Math.abs(after.text - after.line)).toBeLessThanOrEqual(4);
  expect(after.scrolls).toBe(false);
});

/**
 * The same turn again in light, for the states that only exist mid-turn:
 * streaming and the permission card. A theme switch after the fact cannot
 * show them, so the fake runs its showcase once more.
 */
test("the streaming and permission states render in light", async () => {
  await page.getByRole("button", { name: "New", exact: true }).click();
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
  // The transcript selects, but its own controls do not: a drag that starts
  // on Retry is somebody missing the button (see the selection test).
  expect(await selectability("[data-part=error] button")).toBe("none");
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


/**
 * The mode is the app's one permission control, and it is on the
 * new-session screen too: what the session will be created in.
 *
 * There used to be two levels — the agent's mode *and* an "Ask / Approve for
 * me" chip of Hardcore's own over the top of it — which is two answers to
 * one question and no way to tell which one stopped a request. This is the
 * one that is left, and these are the two ends of it: Manual, where the
 * agent asks and the transcript waits, and full access, where nothing is
 * asked because nothing asks.
 */
test("the new session is created in the mode its chip is on, and Manual waits", async () => {
  const actionRow = page.locator("[data-new-session] [data-composer-row]");
  const chip = actionRow.locator("[data-chip=mode]");
  // Preselected at the agent's own auto preset, the way the model and the
  // effort chips are preselected at what it last ran with.
  await expect(chip).toContainText("Auto");
  await chip.click();
  const menu = page.getByRole("menu");
  // The agent's own names, and no paragraph under any of them...
  for (const name of ["Manual", "Plan", "Auto"]) {
    const row = menu.getByRole("menuitemradio", { name, exact: true });
    await expect(row).toBeVisible();
    expect((await row.boundingBox())!.height).toBeLessThan(36);
  }
  // ...except the one that removes every checkpoint, which says so.
  const full = menu.getByRole("menuitemradio", { name: /Full access/ });
  await expect(full).toContainText("Never asks");
  await expect(menu.locator("[data-mode-full-access]")).toHaveCount(1);
  await shoot("session-new-mode-menu.png");

  await menu.getByRole("menuitemradio", { name: "Manual", exact: true }).click();
  await expect(chip).toContainText("Manual");
  await expectNoChevrons();

  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("permission to run ls");
  await composer.press("Enter");

  // Manual: the agent asks, the request is in the transcript, and the thread
  // waits for the person — nothing in the app answers it.
  const permission = page.locator("[data-permission][data-outcome=pending]");
  await expect(permission).toBeVisible();
  await expect(page.locator("[data-status-line]")).toContainText("Waiting for your approval");
  await expect(page.locator("[data-composer-row] [data-chip=mode]")).toContainText("Manual");
  await permission.getByRole("button", { name: "Yes", exact: true }).click();
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });

  // And it was created in Manual: the fake reports what the client set on it
  // and which mode it ended in, so no `mode:` at all is the assertion —
  // `default` is where it starts and where the chip said to leave it.
  await composer.fill("applied");
  await composer.press("Enter");
  await expect(page.locator("[data-turn][data-role=agent]").last()).toContainText("in default");
  await expect(page.locator("[data-turn][data-role=agent]").last()).not.toContainText("mode:");
});

test("the full-access mode is never asked anything", async () => {
  await page.getByRole("button", { name: "New", exact: true }).click();
  const chip = page.locator("[data-new-session] [data-composer-row] [data-chip=mode]");
  // On one of the agent's own modes — the one it was last left in for this
  // agent, else its auto preset (which is which is asserted per agent in
  // `tests/unit/renderer/agent-options-store.test.tsx`).
  await expect(chip).toContainText(/Manual|Plan|Auto|Full access/);
  await chip.click();
  await page.getByRole("menu").getByRole("menuitemradio", { name: /Full access/ }).click();
  await expect(chip).toContainText("Full access");

  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("permission to run ls");
  await composer.press("Enter");
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle", { timeout: 20_000 });
  // The same prompt as the test above, and no card: the request was never
  // made. Nothing here auto-answered one.
  await expect(page.locator("[data-permission]")).toHaveCount(0);
  await expect(page.locator("[data-status-line]")).toHaveCount(0);
  await composer.fill("applied");
  await composer.press("Enter");
  await expect(page.locator("[data-turn][data-role=agent]").last()).toContainText("mode:full in full");

  // Left as the tests after this expect the sidebar: no rows under the
  // project (the archive test before this left it that way).
  const rows = page.locator("[data-session-row]");
  // The first one, over and over: a list of handles taken before the first
  // delete is a list of rows that no longer exist after it.
  while ((await rows.count()) > 0) {
    await rows.first().getByRole("button", { name: /actions$/ }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await expect(page.getByRole("menuitem", { name: "Delete" })).toBeHidden();
  }
  await expect(rows).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /What should we build in/ })).toBeVisible();
});

test("a signed-out agent asks to sign in", async () => {
  await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), signedOutProject);
  await page.locator("[data-chip=project]").click();
  // `Recent`, then a plain item per folder with a check on the current one
  // (`sidebar.spec.ts` covers the order and `Open folder…`).
  await page.getByRole("menuitem", { name: path.basename(signedOutProject) }).click();
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

/**
 * What `user-select` computes to for everything in the transcript matching
 * `selector` — one value when they agree, and the values joined when they do
 * not, so a mixture fails loudly. `no such node` rather than a default,
 * because an assertion that passes by matching nothing is not an assertion.
 */
async function selectability(selector: string): Promise<string> {
  return page.evaluate((query) => {
    const nodes = [...document.querySelectorAll(`[data-transcript] :is(${query})`)];
    if (nodes.length === 0) {
      return "no such node";
    }
    return [...new Set(nodes.map((node) => getComputedStyle(node).userSelect))].sort().join("/");
  }, selector);
}

/**
 * `lines` more lines into the focused composer, the way a person makes them:
 * Shift+Enter. The counter carries across calls, so the last line typed has
 * a name the assertions can look for.
 */
let typedLines = 0;
async function type(lines: number) {
  for (let index = 0; index < lines; index += 1) {
    if (typedLines > 0) {
      await page.keyboard.press("Shift+Enter");
    }
    await page.keyboard.type(`line ${typedLines}`);
    typedLines += 1;
  }
}

/** One popover's worth of fade and scale, before a picture is taken of it. */
async function settled() {
  await page.waitForTimeout(250);
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

/**
 * The row under the box is one line: `+`, every chip and the context ring
 * share its centre, and nothing has wrapped to a second line.
 */
async function expectOneRowComposer() {
  const row = page.locator("[data-composer-row]");
  const rowBox = await row.boundingBox();
  expect(rowBox, "the composer has no row under its box").not.toBeNull();
  const middle = rowBox!.y + rowBox!.height / 2;
  const items = page.locator("[data-composer-row] [data-chip], [data-composer-row] button");
  expect(await items.count(), "the row is empty").toBeGreaterThan(0);
  for (const item of await items.all()) {
    const box = await item.boundingBox();
    expect(box, "something in the row has no box").not.toBeNull();
    expect(Math.abs(box!.y + box!.height / 2 - middle), "the row has wrapped").toBeLessThan(6);
  }
}

/**
 * No chevron on any chip, in either row. The icon is the chip's one glyph,
 * so a chip with two of them is one that grew a chevron back.
 */
async function expectNoChevrons() {
  const chips = page.locator("[data-chip]");
  expect(await chips.count()).toBeGreaterThan(0);
  for (const chip of await chips.all()) {
    expect(await chip.locator("svg").count(), `${await chip.innerText()} has more than its icon`).toBe(1);
  }
}

/**
 * The shell's contract with the explorer closed, which is how it starts: a
 * 230px sidebar and the session taking the rest of the window. Two panes, not
 * three — a closed pane is not rendered (`Shell`). The explorer opens when
 * something opens in it (`tests/e2e/explorer.spec.ts`).
 */
async function expectPaneWidths() {
  const widths = await page.locator("[data-panel]").evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().width));
  expect(widths).toHaveLength(2);
  expect(Math.abs(widths[0]! - 230), `sidebar ${widths[0]}`).toBeLessThanOrEqual(1);
  expect(widths[1]!, `session ${widths[1]}`).toBeGreaterThanOrEqual(320);
  expect(Math.abs(widths[0]! + widths[1]! - await page.evaluate(() => window.innerWidth))).toBeLessThanOrEqual(3);
}
