import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  _electron as electron,
  expect,
  test,
  type ElectronApplication,
  type Locator,
  type Page,
} from "@playwright/test";

import { PANE_LIMITS } from "../../src/shared/types";

/**
 * The panes, and the top level's back and forward.
 *
 * Both were one defect: collapse used to be three states at once — a stored
 * preference, a panel library's own flag and a layout recomputed from pixels
 * — and they disagreed. A drag under a minimum sometimes snapped back and
 * sometimes closed a pane without recording it, which left the toggle in a
 * pane nobody could see and nothing on screen to press. So the rules asserted
 * here are the ones a person can feel:
 *
 * - a drag stops at a pane's minimum;
 * - 40px past it the pane closes, its toggle appears, and the toggle brings
 *   the pane back at the width it had;
 * - a closed pane is not in the document, so there is never a second copy of
 *   its toggle hidden behind it;
 * - the session never collapses, and a window too narrow for three minimums
 *   closes the explorer first and the sidebar second;
 * - back and forward walk the sessions and new-session screens the session
 *   pane has shown, and are muted at the ends.
 */
declare const window: {
  innerWidth: number;
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string }> };
    settings: { set(patch: { theme: string }): Promise<unknown> };
    agents: { refresh(): Promise<{ id: string; installed: boolean }[]> };
    sessions: {
      create(input: { projectId: string; agentId: string; gitMode: "checkout" }): Promise<{ id: string }>;
      rename(input: { id: string; title: string }): Promise<void>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;
let projectName: string;
let projectId: string;

test.beforeAll(async () => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-panes-"));
  project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-panes-project-"));
  projectName = path.basename(project);
  fs.writeFileSync(path.join(project, "README.md"), "# Panes\n\nA document to open.\n");

  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: fakeAgent },
  });
  page = await app.firstWindow();
  page.on("pageerror", (error) => {
    console.error(`[renderer] ${error.message}\n${error.stack ?? ""}`);
  });
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
  const added = await page.evaluate(
    (directory) => window.hardcore.projects.addPath({ path: directory }),
    project,
  );
  projectId = added.id;
  await expect(page.getByText(projectName).first()).toBeVisible();
  // The explorer's strip binds to the project asynchronously.
  await expect(page.getByRole("button", { name: "Toggle explorer" })).toBeVisible();
});

test.afterAll(async () => {
  await app?.close();
  for (const directory of [userData, project]) {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test("a drag stops at the sidebar's minimum and does not snap back", async () => {
  await expect.poll(sidebarWidth).toBe(PANE_LIMITS.sidebar.default);

  // Short of the overshoot: the pane narrows and stays narrowed. This is the
  // half that used to pop back open.
  await drag("sidebar", -30);
  expect(await sidebarWidth()).toBe(PANE_LIMITS.sidebar.default - 30);
  // Under the minimum but not past the overshoot: it stops at the minimum and
  // the pane is still there.
  await drag("sidebar", -(PANE_LIMITS.sidebar.default - 30 - PANE_LIMITS.sidebar.min) - 20);
  expect(await sidebarWidth(), "a drag under the minimum did not stop at it").toBe(
    PANE_LIMITS.sidebar.min,
  );
  await expect(page.locator("[data-sidebar-titlebar]")).toBeVisible();

  // Wide, and clamped at the maximum.
  await drag("sidebar", 1000);
  expect(await sidebarWidth()).toBe(PANE_LIMITS.sidebar.max);
  await drag("sidebar", PANE_LIMITS.sidebar.default - PANE_LIMITS.sidebar.max);
  expect(await sidebarWidth()).toBe(PANE_LIMITS.sidebar.default);
});

test("a drag 40px past the sidebar's minimum closes it, and the toggle brings that width back", async () => {
  await drag("sidebar", 200 - PANE_LIMITS.sidebar.default);
  expect(await sidebarWidth()).toBe(200);

  // The overshoot, in one gesture: the pane closes rather than clamping.
  await drag("sidebar", -(200 - PANE_LIMITS.sidebar.min) - PANE_LIMITS.overshoot - 4);
  await expect(page.getByTestId("sidebar")).toHaveCount(0);
  // And the control that brings it back is on screen — the whole complaint.
  const toggle = page.locator("[data-session-header]").getByRole("button", { name: "Toggle sidebar" });
  await expect(toggle).toBeVisible();
  await expect(page.locator("[data-shell]")).toHaveAttribute("data-leftmost", "session");
  await shoot("panes-sidebar-collapsed.png");

  await toggle.click();
  await expect(page.getByTestId("sidebar")).toHaveCount(1);
  // The width the drag stopped at, not the floor and not a share of anything.
  expect(await sidebarWidth()).toBe(200);
  await drag("sidebar", PANE_LIMITS.sidebar.default - 200);
});

test("the explorer collapses on the same rule and comes back at its width", async () => {
  await openExplorer();
  const wide = await explorerWidth();
  expect(wide).toBeGreaterThan(PANE_LIMITS.explorer.min);

  // Short of the overshoot: it stops at the floor.
  await drag("explorer", wide - PANE_LIMITS.explorer.min + 20);
  expect(await explorerWidth()).toBe(PANE_LIMITS.explorer.min);
  // The toggle is the strip's last control while the pane is open, and the
  // session's bar has none.
  await expect(page.locator("[data-tab-strip]").getByRole("button", { name: "Toggle explorer" })).toBeVisible();
  await expect(page.locator("[data-session-header]").getByRole("button", { name: "Toggle explorer" })).toHaveCount(0);

  // Past it: closed, and the toggle has moved to the session's bar.
  await drag("explorer", PANE_LIMITS.overshoot + 8);
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  const toggle = page.locator("[data-session-header]").getByRole("button", { name: "Toggle explorer" });
  await expect(toggle).toBeVisible();

  await toggle.click();
  await expect(page.getByTestId("explorer")).toHaveCount(1);
  expect(await explorerWidth()).toBe(PANE_LIMITS.explorer.min);
});

/**
 * The state the person hit: a markdown file open, the file tree hidden, and
 * the explorer's toggle doing nothing at all. It did nothing because the pane
 * had been collapsed by a drag without the store hearing about it, so the
 * only toggle in the document was the one inside the invisible pane.
 */
test("the explorer's toggle answers with a markdown file open and the tree hidden", async () => {
  await openExplorer();
  // Room for the tree and the document beside it: the test before this one
  // left the pane at its floor, where a file tab is all tree.
  const short = PANE_LIMITS.explorer.default - (await explorerWidth());
  if (short > 0) {
    await drag("explorer", -short);
  }
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: /^File/ }).click();
  await page.getByRole("treeitem", { name: /README\.md/ }).click();
  await expect(page.getByRole("tab", { name: /README\.md/ })).toBeVisible();
  // Rendered, not raw: the `#` became an H1 (the document editor is up).
  await expect(page.getByTestId("explorer").getByRole("heading", { level: 1, name: "Panes" })).toBeVisible();

  await page.getByTestId("tree-toggle").click();
  await expect(page.getByRole("button", { name: "Show files" })).toBeVisible();

  const inStrip = page.locator("[data-tab-strip]").getByRole("button", { name: "Toggle explorer" });
  await expect(inStrip).toBeVisible();
  await inStrip.click();
  await expect(page.getByTestId("explorer")).toHaveCount(0);

  const inHeader = page.locator("[data-session-header]").getByRole("button", { name: "Toggle explorer" });
  await expect(inHeader).toBeVisible();
  await inHeader.click();
  await expect(page.getByTestId("explorer")).toHaveCount(1);
  // The tab and the hidden tree are as they were: the pane closing is not the
  // strip being thrown away.
  await expect(page.getByRole("tab", { name: /README\.md/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Show files" })).toBeVisible();
  await page.getByRole("button", { name: "Show files" }).click();
});

/**
 * A window with no room closes a pane rather than overflowing — the explorer
 * first, the sidebar second — and the collapse is *state*, so both toggles are
 * on screen afterwards.
 */
test("a window too narrow for three minimums gives up the explorer, then the sidebar", async () => {
  await openExplorer();
  await expect(page.getByTestId("sidebar")).toHaveCount(1);
  // The window's own minimum is 900, which fits all three minimums; the test
  // is about the renderer, so the window is allowed under it for a moment.
  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()[0]!.setMinimumSize(360, 360);
  });

  await setContentSize(1100, 800);
  await expect(page.getByTestId("explorer")).toHaveCount(1);

  // 320 + 180 + 280 + two separators is 782: one pixel under it, the explorer
  // goes.
  await setContentSize(760, 700);
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  await expect(page.getByTestId("sidebar")).toHaveCount(1);
  await expect(page.locator("[data-session-header]").getByRole("button", { name: "Toggle explorer" })).toBeVisible();

  // 320 + 180 + one separator is 501: under that, the sidebar goes too.
  await setContentSize(460, 700);
  await expect(page.getByTestId("sidebar")).toHaveCount(0);
  await expect(page.locator("[data-session-header]").getByRole("button", { name: "Toggle sidebar" })).toBeVisible();
  await expect(page.getByTestId("session")).toBeVisible();

  // Growing the window does not undo a collapse — the toggles do, because a
  // pane that reopened itself would be a pane the person did not ask for.
  await setContentSize(1440, 900);
  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()[0]!.setMinimumSize(900, 600);
  });
  await page.locator("[data-session-header]").getByRole("button", { name: "Toggle sidebar" }).click();
  await expect(page.getByTestId("sidebar")).toHaveCount(1);
});

/**
 * Back and forward, over the top level only: the sessions and the project's
 * new-session screen. Codex's behaviour — the arrows sit right after the
 * sidebar's toggle and are muted, not hidden, at the ends of the stack.
 */
test("back and forward walk the sessions and the new-session screen", async () => {
  const strip = page.locator("[data-sidebar-titlebar]");
  const back = strip.getByRole("button", { name: "Back", exact: true });
  const forward = strip.getByRole("button", { name: "Forward", exact: true });
  // Right after the sidebar's toggle, in that order.
  const [toggleBox, backBox, forwardBox] = await Promise.all([
    strip.getByRole("button", { name: "Toggle sidebar" }).boundingBox(),
    back.boundingBox(),
    forward.boundingBox(),
  ]);
  expect(backBox!.x).toBeGreaterThan(toggleBox!.x);
  expect(forwardBox!.x).toBeGreaterThan(backBox!.x);
  // Nowhere to go yet: muted, and still there.
  await expect(back).toBeDisabled();
  await expect(forward).toBeDisabled();

  // Two threads, made through IPC: this test is about navigation, and a
  // prompt each would be two minutes of streaming to prove nothing extra.
  const ids = await page.evaluate(async (id) => {
    const created: string[] = [];
    // The detector probes at launch; `refresh` is the answer whenever it lands.
    const agents = await window.hardcore.agents.refresh();
    const agentId = (agents.find((agent) => agent.installed) ?? agents[0]!).id;
    for (const title of ["Alpha", "Beta"]) {
      const session = await window.hardcore.sessions.create({ projectId: id, agentId, gitMode: "checkout" });
      await window.hardcore.sessions.rename({ id: session.id, title });
      created.push(session.id);
    }
    return created;
  }, projectId);
  expect(ids).toHaveLength(2);

  const sidebar = page.getByTestId("sidebar");
  await sidebar.getByRole("button", { name: "Alpha", exact: true }).click();
  await expectShowing("Alpha");
  await sidebar.getByRole("button", { name: "Beta", exact: true }).click();
  await expectShowing("Beta");
  await sidebar.getByRole("button", { name: "New chat", exact: true }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`What should we build in ${projectName}`) })).toBeVisible();
  await expect(back).toBeEnabled();
  await expect(forward).toBeDisabled();

  await back.click();
  await expectShowing("Beta");
  await back.click();
  await expectShowing("Alpha");
  await back.click();
  await expect(page.getByRole("heading", { name: new RegExp(`What should we build in ${projectName}`) })).toBeVisible();
  // The bottom of the stack: muted, and the way out is forward.
  await expect(back).toBeDisabled();
  await expect(forward).toBeEnabled();
  await shoot("panes-history.png");

  await forward.click();
  await expectShowing("Alpha");
  await forward.click();
  await expectShowing("Beta");

  // The keyboard is the same two commands.
  const mod = process.platform === "darwin" ? "Meta" : "Control";
  await page.keyboard.press(`${mod}+BracketLeft`);
  await expectShowing("Alpha");
  await page.keyboard.press(`${mod}+BracketRight`);
  await expectShowing("Beta");

  // The pair moves with the sidebar's toggle, never off screen.
  await sidebar.getByRole("button", { name: "Toggle sidebar" }).click();
  const header = page.locator("[data-session-header]");
  await expect(header.getByRole("button", { name: "Back", exact: true })).toBeVisible();
  await expect(header.getByRole("button", { name: "Forward", exact: true })).toBeVisible();
  const movedBack = (await header.getByRole("button", { name: "Back", exact: true }).boundingBox())!;
  expect(Math.abs(movedBack.x - backBox!.x)).toBeLessThan(4);
  await header.getByRole("button", { name: "Toggle sidebar" }).click();
  await expect(sidebar).toHaveCount(1);
});

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

/** What the session pane is showing, by the title in its bar. */
async function expectShowing(title: string) {
  await expect(page.locator("[data-session-header] [data-session-title]")).toHaveText(title);
}

/** A pane's width, and zero when it is closed: a closed pane is not rendered. */
async function widthOf(pane: "sidebar" | "explorer" | "session") {
  const locator = page.getByTestId(pane);
  return (await locator.count()) === 0 ? 0 : ((await locator.boundingBox())?.width ?? 0);
}

const sidebarWidth = () => widthOf("sidebar");
const explorerWidth = () => widthOf("explorer");

async function openExplorer() {
  if ((await explorerWidth()) === 0) {
    await page.getByRole("button", { name: "Toggle explorer" }).click();
  }
  await expect(page.getByTestId("explorer")).toHaveCount(1);
}

/**
 * Drag one pane's separator `by` pixels — positive is to the right, so it
 * widens the sidebar and narrows the explorer.
 */
async function drag(pane: "sidebar" | "explorer", by: number) {
  const separator: Locator = page.locator(`[data-separator=${pane}]`);
  const box = (await separator.boundingBox())!;
  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + box.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + by, y, { steps: 10 });
  await page.mouse.up();
  await page.waitForTimeout(120);
}

async function setContentSize(width: number, height: number) {
  await app.evaluate(({ BrowserWindow }, size) => {
    BrowserWindow.getAllWindows()[0]!.setContentSize(size.width, size.height);
  }, { width, height });
  await page.waitForTimeout(250);
}

async function shoot(name: string) {
  await page.screenshot({ path: path.join(screenshots, name), animations: "disabled" });
}
