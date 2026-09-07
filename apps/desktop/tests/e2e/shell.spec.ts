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
 * `page.evaluate` bodies run in the renderer, not here, so they see the
 * preload bridge. This file is compiled with the node tsconfig, which has no
 * DOM lib — the declaration is module-scoped and exists only to type those
 * snippets. Widening the node project's libs instead would hand `window` to
 * the main process, where it does not exist.
 */
declare const window: {
  hardcore: {
    settings: { set(patch: { theme: string }): Promise<unknown> };
    projects: {
      addPath(request: { path: string }): Promise<{ id: string }>;
      remove(request: { id: string }): Promise<void>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");

let app: ElectronApplication;
let page: Page;
let userData: string;

test.beforeAll(async () => {
  // A fresh user-data directory per run: the app's database, settings and
  // window geometry all live there, and a suite that inherited the
  // developer's would pass or fail depending on what they had open.
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-"));

  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test" },
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
});

test.afterAll(async () => {
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
});

/**
 * No project, no explorer. The strip is a view of a directory: with none
 * bound the panel is not in the document at all, and neither is the control
 * that would open it — the toggle in the title bar, or the palette's row.
 */
test("shows two panes and no explorer until a project is bound", async () => {
  const panes = page.locator("[data-panel]");
  await expect(panes).toHaveCount(2);
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Toggle explorer" })).toHaveCount(0);

  await expect(page.getByRole("button", { name: "Add project" })).toBeVisible();
  await expect(page.getByText("Projects", { exact: true })).toBeVisible();
  await expect(page.getByText("Add a project to get started")).toBeVisible();

  // Nor in the palette, and `Mod+Alt+B` has nothing to act on either.
  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeVisible();
  await expect(page.getByRole("option", { name: "Toggle sidebar" })).toBeVisible();
  await expect(page.getByRole("option", { name: "Toggle explorer" })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.keyboard.press(process.platform === "darwin" ? "Meta+Alt+b" : "Control+Alt+b");
  await expect(page.getByTestId("explorer")).toHaveCount(0);

  // Left to right, and the sidebar is the narrow one.
  const boxes = await panes.evaluateAll((nodes) =>
    nodes.map((node) => node.getBoundingClientRect().x),
  );
  expect(boxes).toEqual([...boxes].sort((a, b) => a - b));
});

/**
 * The sidebar's collapse sits at the right end of the sidebar's title strip
 * while the sidebar is open — the traffic lights' row, level with the
 * session's title bar and above the app's name — and at the far left of that
 * title bar once the sidebar is gone. (The explorer's toggle, which stays on
 * the right of that bar, needs a project: the test below.)
 */
test("the sidebar's collapse is right after the traffic lights, open or shut", async () => {
  const sidebar = page.getByTestId("sidebar");
  const header = page.locator("[data-session-header]");
  const inSidebar = sidebar.getByRole("button", { name: "Toggle sidebar" });
  await expect(inSidebar).toBeVisible();
  await expect(header.getByRole("button", { name: "Toggle sidebar" })).toHaveCount(0);
  const [toggleBox, nameBox, openTitleBox] = await Promise.all([
    inSidebar.boundingBox(),
    page.getByText("Hardcore", { exact: true }).boundingBox(),
    header.locator("[data-session-title]").boundingBox(),
  ]);
  // In the title strip above the name, level with the session's bar.
  expect(toggleBox!.y + toggleBox!.height).toBeLessThanOrEqual(nameBox!.y + 1);
  const toggleMid = toggleBox!.y + toggleBox!.height / 2;
  const titleMid = openTitleBox!.y + openTitleBox!.height / 2;
  expect(Math.abs(toggleMid - titleMid)).toBeLessThan(6);

  await inSidebar.click();
  // A collapsed pane is not rendered at all — the point of there being one
  // flag: no zero-width sidebar is left in the document holding a copy of
  // this button that nobody can click.
  await expect(sidebar).toHaveCount(0);

  // Gone, the same control is in the session's title bar — at the same
  // place on screen, so the eye and the pointer find it where it was.
  const collapse = header.getByRole("button", { name: "Toggle sidebar" });
  await expect(collapse).toBeVisible();
  const [collapseBox, titleBox] = await Promise.all([
    collapse.boundingBox(),
    header.locator("[data-session-title]").boundingBox(),
  ]);
  expect(collapseBox!.x).toBeLessThan(titleBox!.x);
  expect(Math.abs(collapseBox!.x - toggleBox!.x)).toBeLessThan(4);
  expect(Math.abs(collapseBox!.y - toggleBox!.y)).toBeLessThan(4);

  await collapse.click();
  await expect(sidebar).toHaveCount(1);
  await expect(inSidebar).toBeVisible();
});

test("the explorer opens and closes a tab", async () => {
  // A strip needs a project. `tests/e2e/explorer.spec.ts` covers what each
  // kind of tab then does; this is the shell's half of it.
  // A directory of its own, not `/tmp`: a project's root is watched, and
  // pointing a recursive watcher at the machine's temp directory is a great
  // deal of work before the first click can land.
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-shell-project-"));
  const project = await page.evaluate(
    (directory) => window.hardcore.projects.addPath({ path: directory }),
    fixture,
  );
  // A project brings the pane and its toggle back, on the right of the
  // session's title bar and with the project's own remembered state — closed,
  // for one nobody has opened it in.
  const header = page.locator("[data-session-header]");
  const toggle = header.getByRole("button", { name: "Toggle explorer" });
  await expect(toggle).toBeVisible();
  // Two panes, not three at a zero width: the explorer is closed for a
  // project nobody has opened it in, and a closed pane is not in the document.
  await expect(page.locator("[data-panel]")).toHaveCount(2);
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  const [toggleBox, titleBox] = await Promise.all([
    toggle.boundingBox(),
    header.locator("[data-session-title]").boundingBox(),
  ]);
  expect(toggleBox!.x).toBeGreaterThan(titleBox!.x);

  await openExplorer();
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeVisible();
  // Open, the toggle is the explorer's strip's last control — at the same
  // place on screen it had in the title bar, the window's right edge.
  await expect(header.getByRole("button", { name: "Toggle explorer" })).toHaveCount(0);
  const inStrip = page.locator("[data-tab-strip]").getByRole("button", { name: "Toggle explorer" });
  await expect(inStrip).toBeVisible();
  const stripBox = (await inStrip.boundingBox())!;
  expect(Math.abs(stripBox.x - toggleBox!.x)).toBeLessThan(4);
  expect(Math.abs(stripBox.y - toggleBox!.y)).toBeLessThan(4);

  // `+` is a menu of the four kinds now.
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: /^File/ }).click();
  await expect(page.getByRole("button", { name: "Close Untitled" })).toBeVisible();

  // The toggle answers in every state, from wherever it is drawn — with a tab
  // open, with the sidebar hidden, and from the palette. There is one of it in
  // the document at a time, so "the toggle did nothing" cannot be a state.
  await inStrip.click();
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  await header.getByRole("button", { name: "Toggle explorer" }).click();
  await expect(page.getByTestId("explorer")).toHaveCount(1);
  await page.getByTestId("sidebar").getByRole("button", { name: "Toggle sidebar" }).click();
  await expect(page.getByTestId("sidebar")).toHaveCount(0);
  await page.locator("[data-tab-strip]").getByRole("button", { name: "Toggle explorer" }).click();
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  await page.keyboard.press(process.platform === "darwin" ? "Meta+Alt+b" : "Control+Alt+b");
  await expect(page.getByTestId("explorer")).toHaveCount(1);
  await page.locator("[data-session-header]").getByRole("button", { name: "Toggle sidebar" }).click();
  await expect(page.getByTestId("sidebar")).toHaveCount(1);

  await page.getByRole("button", { name: "Close Untitled" }).click();
  await expect(page.getByText("Nothing open")).toBeVisible();

  // Put the app back the way the rest of this file expects to find it — and
  // taking the project away takes the pane with it.
  await page.evaluate((id) => window.hardcore.projects.remove({ id }), project.id);
  await expect(page.getByText("Add a project to get started")).toBeVisible();
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Toggle explorer" })).toHaveCount(0);
  fs.rmSync(fixture, { recursive: true, force: true });
});

/**
 * The strip under pressure, and the session's floor.
 *
 * `+` trails the last tab and sticks to the strip's right edge, so the button
 * that opens the eighth tab is not the thing that scrolled off when the
 * seventh was opened. And the session never collapses: dragging the explorer's
 * divider as far left as it goes stops at the session's 320px floor rather
 * than squeezing the pane out of the window.
 */
test("keeps + at the strip's right edge, and the session above its floor", async () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-shell-strip-"));
  const project = await page.evaluate(
    (directory) => window.hardcore.projects.addPath({ path: directory }),
    fixture,
  );
  await openExplorer();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();

  // The explorer at its floor, which is the pane a person actually has this
  // problem in: drag its separator right until it stops. Not by four thousand
  // pixels — 40px past the floor is a collapse now — but by the distance to
  // the floor and a little more, which clamps.
  const separator = page.locator("[data-separator=explorer]");
  await dragSeparator(separator, (await explorerWidth()) - PANE_LIMITS.explorer.min + 20);
  expect(await explorerWidth(), "the explorer would not narrow").toBeLessThan(360);
  expect(await explorerWidth(), "the explorer went under its floor").toBe(PANE_LIMITS.explorer.min);

  // Seven file tabs. Each is about a hundred pixels, so the row is twice the
  // pane and the seventh `+` is exactly the button that used to scroll away.
  for (let index = 0; index < 7; index += 1) {
    await page.getByRole("button", { name: "New tab", exact: true }).click();
    await page.getByRole("menuitem", { name: /^File/ }).click();
  }
  await expect(page.getByRole("tab")).toHaveCount(7);

  const strip = page.locator("[data-tab-strip]");
  const plus = page.locator("[data-new-tab]");
  const [stripBox, plusBox, firstBox] = await Promise.all([
    strip.boundingBox(),
    plus.boundingBox(),
    page.getByRole("tab").first().boundingBox(),
  ]);
  // The row really did overflow: the first tab is off the left edge of the
  // strip. Without that this assertion proves nothing about sticky.
  expect(firstBox!.x, "the strip did not overflow; the pin is untested").toBeLessThan(stripBox!.x);
  // And `+` is inside the strip, at its right end.
  expect(plusBox!.x).toBeGreaterThanOrEqual(stripBox!.x);
  // `+` ends where the explorer's toggle begins: that toggle is the strip's
  // last control, pinned to the window's right edge, and `+` sits just
  // inside it.
  const toggleBox = (await strip.getByRole("button", { name: "Toggle explorer" }).boundingBox())!;
  expect(toggleBox.x + toggleBox.width).toBeLessThanOrEqual(stripBox!.x + stripBox!.width + 1);
  expect(plusBox!.x + plusBox!.width).toBeLessThanOrEqual(toggleBox.x + 1);
  expect(plusBox!.x + plusBox!.width).toBeGreaterThan(toggleBox.x - 24);
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeVisible();
  await shoot(page, "strip-overflow.png");

  // The session's floor. Drag the same separator to the window's left edge:
  // the session stops at its 320px minimum instead of collapsing to nothing,
  // and the explorer stops growing there. The session is the app; it has no
  // collapse to reach.
  const sessionWidth = async () => (await page.getByTestId("session").boundingBox())?.width ?? 0;
  const roomy = await sessionWidth();
  await dragSeparator(separator, -4000);
  const floored = await sessionWidth();
  expect(floored, "the divider did not move the session at all").toBeLessThan(roomy);
  expect(floored, "the session was dragged under its minimum").toBeGreaterThanOrEqual(PANE_LIMITS.session.min);
  expect(floored, "the session kept more than its floor").toBeLessThanOrEqual(PANE_LIMITS.session.min + 2);
  await expect(page.locator("[data-session-header]")).toBeVisible();
  await expect(page.getByTestId("explorer")).toHaveCount(1);

  await page.evaluate((id) => window.hardcore.projects.remove({ id }), project.id);
  await expect(page.getByText("Add a project to get started")).toBeVisible();
  fs.rmSync(fixture, { recursive: true, force: true });
});

test("the command palette opens on the keyboard", async () => {
  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeHidden();
});

test("settings replaces the window and comes back", async () => {
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "General" })).toBeVisible();
  await expect(page.getByRole("button", { name: "About & Updates" })).toBeVisible();

  await page.getByRole("button", { name: "Appearance" }).click();
  await expect(page.getByRole("heading", { name: "Appearance" })).toBeVisible();
  await shoot(page, "settings.png");

  await page.getByRole("button", { name: "Back to app" }).click();
  await expect(page.getByText("Add a project to get started")).toBeVisible();
});

/**
 * The updater's whole path, end to end: main's status, over IPC, into the store,
 * onto the page. Its value here is `unsupported` — an unpackaged build has no
 * `app-update.yml` and must never be told to replace itself — and asserting the
 * honest empty state is the only assertion this suite can make without a real
 * release to check against.
 */
test("About reports the updater's state", async () => {
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("button", { name: "About & Updates" }).click();
  await expect(page.getByRole("heading", { name: "About & Updates" })).toBeVisible();

  await expect(page.getByText("Software update")).toBeVisible();
  await expect(page.getByText("Updates are delivered to installed builds")).toBeVisible();

  await page.getByRole("button", { name: "Back to app" }).click();
  await expect(page.getByText("Add a project to get started")).toBeVisible();
});

test("renders in both themes", async () => {
  // The canonical shots are of the app as it opens: no project, and so no
  // explorer at all — two panes and the session filling the window.
  await expect(page.getByTestId("explorer")).toHaveCount(0);

  // Dark, then light, through the real setting — which round-trips through
  // sqlite in main, so this also proves settings persist.
  for (const theme of ["dark", "light"] as const) {
    await setTheme(theme);
    await shoot(page, `shell-${theme}.png`);
  }

  // The canonical screenshot the review looks at.
  await setTheme("dark");
  await shoot(page, "shell.png");
});

/**
 * The explorer's width, and zero when it is closed: a closed pane is not in
 * the document, so there is nothing to measure rather than a zero-width box.
 */
async function explorerWidth() {
  const pane = page.getByTestId("explorer");
  return (await pane.count()) === 0 ? 0 : ((await pane.boundingBox())?.width ?? 0);
}

/** Open the explorer pane if it is closed — it starts that way (plan §3). */
async function openExplorer() {
  if ((await explorerWidth()) === 0) {
    await page.getByRole("button", { name: "Toggle explorer" }).click();
  }
  await expect.poll(explorerWidth).toBeGreaterThan(0);
}

/**
 * Drag a separator `by` pixels. A pane clamps at its minimum, and 40px past
 * it (`PANE_LIMITS.overshoot`) collapses instead — so a drag meant to reach a
 * floor aims at the floor rather than at infinity.
 */
async function dragSeparator(separator: Locator, by: number) {
  const box = (await separator.boundingBox())!;
  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + box.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + by, y, { steps: 12 });
  await page.mouse.up();
  await page.waitForTimeout(120);
}

async function setTheme(theme: "dark" | "light") {
  await page.evaluate((value) => window.hardcore.settings.set({ theme: value }), theme);
  await expect(page.locator("html")).toHaveClass(
    theme === "dark" ? /\bdark\b/ : /^(?!.*\bdark\b).*$/,
  );
}

/**
 * Screenshot with transitions finished.
 *
 * Half the app's surfaces carry `transition-colors`, so a shot taken the
 * instant the theme flips catches cards and buttons still holding the previous
 * theme's colour — a screenshot that looks like a token bug and is not one.
 * `animations: "disabled"` fast-forwards them to their end state.
 */
async function shoot(target: Page, name: string) {
  await target.screenshot({ path: path.join(screenshots, name), animations: "disabled" });
}
