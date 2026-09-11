import { execFileSync } from "node:child_process";
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

/**
 * The explorer, against this repository.
 *
 * The project is the checkout the suite is running from — a real tree with a
 * `.gitignore`, `node_modules`, LFS pointers and a hundred thousand files —
 * because that is where the interesting failures are. A fixture directory of
 * six files would pass while the tree ignored nothing and the watcher took ten
 * seconds to start.
 *
 * Every tab kind is opened and screenshotted. The screenshots are the point:
 * they are the only check on whether the pane *looks* like an app, and the
 * README says to look at them.
 */

declare const window: {
  innerWidth: number;
  localStorage: { getItem(key: string): string | null };
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string; name: string }> };
    settings: { set(patch: { theme?: string; cadPythonOverride?: string | null }): Promise<unknown> };
    explorer: { loadTabs(request: { projectId: string }): Promise<unknown[]> };
    runtime: { status(): Promise<{ state: string; python: string | null; source: string | null; cadgenVersion: string | null }> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const repoRoot = path.resolve(appRoot, "..", "..");
// The project's display name is the directory's basename — which in a git
// worktree is the worktree's name, not the repository's.
const projectName = path.basename(repoRoot);
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");

/** Files in this repository the suite opens. All tracked, none generated. */
// AGENTS.md rather than README.md: its source opens with a literal
// `# AGENTS.md` heading, so "preview" and "source" are visibly different
// documents. The root README opens with a block of raw HTML, which tells the
// two apart far less clearly.
const MARKDOWN = "AGENTS.md";
const IMAGE = "apps/desktop/build/icon.png";
const STEP = "models/examples/imported/import-smoke.step";

/**
 * The CAD tests run against whatever runtime the app resolves on its own —
 * the bundled one under `resources/runtime/<os>-<arch>/` when the bundler
 * has run, else the checkout's `.venv` — so the app is launched WITHOUT
 * `CAD_DESKTOP_PYTHON`. The first STEP test breaks the runtime on purpose
 * (an override pointing nowhere) to see the failure card; the render test
 * clears it and skips itself on a machine with no runtime at all (CI's
 * test job, which bundles nothing and has no venv).
 */
let cadReady = false;

/**
 * The review test gets a repository of its own, built in `beforeAll`.
 *
 * Reviewing *this* checkout was the obvious thing and the wrong one: the
 * screenshot then shows the state of the tree it is committed into, so every
 * run changes it, which changes the review, which changes the screenshot. A
 * fixture with one modified file and one untracked file is deterministic, and
 * it is still a real repository with real `git` behind it.
 */
let reviewRepo: string;

/**
 * A directory holding copies of this repository's `README.md` and
 * `AGENTS.md`.
 *
 * The editing test wants *these* files — raw HTML, badge images, GFM tables,
 * hard-wrapped prose — and it wants to save them and diff the result, which
 * is not something to do to the checkout the suite is running from.
 */
let docsDir: string;

let app: ElectronApplication;
let page: Page;
let userData: string;

test.beforeAll(async () => {
  reviewRepo = makeReviewRepo();
  docsDir = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-docs-"));
  for (const name of ["README.md", "AGENTS.md"]) {
    fs.copyFileSync(path.join(repoRoot, name), path.join(docsDir, name));
  }
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-explorer-e2e-"));
  const { CAD_DESKTOP_PYTHON: _unset, ...inherited } = process.env;
  const env = { ...inherited, NODE_ENV: "test" };
  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env,
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");

  // Dark, so every screenshot in this file is comparable with the others.
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));

  // The project is added through IPC rather than through the folder chooser:
  // a native dialog cannot be driven from Playwright.
  await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), repoRoot);
  await expect(page.getByText(projectName).first()).toBeVisible();
  // The strip binds to the project asynchronously (it loads `explorer_tabs`
  // and starts the watcher); `+` does nothing until it has.
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  // The explorer pane starts closed and opens when something opens in it
  // (plan §3). This suite is about what it *shows*, so it is opened once
  // here rather than incidentally by the first file.
  await page.getByRole("button", { name: "Toggle explorer" }).click();
  await expect(page.getByTestId("explorer")).toBeVisible();
});

test.afterAll(async () => {
  // Quitting takes the app anywhere from ten seconds to a few minutes — the
  // detector's CLI probes and the watcher over this repository are still
  // winding down — and a hook that gives up at sixty fails the last test.
  test.setTimeout(300_000);
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
  fs.rmSync(reviewRepo, { recursive: true, force: true });
  fs.rmSync(docsDir, { recursive: true, force: true });
});

test.describe.configure({ mode: "serial" });

test("opens a markdown file as a preview, then as source", async () => {
  await newTab(page, "File");

  // The tree is the way in, and it is what the filter is for. The root file
  // ranks above the other AGENTS.md in the tree — depth is the tie-break.
  await page.getByLabel("Filter files").fill(MARKDOWN);
  await page.getByRole("option", { name: MARKDOWN, exact: false }).first().click();

  // The breadcrumb names the file, and nothing above the root: a root crumb's
  // menu would be files outside the project.
  await expect(page.getByRole("button", { name: `Browse ${MARKDOWN}`, exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: `Browse ${projectName}`, exact: true })).toHaveCount(0);
  // Rendered markdown: the heading is an H1, not a line beginning with `#`.
  await expect(page.getByRole("heading", { level: 1, name: "AGENTS.md" })).toBeVisible();
  await shoot("file-markdown-preview.png");

  /*
    The source view is markdown's one PANEL (`@hardcore/ui/navigation`'s `panels.js`), declared
    the same way a CAD file declares its two: an icon button with
    `aria-pressed`, at the right end of the row and immediately left of the
    files toggle, which stays last. It used to be a special case in the
    header with its own label.
  */
  const toggle = page.getByTestId("tree-toggle");
  const source = page.getByRole("button", { name: "View source" });
  const [toggleBox, sourceBox] = await Promise.all([toggle.boundingBox(), source.boundingBox()]);
  expect(sourceBox!.x + sourceBox!.width).toBeLessThanOrEqual(toggleBox!.x + 1);
  await expect(source).toHaveAttribute("aria-pressed", "false");
  await expect(source).toHaveAttribute("data-file-panel", "source");
  // The tree is the open panel, and there is one panel column in the tab.
  await expect(panels(page)).toHaveCount(1);
  await expect(toggle).toHaveAttribute("aria-pressed", "true");

  await source.click();
  // Monaco is up, and it is showing the raw text — the `#` the preview ate.
  await expect(page.locator(".monaco-editor").first()).toBeVisible();
  await expect(page.locator(".view-lines").first()).toContainText("# AGENTS.md");
  // The panel is open, and the files toggle did not move to make room.
  const preview = page.getByRole("button", { name: "View preview" });
  await expect(preview).toHaveAttribute("aria-pressed", "true");
  expect(Math.abs((await toggle.boundingBox())!.x - toggleBox!.x)).toBeLessThan(1);
  /*
    ONE panel at a time, the tree included (the user's rule): the source view
    is a panel of this list, so opening it closed the tree, and the files
    toggle is no longer the pressed one. The tree used to be exempt — a
    second column beside the renderer's panels, with a design of its own.
  */
  await expect(panels(page)).toHaveCount(0);
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await expect(toggle).toHaveAttribute("aria-label", "Show files");
  await shoot("file-markdown-source.png");

  // ...and taking the tree back closes the source: back to the preview,
  // without pressing the source toggle at all.
  await toggle.click();
  await expect(panels(page)).toHaveCount(1);
  await expect(page.getByRole("heading", { level: 1, name: "AGENTS.md" })).toBeVisible();
  await expect(source).toHaveAttribute("aria-pressed", "false");
});

test("expands three levels of the tree, and keeps them", async () => {
  await newTab(page, "File");

  // Jake's repro: `apps`, then `apps/web`, then `apps/web/src`. Each
  // one is a lazy `explorer.list`, and each one used to be a click that shut
  // the tree instead of opening it once a file was open under any of them.
  const folder = (relative: string) => page.locator(`[role="treeitem"][data-path="${relative}"]`);

  await folder("apps").click();
  await expect(folder("apps/web")).toBeVisible();
  await folder("apps/web").click();
  await expect(folder("apps/web/src")).toBeVisible();
  await folder("apps/web/src").click();

  // The leaves of the third level, which is what "nothing happened" cost.
  await expect(folder("apps/web/src/client")).toBeVisible();
  await expect(folder("apps/web/src/shared")).toBeVisible();
  await expect(folder("apps/web/src")).toHaveAttribute("aria-expanded", "true");

  // Opening a file makes a tab, and a tab is a remount: the three levels have
  // to still be there afterwards, and a click on one of them has to shut it
  // rather than do nothing.
  await folder("apps/web/src/client").click();
  await page.locator(`[role="treeitem"][data-path="apps/web/src/client/unboundIdentifiers.test.js"]`).click();
  await expect(page.getByRole("tab", { name: /unboundIdentifiers\.test\.js/ })).toBeVisible();
  await expect(folder("apps/web/src/client")).toBeVisible();

  await folder("apps/web").click();
  await expect(folder("apps/web/src")).toHaveCount(0);
  await folder("apps/web").click();
  await expect(folder("apps/web/src/client")).toBeVisible();

  await shoot("file-tree-deep.png");
  await page.getByRole("tab", { name: /unboundIdentifiers\.test\.js/ }).getByRole("button", { name: "Close unboundIdentifiers.test.js" }).click();
});

test("navigates by the breadcrumb's menus", async () => {
  await newTab(page, "File");
  await openFromTree("apps/web/src/client/unboundIdentifiers.test.js");
  await expect(page.getByRole("tab", { name: /unboundIdentifiers\.test\.js/ })).toBeVisible();

  // The header is the breadcrumb, the view toggle and the files toggle. The
  // copy button and the `Open ▾` menu are gone: their items live in the
  // entry menus now (below).
  const header = page.getByTestId("explorer").locator("header");
  await expect(header.getByRole("button", { name: "Copy path" })).toHaveCount(0);
  await expect(header.getByRole("button", { name: "Open", exact: true })).toHaveCount(0);
  await expect(header.getByRole("button", { name: /^Open\b/ })).toHaveCount(0);

  // Wide enough for every folder to be its own crumb: the default pane folds
  // them into `…`, which is a menu of folders in its own right. The session
  // keeps its floor whatever the divider does, so the room comes from the
  // window as well as from the sidebar.
  await resizeWindow(1680, 1050);
  await widenExplorer();

  // There is no root crumb: the crumbs are the segments below the root, so
  // `apps` is the first of them and the project's own name is not a crumb at
  // all. A crumb for the root would have to list the root's neighbours, which
  // are outside the project.
  // `apps › web › src › client › unboundIdentifiers.test.js`, and no sixth crumb for the
  // project the five of them are in.
  const nav = header.getByRole("navigation", { name: "Breadcrumb" });
  await expect(nav.getByRole("button", { name: /^Browse / })).toHaveCount(5);
  await expect(nav.getByRole("button", { name: "Browse apps", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: `Browse ${projectName}`, exact: true })).toHaveCount(0);

  // A folder crumb lists its NEIGHBOURS — its parent's listing — with itself
  // marked; picking one navigates there.
  // Radix names a menu after its trigger, so each one is addressed by the
  // crumb that opened it — a menu on its way out is still in the DOM for
  // the length of its exit animation.
  await page.getByRole("button", { name: "Browse client", exact: true }).click();
  const menu = page.getByRole("menu", { name: "Browse client" });
  // `client` lives in `apps/web/src`, so the menu is that folder: itself
  // marked, and `shared` beside it.
  await expect(menu.getByRole("menuitem", { name: "client", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(menu.getByRole("menuitem", { name: "shared", exact: true })).toBeVisible();
  // Not its own children, which is what it used to list.
  await expect(menu.getByRole("menuitem", { name: "unboundIdentifiers.test.js", exact: true })).toHaveCount(0);
  // Directories first: every one of these is a submenu, above any files.
  await expect(menu.getByRole("menuitem").first()).toHaveAttribute("aria-haspopup", "menu");
  await shoot("file-crumb-menu.png", true);
  // Picking a neighbour navigates: its own listing is a submenu of it.
  await menu.getByRole("menuitem", { name: "shared", exact: true }).hover();
  const shared = page.getByRole("menu", { name: "shared" });
  await expect(shared.getByRole("menuitem").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);

  // The file crumb lists its siblings, with itself marked; a sibling folder
  // is a submenu of its own listing, and picking a file opens it in this tab.
  await page.getByRole("button", { name: "Browse unboundIdentifiers.test.js", exact: true }).click();
  const siblings = page.getByRole("menu", { name: "Browse unboundIdentifiers.test.js" });
  await expect(siblings.getByRole("menuitem", { name: "unboundIdentifiers.test.js", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(siblings.getByRole("menuitem", { name: "components", exact: true })).toBeVisible();
  await siblings.getByRole("menuitem", { name: "workbench" }).hover();
  const submenu = page.getByRole("menu", { name: "workbench" });
  await expect(submenu.getByRole("menuitem", { name: "persistence.js", exact: true })).toBeVisible();
  await submenu.getByRole("menuitem", { name: "persistence.js", exact: true }).click();
  await expect(page.getByRole("tab", { name: /persistence\.js/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Browse persistence.js", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: /^unboundIdentifiers\.test\.js/ })).toHaveCount(0);
  await expect(page.locator(".view-lines").first()).toBeVisible();
  await expect(page.getByRole("menu")).toHaveCount(0);

  // The file crumb's `⋯` opens the entry menu a right-click opens — the same
  // table, drawn as a dropdown — and it has no `Open`, because the crumb IS
  // the open file.
  await page.getByTestId("crumb-actions").click();
  const actions = page.getByRole("menu");
  await expect(actions.getByRole("menuitem", { name: "Open", exact: true })).toHaveCount(0);
  await expect(actions.getByRole("menuitem", { name: "Move to Trash" })).toBeVisible();
  await pick("Copy relative path");
  await expect
    .poll(() => app.evaluate(({ clipboard }) => clipboard.readText()))
    .toBe("apps/web/src/client/workbench/persistence.js");

  // Escape closes a crumb's menu.
  await page.getByRole("button", { name: "Browse workbench", exact: true }).click();
  await expect(page.getByRole("menu", { name: "Browse workbench" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);

  // A code file declares no panels of its own, so the tree is the whole list
  // and the row's right end is the files toggle alone (`@hardcore/ui/navigation`'s `panels.js`).
  await expect(header.locator("[data-file-panel]")).toHaveCount(1);
  await expect(header.locator("[data-file-panel]")).toHaveAttribute("data-file-panel", "tree");
  await expect(header.getByTestId("tree-toggle")).toBeVisible();

  await restoreLayout();
  await resizeWindow(1440, 900);
  await page.getByRole("tab", { name: /persistence\.js/ }).getByRole("button", { name: "Close persistence.js" }).click();
});

test("keeps the files toggle where it is when the tree opens and shuts", async () => {
  // The toggle is the right end of the header whether the tree is open or
  // not. It used to move into the tree's own header when the tree opened.
  const toggle = page.getByTestId("tree-toggle");
  await expect(toggle).toHaveAttribute("aria-label", "Hide files");
  const open = (await toggle.boundingBox())!;
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-label", "Show files");
  await expect(page.getByLabel("Filter files")).toHaveCount(0);
  const shut = (await toggle.boundingBox())!;
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-label", "Hide files");
  await expect(page.getByLabel("Filter files")).toBeVisible();
  const reopened = (await toggle.boundingBox())!;
  for (const box of [shut, reopened]) {
    expect(Math.abs(box.x - open.x)).toBeLessThan(1);
    expect(Math.abs(box.y - open.y)).toBeLessThan(1);
  }
  // And the tree's own header is the filter, nothing else.
  await expect(page.getByRole("button", { name: "Hide files" })).toHaveCount(1);
});


test("copies a relative path from a row's context menu", async () => {
  await newTab(page, "File");
  await openFromTree("apps/web/src/client/unboundIdentifiers.test.js");
  const row = page.locator(`[role="treeitem"][data-path="apps/web/src/client/unboundIdentifiers.test.js"]`);
  await expect(row).toBeVisible();

  await openContextMenu(row);
  const menu = page.getByRole("menu");
  await expect(menu.getByRole("menuitem", { name: "Copy reference" })).toHaveCount(0);
  await expect(menu.getByRole("menuitem", { name: "Move to Trash" })).toBeVisible();
  await shoot("file-context-menu.png");
  await pick("Copy relative path");
  await expect.poll(() => app.evaluate(({ clipboard }) => clipboard.readText())).toBe("apps/web/src/client/unboundIdentifiers.test.js");

  // Copy path is the absolute one, and Copy reference is there for a CAD file.
  await openContextMenu(row);
  await pick("Copy path");
  await expect.poll(() => app.evaluate(({ clipboard }) => clipboard.readText())).toBe(
    fs.realpathSync(path.join(repoRoot, "apps/web/src/client/unboundIdentifiers.test.js")),
  );
  await page.locator(`[role="treeitem"][data-path="apps/web/src/client"]`).click();
  const step = page.locator(`[role="treeitem"][data-path="${STEP}"]`);
  await page.getByLabel("Filter files").fill(STEP);
  await openContextMenu(page.getByRole("option", { name: STEP, exact: false }).first());
  await expect(page.getByRole("menu").getByRole("menuitem", { name: "Copy reference" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByLabel("Filter files").fill("");
  await expect(step).toHaveCount(0);
  await page.getByRole("tab", { name: /unboundIdentifiers\.test\.js/ }).getByRole("button", { name: "Close unboundIdentifiers.test.js" }).click();
});

test("opens an image with its dimensions", async () => {
  await newTab(page, "File");
  await openFromTree(IMAGE);

  const image = page.locator(`img[alt="icon.png"]`);
  await expect(image).toBeVisible();
  // The footer reports the real pixels, which is the reason to open a PNG here
  // rather than in Preview.
  await expect(page.getByText(/\d+ × \d+ · /)).toBeVisible();
  // The tree reveals what is open: `apps › desktop › build` are expanded and
  // the file is the selected row.
  await expect(page.getByRole("treeitem", { name: "icon.png" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await shoot("file-image.png");
});

test("shows the runtime's own error for a STEP file when the runtime cannot start", async () => {
  // An override that points nowhere is the one way to break the runtime on
  // every machine alike. The tab is not a placeholder: it says the runtime
  // did not start, shows the interpreter's words, and offers to try again.
  await page.evaluate(() => window.hardcore.settings.set({ cadPythonOverride: "/nowhere/python" }));
  const broken = await page.evaluate(() => window.hardcore.runtime.status());
  expect(broken.state).toBe("error");

  await newTab(page, "File");
  await openFromTree(STEP);
  await expect(page.getByText("The CAD runtime did not start")).toBeVisible();
  await expect(page.locator("[data-cad-failure=runtime-not-ready]")).toContainText("/nowhere/python");
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Runtime status" })).toBeVisible();
  // And no CAD panel toggles: the surface that draws those panels never came
  // up, so the CAD declaration offers none (`@hardcore/ui/navigation`'s `panels.js`) and the
  // tree is the whole list. Two lit buttons over a failure card would open
  // nothing.
  await expect(page.locator("[data-file-panel]")).toHaveCount(1);
  await expect(page.locator("[data-file-panel]")).toHaveAttribute("data-file-panel", "tree");
  await expect(page.getByTestId("tree-toggle")).toBeVisible();
  // ...so what the one panel column holds is the tree: the default falls to
  // it when the renderer has declared nothing, rather than leaving a column
  // with a panel in it that cannot be drawn.
  await expect(panels(page)).toHaveCount(1);
  await expect(panels(page)).toHaveAttribute("data-file-panel-container", "tree");
  await shoot("file-cad-failed.png");

  // With the override gone the runtime is whatever the app resolves; Try
  // again asks for the viewer once more without reopening the file.
  await page.evaluate(() => window.hardcore.settings.set({ cadPythonOverride: null }));
  const status = await page.evaluate(() => window.hardcore.runtime.status());
  cadReady = status.state === "ready";
  if (cadReady) {
    expect(status.cadgenVersion).toMatch(/^\d+\.\d+\.\d+/);
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 60_000 });
  }
  // Closed either way: the render test opens it again from a clean tab.
  await page.getByRole("tab", { name: /import-smoke\.step/ }).hover();
  await page.getByRole("tab", { name: /import-smoke\.step/ }).getByRole("button", { name: "Close import-smoke.step" }).click();
});

test("runs a command in a terminal tab", async () => {
  await newTab(page, "Terminal");

  await expect(page.locator(".xterm-screen")).toBeVisible();
  // The shell is a *login* shell, so it reads the user's profile before it
  // prompts. Typing into it before then is echoed by the tty and re-echoed by
  // the shell afterwards, which is a mess in a screenshot and a race in a test.
  await settleTerminal();
  await page.locator(".xterm-helper-textarea").click();

  // The command and its output have to be *different* strings, or the
  // assertion passes on the echoed keystrokes without the shell ever running.
  await page.keyboard.type("echo hardcore-$((6 * 7))");
  await page.keyboard.press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText("hardcore-42", { timeout: 20_000 });
  await shoot("terminal.png");
});

test("replays a terminal's scrollback exactly once on reattach", async () => {
  // Switching away unmounts the xterm; the pty keeps running in main. Coming
  // back writes the buffered scrollback *and* subscribes to the live stream,
  // and the two overlap — `terminal.data`'s sequence number is what stops the
  // shell's output being written twice.
  const before = await page.locator(".xterm-rows").innerText();
  const seen = occurrences(before, "hardcore-42");
  expect(seen).toBeGreaterThan(0);

  await page.getByRole("tab").first().click();
  await expect(page.locator(".xterm-screen")).toHaveCount(0);
  await page.getByRole("tab", { name: /Terminal/ }).click();
  await expect(page.locator(".xterm-screen")).toBeVisible();
  await settleTerminal();

  // The same count, not twice it. The whole point of the sequence number.
  const after = await page.locator(".xterm-rows").innerText();
  expect(occurrences(after, "hardcore-42")).toBe(seen);
});

test("browses to a URL in a browser tab", async () => {
  await newTab(page, "Browser");

  await expect(page.getByText("Start browsing")).toBeVisible();
  await shoot("browser-empty.png");

  await page.getByLabel("Address").fill("https://example.com");
  await page.keyboard.press("Enter");
  // The webview is its own process; asserting on the address bar and the tag
  // is what this suite can do without depending on the network.
  await expect(page.locator("webview")).toBeAttached();
  await expect(page.getByLabel("Address")).toHaveValue(/example\.com/);
  // The tab is titled by host, not by the whole URL.
  await expect(page.getByRole("tab", { name: /example\.com/ })).toBeVisible();
  await page.waitForTimeout(2500);
  await shoot("browser.png");
});

/**
 * After the terminal and browser tests, not before: this one resizes the
 * window, and the tests that click a tab by position want the strip as it
 * first was.
 */
test("renders a STEP file through the bundled runtime's viewer", async () => {
  test.skip(!cadReady, "no CAD runtime on this machine: no bundle under resources/runtime and no .venv");

  const status = await page.evaluate(() => window.hardcore.runtime.status());
  expect(status.state, JSON.stringify(status)).toBe("ready");
  expect(["bundled", "checkout"]).toContain(status.source);

  await newTab(page, "File");
  await openFromTree(STEP);

  // The viewer's surface: a WebGL canvas, and the STEP sheet's tabs. The
  // first open compiles the document in cadgen's build pool, so this is the
  // slow assertion of the suite.
  await expect(page.locator("canvas").first()).toBeVisible({ timeout: 60_000 });
  const tree = page.getByRole("tab", { name: "Model" });
  await expect(tree).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("tab", { name: "Source features" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Surfaces" })).toHaveCount(0);

  /*
    A CAD tab opens with the viewer's Inspector as its ONE panel — a STEP
    file's geometry and source features are why the tab is open — so the files
    toggle offers the tree rather than hiding it. The Inspector is drawn in
    this app's panel column (`panelSlot`), which is the same column the tree
    would be in, to the right of the model and never a drawer over it, at
    1440×900 and at 1280×800.
  */
  await expect(page.getByRole("button", { name: "Show files" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Hide files" })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Model", exact: true })).toBeVisible({ timeout: 120_000 });
  await page.waitForTimeout(1000);
  await shoot("file-cad-default.png", true);
  await expectInspectorBesideModel();
  await resizeWindow(1280, 800);
  await expectInspectorBesideModel();
  await shoot("file-cad-default-1280x800.png", true);
  /*
    The files toggle puts the tree in that column, which closes the
    Inspector: one panel, one column, whatever is in it. The tree used to
    open BESIDE it — two columns, two designs — and this pane was too narrow
    to hold both, which is why the tree used to hide itself here.
  */
  await page.getByRole("button", { name: "Show files" }).click();
  await expect(page.getByRole("button", { name: "Hide files" })).toBeVisible();
  await expect(page.getByLabel("Filter files")).toBeVisible();
  await expect(panels(page)).toHaveCount(1);
  await expect(page.getByRole("tab", { name: "Source features" })).toHaveCount(0);
  await shoot("file-cad-tree.png", true);
  // ...and the Inspector's own toggle brings it back, closing the tree.
  await page.locator("header [data-file-panel='cad-file-sheet']").click();
  await expect(page.getByRole("tab", { name: "Source features" })).toHaveCount(0);
  await expect(page.getByLabel("Filter files")).toHaveCount(0);
  await expect(panels(page)).toHaveCount(1);
  await resizeWindow(1440, 900);

  // At the explorer's widest — the sidebar hidden and the session at its
  // 560px floor — the surface holds everything at once, which is how a person
  // reviews a part. There is no fullscreen to reach for: the session pane is
  // never taken away, so this is as wide as the explorer gets. The tree lists
  // the document's solids once the compile lands.
  await widenExplorer();
  await expect(page.getByRole("treeitem", { name: /import-smoke/ }).first()).toBeVisible();
  await expectInspectorBesideModel();
  await page.waitForTimeout(1500);
  await shoot("file-cad.png", true);
  await resizeWindow(1280, 800);
  await shoot("file-cad-1280x800.png", true);
  await resizeWindow(1440, 900);

  // Display is an on-demand toolbar popover; closing it preserves per-file settings.
  await expect(page.getByRole("tab", { name: "Display", exact: true })).toHaveCount(0);
  const display = page.getByRole("button", { name: "Display", exact: true });
  await display.click();
  const displayPanel = page.getByRole("dialog", { name: "Display settings" });
  await expect(displayPanel).toBeVisible();
  await displayPanel.getByRole("combobox", { name: "Display mode" }).click();
  await page.getByRole("option", { name: "Wire", exact: true }).click();
  await displayPanel.getByRole("button", { name: "Close Display" }).click();
  await expect(displayPanel).toHaveCount(0);
  await display.click();
  await expect(displayPanel.getByRole("combobox", { name: "Display mode" })).toContainText("Wire");
  await displayPanel.getByRole("combobox", { name: "Display mode" }).click();
  await page.getByRole("option", { name: "Solid", exact: true }).click();
  await expect(page.getByRole("listbox")).toHaveCount(0);
  await expect(displayPanel).toBeVisible();
  await expect(displayPanel.getByRole("combobox", { name: "Display mode" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(displayPanel).toHaveCount(0);
  await expect(display).toHaveAttribute("aria-expanded", "false");
  await expect(display).toBeFocused();
  await expect(tree).toBeVisible();

  // Measurements live under the toolbar tool and close when it is toggled off.
  const measure = page.getByRole("button", { name: "Measure", exact: true });
  await measure.click();
  await expect(measure).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Select two points, edges, or faces to measure", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Finish measuring" })).toBeVisible();
  await shoot("file-cad-measure.png", true);
  await measure.click();
  await expect(measure).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: "Finish measuring" })).toHaveCount(0);
  await expect(tree).toBeVisible();

  /*
    A CAD file's two panels (`@hardcore/ui/navigation`'s `panels.js`): the viewer's theme editor
    and its Inspector, which `layout="desktop"` had left with no door in this
    app because that layout hides the top bar their toggles live in. Both sit
    left of the files toggle, which stays last and does not move for them, and
    each is highlighted while its panel is up.

    They and the file tree are ONE panel column with one design (the user's
    rule): whichever is up, there is exactly one container in the tab, and
    opening any of the three closes the other two.
  */
  const filesToggle = page.getByTestId("tree-toggle");
  const themePanel = page.locator("header [data-file-panel='cad-theme']");
  const sheetPanel = page.locator("header [data-file-panel='cad-file-sheet']");
  await expect(themePanel).toHaveAttribute("aria-label", "Theme settings");
  /*
    "Inspector", not "File sheet": the panel is the file's tree, its
    measurements and its parameters, and "sheet" named the mechanism. The id
    behind it is still `cad-file-sheet` — the tab's stored `panel` field
    holds it and the viewer's host contract calls it `fileSheetOpen` — so
    what changed is only what a person reads.

    And the glyph is the standalone viewer's own for this panel (its top bar
    renders lucide's `SlidersHorizontal` beside the theme toggle), so a
    person who knows one knows the other. It used to be a panel-layout icon,
    which named the mechanism as well.
  */
  await expect(sheetPanel).toHaveAttribute("aria-label", "Inspector");
  await expect(sheetPanel).toHaveAttribute("title", "Inspector");
  await expect(sheetPanel.locator("svg.lucide-sliders-horizontal")).toHaveCount(1);
  const parked = (await filesToggle.boundingBox())!;
  for (const panel of [themePanel, sheetPanel]) {
    const box = (await panel.boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(parked.x + 1);
  }
  // Declaration order: theme, then the Inspector, then the files toggle.
  expect((await themePanel.boundingBox())!.x).toBeLessThan((await sheetPanel.boundingBox())!.x);

  // The Inspector is open at this point (its Tree/Features tabs are on
  // screen), so its toggle is the pressed one.
  await expect(sheetPanel).toHaveAttribute("aria-pressed", "true");
  await expect(themePanel).toHaveAttribute("aria-pressed", "false");

  // The theme toggle opens the theme panel — the one thing this app had no
  // way to reach — and takes the highlight off the Inspector.
  await themePanel.click();
  await expect(themePanel).toHaveAttribute("aria-pressed", "true");
  await expect(sheetPanel).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("tab", { name: "Model" })).toHaveCount(0);
  // The theme panel takes the Inspector's place in the SAME column: the viewer
  // portals it into this app's panel container, so there is one of those and
  // it names the panel that is in it.
  await expect(panels(page)).toHaveCount(1);
  await expect(panels(page)).toHaveAttribute("data-file-panel-container", "cad-theme");
  // The viewer's own panel, inside this app's frame: the surface names what
  // it portaled, and it drew no aside of its own to put it in.
  await expect(page.locator("[data-file-sheet='Theme']")).toBeVisible();
  await expect(page.locator("[data-cad-surface] aside")).toHaveCount(0);
  await shoot("file-cad-theme.png", true);
  expect(Math.abs((await filesToggle.boundingBox())!.x - parked.x)).toBeLessThan(1);

  // The files toggle takes that column for the tree, which closes the theme
  // panel — the tree is one of these panels now, not a column beside them.
  await filesToggle.click();
  await expect(themePanel).toHaveAttribute("aria-pressed", "false");
  await expect(filesToggle).toHaveAttribute("aria-pressed", "true");
  await expect(panels(page)).toHaveCount(1);
  await expect(panels(page)).toHaveAttribute("data-file-panel-container", "tree");
  await expect(page.getByLabel("Filter files")).toBeVisible();
  await shoot("file-cad-files.png", true);

  // ...and the theme toggle takes it straight back off the tree.
  await themePanel.click();
  await expect(filesToggle).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByLabel("Filter files")).toHaveCount(0);
  await expect(panels(page)).toHaveAttribute("data-file-panel-container", "cad-theme");

  // Opening the Inspector closes the theme panel and swaps the highlight
  // back, and its sections are the STEP file's as before.
  await sheetPanel.click();
  await expect(sheetPanel).toHaveAttribute("aria-pressed", "true");
  await expect(themePanel).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("tab", { name: "Model" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Source features" })).toHaveCount(0);
  await expect(panels(page)).toHaveCount(1);
  await expect(panels(page)).toHaveAttribute("data-file-panel-container", "cad-file-sheet");
  await expectInspectorBesideModel();
  expect(Math.abs((await filesToggle.boundingBox())!.x - parked.x)).toBeLessThan(1);

  /*
    The CAD theme paints the SCENE and nothing else (the user's rule), and the
    app's colour scheme paints the chrome. So a dark studio inside a light
    window is a legal picture — and used to be an impossible one: the theme's
    background luminance wrote `.dark` on the document, so opening a STEP file
    under a dark preset repainted every panel, tab strip and menu in the app.

    Cinematic is the test case: a real dark stage — charcoal glossy floor,
    warm key light, dark materials — picked from the theme panel this app
    now draws in its own column.
  */
  await themePanel.click();
  const preset = panels(page).getByRole("combobox").first();
  await expect(preset).toContainText("System");
  const paint = () => panels(page).evaluate((node) => node.ownerDocument.defaultView!.getComputedStyle(node).backgroundColor);

  /*
    The System theme is the one that follows the app, and following it is
    about the BACKGROUND as much as the light/dark: the scene sits on this
    window's own `--background`, so a model under it is on the same ground as
    the chrome instead of in a framed studio. Dark first, because that is
    where this test is.
  */
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await expect.poll(sceneBackdrop).toEqual({ scene: await appBackground(), followsApp: true });

  // ...and it follows the app across a scheme change, both ways.
  await page.evaluate(() => window.hardcore.settings.set({ theme: "light" }));
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
  await expect.poll(async () => (await sceneBackdrop()).followsApp).toBe(true);
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await expect.poll(async () => (await sceneBackdrop()).followsApp).toBe(true);

  /*
    Cinematic is the test case for the other half of the rule: a real dark
    stage — charcoal glossy floor, warm key light, dark materials — picked
    from the theme panel this app draws in its own column, and it paints its
    OWN background. This app used to hand its `--background` to the surface
    for every theme, so the theme panel's eight presets were one colour here
    and picking a preset never changed the picture behind the model.
  */
  await preset.click();
  await page.getByRole("option", { name: "Cinematic" }).click();
  await expect(preset).toContainText("Cinematic");
  await expect.poll(async () => (await sceneBackdrop()).followsApp).toBe(false);
  const stage = (await sceneBackdrop()).scene;

  // The theme is dark and the chrome did NOT follow it: still the app's own
  // dark, which is what it was before the preset changed.
  const themeBefore = await activeCadTheme(page);
  expect(themeBefore, "the preset is stored by the viewer").toContain("cinematic");
  const panelDark = await paint();

  await page.evaluate(() => window.hardcore.settings.set({ theme: "light" }));
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
  // The panel's chrome went light with the app...
  await expect.poll(paint).not.toBe(panelDark);
  // ...and the theme did not move: the same dark stage under light chrome,
  // background included. A theme that is not System is DETACHED from the
  // app's light/dark, which is the whole point of picking one.
  expect(await activeCadTheme(page)).toEqual(themeBefore);
  await expect(preset).toContainText("Cinematic");
  expect(await sceneBackdrop()).toEqual({ scene: stage, followsApp: false });

  /*
    And the canvas fills the box it was given, with no band of the app's
    background above the scene. Invisible while the backdrop WAS the app's
    background; a one-pixel gap over a charcoal stage under light chrome is
    the first thing a person sees.
  */
  await expectCanvasFillsItsBox();
  await shoot("file-cad-light-chrome.png", true);

  // Back to the app's dark and the theme it came in with.
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await expect.poll(paint).toBe(panelDark);

  // Switching back to System puts the scene back on the app's ground.
  await preset.click();
  await page.getByRole("option", { name: "System" }).click();
  await expect(preset).toContainText("System");
  await expect.poll(sceneBackdrop).toEqual({ scene: await appBackground(), followsApp: true });
  await sheetPanel.click();

  await restoreLayout();
});

test("keeps every tab in one strip, with + at its end", async () => {
  // A file tab under the strip, not whichever tab happened to be last: this
  // shot is about the strip and the layout, and a review of *this* repository
  // in the background would make it change on every run. First, too, because
  // the STEP tab is the one open and the viewer's own Tree/Measure tabs
  // inside it are tabs as well.
  await page.getByRole("tab").first().click();
  // Two file tabs, a terminal and a browser — and the STEP when the runtime
  // could open it on this machine.
  await expect(page.getByRole("tab")).toHaveCount(cadReady ? 5 : 4);

  // `+` trails the tabs inside their scrolling row rather than sitting in a
  // corner of its own, and it is at the strip's right edge with five tabs of
  // real names in a pane this wide. `tests/e2e/shell.spec.ts` is where the
  // row is driven properly into overflow.
  const strip = page.locator("[data-tab-strip]");
  const plus = page.locator("[data-new-tab]");
  const [stripBox, plusBox, firstTabBox] = await Promise.all([
    strip.boundingBox(),
    plus.boundingBox(),
    page.getByRole("tab").first().boundingBox(),
  ]);
  expect(plusBox!.x).toBeGreaterThan(firstTabBox!.x);
  // `+` ends where the explorer's toggle begins: that toggle is the strip's
  // last control, pinned to the window's right edge, and `+` sits just
  // inside it.
  const toggleBox = (await strip.getByRole("button", { name: "Toggle explorer" }).boundingBox())!;
  expect(toggleBox.x + toggleBox.width).toBeLessThanOrEqual(stripBox!.x + stripBox!.width + 1);
  expect(plusBox!.x + plusBox!.width).toBeLessThanOrEqual(toggleBox.x + 1);
  expect(plusBox!.x + plusBox!.width).toBeGreaterThan(toggleBox.x - 24);
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeVisible();
  // And nothing that would take the session pane away.
  await expect(page.getByRole("button", { name: "Expand explorer" })).toHaveCount(0);

  await shoot("strip.png", true);
});

test("persists the strip across a reload", async () => {
  const before = await page.getByRole("tab").count();
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
  await expect(page.getByRole("tab")).toHaveCount(before, { timeout: 20_000 });
});

test("renders the explorer in light as well as dark", async () => {
  await page.evaluate(() => window.hardcore.settings.set({ theme: "light" }));
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
  // Every kind of tab, in light: the markdown preview, the image, the
  // terminal, the browser and — when a runtime is there — the CAD surface,
  // whose light is the app's, not the CAD theme's.
  await page.getByRole("tab").first().click();
  await shoot("explorer-light.png");
  await page.getByRole("tab", { name: /icon\.png/ }).click();
  await expect(page.locator(`img[alt="icon.png"]`)).toBeVisible();
  await shoot("file-image-light.png");
  await page.getByRole("tab", { name: /Terminal/ }).click();
  await expect(page.locator(".xterm-screen")).toBeVisible();
  await settleTerminal();
  await shoot("terminal-light.png");
  await page.getByRole("tab", { name: /example\.com/ }).click();
  await expect(page.getByLabel("Address")).toHaveValue(/example\.com/);
  await shoot("browser-light.png");
  if (cadReady) {
    await page.getByRole("tab", { name: /import-smoke\.step/ }).click();
    await expect(page.getByRole("tab", { name: "Model" })).toBeVisible({ timeout: 60_000 });
    // The app stays light: the surface follows the app's theme rather than
    // flipping the document to the CAD theme's own.
    await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
    await page.waitForTimeout(1000);
    await shoot("file-cad-light.png", true);
  }
  await page.getByRole("tab").first().click();
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
});

/**
 * Second to last: this one switches projects too, so it sits with the review
 * test at the end rather than in the middle of the strip's own tests.
 */
test("edits a markdown file in place and saves the lines it changed", async () => {
  await page.evaluate((directory) => window.hardcore.projects.addPath({ path: directory }), docsDir);
  // A project's section header collapses it; what *binds* the project is the
  // `+` on that header, which is the sidebar's `new chat in this project`.
  await page.getByRole("button", { name: `New chat in ${path.basename(docsDir)}` }).click();
  // A new project starts with the pane closed, like every other one.
  await page.getByRole("button", { name: "Toggle explorer" }).click();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();

  await newTab(page, "File");
  await page.getByLabel("Filter files").fill("AGENTS.md");
  await page.getByRole("option", { name: "AGENTS.md", exact: false }).first().click();

  // The document, not a preview of it: an H1 that is a real heading, and a
  // paragraph a caret can be put into.
  await expect(page.getByRole("heading", { level: 1, name: "AGENTS.md" })).toBeVisible();
  // Scoped to the explorer: the composer is a ProseMirror editor as well
  // (features/session/composer), and the first `.ProseMirror p` on the page
  // is the chat box.
  const paragraph = page.getByTestId("explorer").locator(".ProseMirror p").first();
  await paragraph.click();
  await page.keyboard.type("Edited in the app. ");

  // The tab says so, and Cmd/Ctrl+S is the same save Monaco gets.
  await expect(page.getByLabel("Unsaved changes")).toBeVisible();
  await shoot("file-markdown-editable.png");
  await page.keyboard.press(process.platform === "darwin" ? "Meta+s" : "Control+s");
  await expect(page.getByLabel("Unsaved changes")).toHaveCount(0);

  // The file on disk. The edited paragraph is re-printed; every other line of
  // a 210-line document is exactly the line it was — which is the whole point
  // of `packages/ui/src/renderers/markdown/document.ts`.
  const before = fs.readFileSync(path.join(repoRoot, "AGENTS.md"), "utf8");
  const after = fs.readFileSync(path.join(docsDir, "AGENTS.md"), "utf8");
  // Re-wrapped to the column the file wraps at, so the typed words can land on
  // either side of a newline.
  expect(after.replace(/\s+/g, " ")).toContain("Edited in the app.");

  // The other document, for the surfaces AGENTS.md has none of: raw HTML
  // blocks, badge images and a GFM table.
  await newTab(page, "File");
  await page.getByLabel("Filter files").fill("README.md");
  await page.getByRole("option", { name: "README.md", exact: false }).first().click();
  await expect(page.getByRole("table")).toBeVisible();
  await shoot("file-markdown-raw-blocks.png");

  const editedBlock = before.split("\n\n")[1]!;
  const untouched = before
    .split("\n")
    .filter((line) => line.trim() !== "" && !editedBlock.includes(line));
  expect(untouched.length).toBeGreaterThan(100);
  for (const line of untouched) {
    expect(after, `a line nobody edited was rewritten: ${line}`).toContain(line);
  }
});

/**
 * Still in the docs directory: it is a scratch copy, so making, renaming
 * and trashing things in it is fine, which it would not be in the checkout.
 */
test("makes a folder from the tree's menu, renames it, and moves it to the trash", async () => {
  const tree = page.getByTestId("explorer").getByRole("tree");
  const folder = (name: string) => page.locator(`[role="treeitem"][data-path="${name}"]`);
  // The test above left its filter in the box; this one wants the tree.
  await page.getByLabel("Filter files").fill("");
  await expect(folder("README.md")).toBeVisible();

  // The empty space under the rows is the root: New folder, typed in place.
  await openContextMenu(tree, { x: 40, y: 200 });
  await pick("New folder");
  const field = page.getByLabel("New folder name");
  await expect(field).toBeFocused();
  await field.fill("parts");
  await page.keyboard.press("Enter");
  await expect(folder("parts")).toBeVisible();
  expect(fs.statSync(path.join(docsDir, "parts")).isDirectory()).toBe(true);

  // Rename, in the row. The stem is what is selected, so typing replaces it.
  await openContextMenu(folder("parts"));
  await pick("Rename");
  const rename = page.getByLabel("Rename parts");
  await expect(rename).toBeFocused();
  await rename.fill("assemblies");
  await page.keyboard.press("Enter");
  await expect(folder("assemblies")).toBeVisible();
  await expect(folder("parts")).toHaveCount(0);
  expect(fs.existsSync(path.join(docsDir, "assemblies"))).toBe(true);
  expect(fs.existsSync(path.join(docsDir, "parts"))).toBe(false);

  // A file inside it, from the folder's own menu, opens once it is made.
  await openContextMenu(folder("assemblies"));
  await pick("New file");
  await page.getByLabel("New file name").fill("notes.md");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name: /notes\.md/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Browse notes.md", exact: true })).toBeVisible();
  expect(fs.readFileSync(path.join(docsDir, "assemblies", "notes.md"), "utf8")).toBe("");

  // F2 renames the cursor row from the keyboard, and Escape leaves it alone.
  await folder("assemblies/notes.md").click();
  await tree.focus();
  await page.keyboard.press("F2");
  await expect(page.getByLabel("Rename notes.md")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Rename notes.md")).toHaveCount(0);
  await expect(folder("assemblies/notes.md")).toBeVisible();

  // Move to Trash: no dialog, the row goes, the tab that showed the file goes.
  await openContextMenu(folder("assemblies"));
  await pick("Move to Trash");
  await expect(folder("assemblies")).toHaveCount(0);
  await expect(page.getByRole("tab", { name: /notes\.md/ })).toHaveCount(0);
  await expect.poll(() => fs.existsSync(path.join(docsDir, "assemblies"))).toBe(false);
});

/**
 * Last, because it switches projects: the strip belongs to the project, so
 * this leaves a different one selected than every test above it expects.
 */
test("reviews a repository's changes", async () => {
  await page.evaluate(
    (directory) => window.hardcore.projects.addPath({ path: directory }),
    reviewRepo,
  );
  await page.getByRole("button", { name: `New chat in ${path.basename(reviewRepo)}` }).click();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  // The pane's state is per project, so a project nobody has opened it in
  // starts closed however wide the last one was.
  await page.getByRole("button", { name: "Toggle explorer" }).click();
  await expect(page.getByTestId("explorer")).toBeVisible();

  await newTab(page, "Review");

  await expect(page.getByRole("button", { name: /All changes/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Commit or push" })).toBeVisible();

  // A tracked file, edited: git's own numstat.
  await expect(page.getByRole("button", { name: /tracked\.txt/ }).last()).toContainText("+1");
  // A new file's counts come from the file, not from `git diff` against a
  // revision that has never seen it — `git diff --no-index` reports "the files
  // differ" as exit code 1, and reading that as failure showed every added
  // file as `+0 −0`.
  await expect(page.getByRole("button", { name: /added\.txt/ }).last()).toContainText("+12");

  // Both sections open by default and both diffs arrive. A review whose
  // sections all say "Reading the diff…" is a list of filenames.
  await expect(page.locator(".monaco-diff-editor")).toHaveCount(2, { timeout: 30_000 });

  await shoot("review.png");
  await page.evaluate(() => window.hardcore.settings.set({ theme: "light" }));
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
  await shoot("review-light.png");
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
});

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

/** Open a path through the tree's filter — the way a person would. */
async function openFromTree(target: string) {
  const filter = page.getByLabel("Filter files");
  await filter.fill(target);
  await page.getByRole("option", { name: target, exact: false }).first().click();
  // Selection changes the mounted FileViewer. Do not clear the old tree or
  // open a context menu before the host has activated the requested file.
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveAttribute("title", target);
  // A CAD file in a narrow pane hides the tree, filter and all.
  if (await filter.isVisible()) {
    await filter.fill("");
  }
}

/**
 * macOS opens a context menu on right-button down. During its entry animation
 * a clamped popup can overlap the initiating pointer, and Radix interprets a
 * release over an item as drag-selection (including Move to Trash). Let the
 * popup settle before release so these tests exercise their explicit item
 * click, not an accidental drag-selection. Other platforms open on release.
 */
async function openContextMenu(target: Locator, position?: { x: number; y: number }) {
  if (process.platform !== "darwin") {
    await target.click({ button: "right", ...(position ? { position } : {}) });
  } else {
    await target.scrollIntoViewIfNeeded();
    const box = await target.boundingBox();
    if (!box) throw new Error("the context-menu target has no visible bounds");
    await page.mouse.move(box.x + (position?.x ?? box.width / 2), box.y + (position?.y ?? box.height / 2));
    await page.mouse.down({ button: "right" });
    try {
      const menu = page.getByRole("menu");
      await expect(menu).toBeVisible();
      await menu.evaluate((node) => Promise.all(
        node.getAnimations({ subtree: true }).map((animation: { finished: Promise<unknown> }) =>
          animation.finished.catch(() => {}),
        ),
      ));
    } finally {
      await page.mouse.up({ button: "right" });
    }
  }
  await expect(page.getByRole("menu")).toBeVisible();
}

/**
 * Pick an item from the open context menu, and wait for the menu to be
 * gone. A menu on its way out is still in the DOM for its exit animation,
 * and a right-click that lands during it is a dismiss, not a new menu.
 */
async function pick(item: string) {
  await page.getByRole("menu").getByRole("menuitem", { name: item }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
}

/**
 * Screenshot the explorer pane, not the window.
 *
 * Two-thirds of a full-window shot is the sidebar and the session pane, which
 * belong to other phases and are identical in all eleven of these. Clipping to
 * the pane makes each image both a better review artifact and a third of the
 * bytes — and these are committed, so they are read on every change.
 *
 * `whole` is for the two shots that *are* about the window: the strip under
 * pressure, and the expanded layout.
 */
async function shoot(name: string, whole = false) {
  const target = whole ? page : page.getByTestId("explorer");
  await target.screenshot({ path: path.join(screenshots, name), animations: "disabled" });
}

/** How wide the explorer was before `widenExplorer`, so it can be put back. */
let explorerBefore = 0;

/**
 * The explorer at its widest: the sidebar hidden and the session dragged down
 * to its 320px floor. There is no fullscreen — the session pane is not
 * collapsible, because the session is the app — so this is the whole of what
 * "give the CAD surface some room" means now.
 */
async function widenExplorer() {
  explorerBefore = (await page.getByTestId("explorer").boundingBox())!.width;
  // The sidebar's own toggle. A hidden sidebar is not in the document at all,
  // so once it is gone this locator finds nothing and the session's bar holds
  // the only copy of the button.
  await page.getByTestId("sidebar").getByRole("button", { name: "Toggle sidebar" }).click();
  await expect(page.getByTestId("sidebar")).toHaveCount(0);
  await dragSeparator(-4000);
  await expect
    .poll(async () => (await page.getByTestId("explorer").boundingBox())?.width ?? 0)
    .toBeGreaterThan(explorerBefore);
}

/**
 * Undo `widenExplorer`. By the distance it moved, not by four thousand
 * pixels: a drag that overshoots the explorer's minimum by 40px closes the
 * pane now, and this is meant to put the layout back, not to shut it.
 */
async function restoreLayout() {
  const wide = (await page.getByTestId("explorer").boundingBox())!.width;
  await dragSeparator(wide - explorerBefore);
  await page
    .locator("[data-session-header]")
    .getByRole("button", { name: "Toggle sidebar" })
    .click();
  await expect(page.getByTestId("sidebar")).toHaveCount(1);
}

/** Drag the separator between the session and the explorer; it clamps. */
async function dragSeparator(by: number) {
  const box = (await page.locator("[data-separator=explorer]").boundingBox())!;
  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + box.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + by, y, { steps: 12 });
  await page.mouse.up();
  await page.waitForTimeout(200);
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
  await page.waitForTimeout(400);
}

/**
 * The STEP sheet is a column to the right of the model, inside the surface:
 * its left edge is past the canvas's left edge by more than the sheet's own
 * width, and its right edge is the surface's. A drawer over the model would
 * fail the first; a sheet pinned to the window would fail the second.
 */
/** The file tab's panel column — one of them, whatever panel is in it. */
function panels(target: Page) {
  return target.locator("[data-file-panel-container]");
}

/**
 * The Inspector is a column beside the model, never a drawer over it.
 *
 * It is the app's own panel column now (`@hardcore/ui/navigation`'s `FilePanelColumn.jsx`) with the viewer's
 * panel portaled into it, so it sits BESIDE the surface rather than inside
 * it: the model gets the whole surface and the pane is what the column takes
 * its width from.
 */
async function expectInspectorBesideModel() {
  const surface = page.locator("[data-cad-surface]");
  const sheet = panels(page);
  await expect(sheet).toHaveAttribute("data-file-panel-container", "cad-file-sheet");
  await expect(page.getByRole("tab", { name: "Model" })).toBeVisible();
  const surfaceBox = (await surface.boundingBox())!;
  const sheetBox = (await sheet.boundingBox())!;
  const where = `surface ${JSON.stringify(surfaceBox)} sheet ${JSON.stringify(sheetBox)}`;
  expect(sheetBox.width, where).toBeGreaterThanOrEqual(180);
  // The model keeps the whole surface, and the sheet is to the right of it.
  expect(sheetBox.x, where).toBeGreaterThanOrEqual(surfaceBox.x + surfaceBox.width - 2);
  expect(surfaceBox.width, where).toBeGreaterThan(200);
  expect(sheetBox.height, where).toBeGreaterThan(surfaceBox.height * 0.9);
}

/**
 * The window's own ground and the colour the scene is painted on, as `r,g,b`.
 *
 * Both are read through a 2D canvas because the app's tokens are `oklch()`
 * and a theme's colours are hex, and a browser serialises a computed colour
 * in the space it was authored in — so two colours that are the same colour
 * compare unequal as strings. A canvas is the one converter every notation
 * goes through the same way.
 *
 * The scene's backdrop has no DOM presence of its own (it is a three.js
 * texture, and the viewport renderer keeps no drawing buffer), so the box the
 * canvas fills carries it: the viewer paints that box the scene's edge colour
 * for the frame between a resize and the renderer catching up.
 */
async function sceneBackdrop(): Promise<{ scene: string; followsApp: boolean }> {
  return page.locator("[data-cad-scene-backdrop]").evaluate((pane) => {
    const doc = pane.ownerDocument;
    const view = doc.defaultView!;
    const asRgb = (color: string) => {
      const context = doc.createElement("canvas").getContext("2d")!;
      context.fillStyle = "#000000";
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      const [red, green, blue] = context.getImageData(0, 0, 1, 1).data;
      return `${red},${green},${blue}`;
    };
    const scene = asRgb(view.getComputedStyle(pane).backgroundColor);
    return { scene, followsApp: scene === asRgb(view.getComputedStyle(doc.body).backgroundColor) };
  });
}

/** What the chrome paints itself: `--background`, through the same converter. */
async function appBackground(): Promise<string> {
  return page.locator("body").evaluate((body) => {
    const doc = body.ownerDocument;
    const context = doc.createElement("canvas").getContext("2d")!;
    context.fillStyle = "#000000";
    context.fillStyle = doc.defaultView!.getComputedStyle(body).backgroundColor;
    context.fillRect(0, 0, 1, 1);
    const [red, green, blue] = context.getImageData(0, 0, 1, 1).data;
    return `${red},${green},${blue}`;
  });
}

/**
 * The WebGL canvas covers its box exactly — no band of anything behind it.
 *
 * three.js sizes the canvas from a resize observer, a frame after its box
 * changes, so this is a real thing to get wrong; the two overlay canvases
 * over it are `aria-hidden` and laid out by CSS, which is why this asks for
 * the one that is not.
 */
async function expectCanvasFillsItsBox() {
  const pane = page.locator("[data-cad-scene-backdrop]");
  const canvas = pane.locator('canvas:not([aria-hidden="true"])');
  await expect(canvas).toHaveCount(1);
  await expect
    .poll(async () => {
      const box = (await pane.boundingBox())!;
      const drawn = (await canvas.boundingBox())!;
      return [drawn.x - box.x, drawn.y - box.y, drawn.width - box.width, drawn.height - box.height]
        .map((delta) => Math.round(Math.abs(delta)))
        .every((delta) => delta <= 1);
    })
    .toBe(true);
}

/**
 * The CAD theme as the viewer stores it — the scene's settings, which the
 * app's light/dark must not touch.
 */
async function activeCadTheme(target: Page): Promise<string | null> {
  return target.evaluate(() => window.localStorage.getItem("cad-viewer:theme"));
}

/**
 * Wait until the shell is at a prompt.
 *
 * The terminal is a *login* shell, so it runs the user's profile first —
 * `nvm`, `rbenv`, whatever they have — and that arrives in bursts with gaps
 * between them. "The text stopped changing" alone is not enough: a gap in the
 * middle of a slow profile looks exactly like the end of one, and typing into
 * that gap gets the keystrokes echoed by the tty and then again by the shell.
 *
 * So the real signal is a prompt waiting for input — a last line ending in one
 * of the four prompt characters — with the stability check as the fallback for
 * a prompt shaped like nothing in particular.
 */
async function settleTerminal() {
  let previous = "";
  let stableFor = 0;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const current = await page.locator(".xterm-rows").innerText();
    const lines = current.split("\n").filter((line) => line.trim() !== "");
    if (/[$%>#]\s*$/.test(lines.at(-1) ?? "")) {
      return;
    }
    // Three seconds of silence, not one: a slow `nvm` in someone's profile
    // pauses for well over a second in the middle, and typing into that pause
    // is what put a stray echoed command line into this pane's screenshot.
    stableFor = current !== "" && current === previous ? stableFor + 1 : 0;
    if (stableFor >= 20) {
      return;
    }
    previous = current;
    await page.waitForTimeout(150);
  }
}

function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

/**
 * A small git repository with one modified file and one untracked file.
 *
 * A real repository, run through the real `git`, because that is what
 * `src/main/projects/git.ts` shells out to — but a *fixed* one, so the review
 * screenshot shows the same thing on every run.
 */
function makeReviewRepo(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-review-repo-"));
  const run = (...args: string[]) =>
    execFileSync("git", args, { cwd: root, stdio: "ignore", env: gitEnv });

  run("init", "--quiet", "--initial-branch=main");
  fs.writeFileSync(path.join(root, "tracked.txt"), "one\ntwo\nthree\n");
  run("add", "-A");
  run("commit", "--quiet", "-m", "the state being reviewed against");

  fs.writeFileSync(path.join(root, "tracked.txt"), "one\ntwo\nthree\nfour\n");
  fs.writeFileSync(path.join(root, "added.txt"), "a line\n".repeat(12));
  return root;
}

/**
 * The fixture repository's identity, so it does not depend on the machine's
 * `user.name` being set — on a fresh CI runner `git commit` fails without one.
 */
const gitEnv = {
  ...process.env,
  GIT_AUTHOR_NAME: "Hardcore Tests",
  GIT_AUTHOR_EMAIL: "tests@example.invalid",
  GIT_COMMITTER_NAME: "Hardcore Tests",
  GIT_COMMITTER_EMAIL: "tests@example.invalid",
};

/**
 * Open a tab of one kind. `+` is a menu of the four kinds now, so every open
 * is two clicks — which is also the only way to reach a review or a terminal.
 */
async function newTab(page: Page, label: "File" | "Review" | "Browser" | "Terminal") {
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: label }).click();
  // A closing Radix menu can consume the next outside click. Start the next
  // interaction only after it has closed and the new file view has mounted.
  await expect(page.getByRole("menu")).toHaveCount(0);
  if (label === "File") {
    await expect(page.getByText("No file open", { exact: true })).toBeVisible();
  }
}
