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
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string; name: string }> };
    settings: { set(patch: { theme?: string; cadPythonOverride?: string | null }): Promise<unknown> };
    explorer: { loadTabs(request: { projectId: string }): Promise<unknown[]> };
    runtime: { status(): Promise<{ state: string; python: string | null; cadgenVersion: string | null }> };
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
 * The interpreter the CAD tests point the app at: `CAD_DESKTOP_PYTHON`, or the
 * repository's `.venv` — the main checkout's when this is a worktree without
 * one. The app is launched WITHOUT the variable so the first STEP open shows
 * the not-set-up card (a worktree has no .venv and the throwaway user-data
 * directory has no managed runtime), and the override is then set through
 * Settings' IPC, which is the path a person takes.
 */
const CAD_PYTHON =
  process.env.CAD_DESKTOP_PYTHON ??
  [path.join(repoRoot, ".venv", "bin", "python"), path.resolve(repoRoot, "..", "..", "..", ".venv", "bin", "python")].find((candidate) =>
    fs.existsSync(candidate),
  ) ??
  null;

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

let app: ElectronApplication;
let page: Page;
let userData: string;

test.beforeAll(async () => {
  reviewRepo = makeReviewRepo();
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
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeEnabled();
});

test.afterAll(async () => {
  // Quitting takes the app anywhere from ten seconds to a few minutes — the
  // detector's CLI probes and the watcher over this repository are still
  // winding down — and a hook that gives up at sixty fails the last test.
  test.setTimeout(300_000);
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
  fs.rmSync(reviewRepo, { recursive: true, force: true });
});

test.describe.configure({ mode: "serial" });

test("opens a markdown file as a preview, then as source", async () => {
  await newTab(page, "File");

  // The tree is the way in, and it is what the filter is for. The root file
  // ranks above the other AGENTS.md in the tree — depth is the tie-break.
  await page.getByLabel("Filter files").fill(MARKDOWN);
  await page.getByRole("option", { name: MARKDOWN, exact: false }).first().click();

  // The breadcrumb names the project and the file, Codex-style.
  await expect(page.getByText(projectName, { exact: true }).last()).toBeVisible();
  // Rendered markdown: the heading is an H1, not a line beginning with `#`.
  await expect(page.getByRole("heading", { level: 1, name: "AGENTS.md" })).toBeVisible();
  await shoot("file-markdown-preview.png");

  await page.getByRole("button", { name: "View source" }).click();
  // Monaco is up, and it is showing the raw text — the `#` the preview ate.
  await expect(page.locator(".monaco-editor").first()).toBeVisible();
  await expect(page.locator(".view-lines").first()).toContainText("# AGENTS.md");
  await shoot("file-markdown-source.png");

  await page.getByRole("button", { name: "View preview" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "AGENTS.md" })).toBeVisible();
});

test("expands three levels of the tree, and keeps them", async () => {
  await newTab(page, "File");

  // Jake's repro: `apps`, then `apps/viewer`, then `apps/viewer/src`. Each
  // one is a lazy `explorer.list`, and each one used to be a click that shut
  // the tree instead of opening it once a file was open under any of them.
  const folder = (relative: string) => page.locator(`[role="treeitem"][data-path="${relative}"]`);

  await folder("apps").click();
  await expect(folder("apps/viewer")).toBeVisible();
  await folder("apps/viewer").click();
  await expect(folder("apps/viewer/src")).toBeVisible();
  await folder("apps/viewer/src").click();

  // The leaves of the third level, which is what "nothing happened" cost.
  await expect(folder("apps/viewer/src/client")).toBeVisible();
  await expect(folder("apps/viewer/src/shared")).toBeVisible();
  await expect(folder("apps/viewer/src")).toHaveAttribute("aria-expanded", "true");

  // Opening a file makes a tab, and a tab is a remount: the three levels have
  // to still be there afterwards, and a click on one of them has to shut it
  // rather than do nothing.
  await folder("apps/viewer/src/client").click();
  await page.locator(`[role="treeitem"][data-path="apps/viewer/src/client/main.jsx"]`).click();
  await expect(page.getByRole("tab", { name: /main\.jsx/ })).toBeVisible();
  await expect(folder("apps/viewer/src/client")).toBeVisible();

  await folder("apps/viewer").click();
  await expect(folder("apps/viewer/src")).toHaveCount(0);
  await folder("apps/viewer").click();
  await expect(folder("apps/viewer/src/client")).toBeVisible();

  await shoot("file-tree-deep.png");
  await page.getByRole("tab", { name: /main\.jsx/ }).getByRole("button", { name: "Close main.jsx" }).click();
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

test("shows the CAD runtime placeholder for a STEP file before a runtime exists", async () => {
  await newTab(page, "File");
  await openFromTree(STEP);

  // No override, no .venv in a worktree, nothing provisioned into a fresh
  // user-data directory: `cad.viewerOrigin` answers `runtime-not-ready` and
  // this is the surface the person gets — a real card with a real action.
  await expect(page.getByText("CAD runtime is not set up yet")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open CAD Runtime settings" })).toBeVisible();
  await shoot("file-cad-placeholder.png");
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
 * After the terminal and browser tests, not before: this one expands and
 * restores the layout, and the restored explorer is narrower than the initial
 * one, which scrolls the strip. The tests that click a tab by position want
 * the strip as it first was.
 */
test("renders a STEP file through the viewer once an interpreter is set", async () => {
  test.skip(CAD_PYTHON === null, "no CAD_DESKTOP_PYTHON and no .venv to point the app at");

  // The override is a setting; the runtime reads it fresh and probes cadgen.
  await page.evaluate((python) => window.hardcore.settings.set({ cadPythonOverride: python }), CAD_PYTHON);
  const status = await page.evaluate(() => window.hardcore.runtime.status());
  expect(status.state, JSON.stringify(status)).toBe("ready");
  expect(status.cadgenVersion).toMatch(/^\d+\.\d+\.\d+/);

  // A renderer asks for its origin once per mount: reopen the file.
  await page.getByRole("tab", { name: /import-smoke\.step/ }).hover();
  await page.getByRole("tab", { name: /import-smoke\.step/ }).getByRole("button", { name: "Close import-smoke.step" }).click();
  await newTab(page, "File");
  await openFromTree(STEP);

  // The viewer's surface: a WebGL canvas, and the STEP sheet's tabs. The
  // first open compiles the document in cadgen's build pool, so this is the
  // slow assertion of the suite.
  await expect(page.locator("canvas").first()).toBeVisible({ timeout: 60_000 });
  const tree = page.getByRole("tab", { name: "Tree" });
  await expect(tree).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("tab", { name: "Measure" })).toBeVisible();

  // At the explorer's default share the pane is too narrow for a model, a
  // sheet and the file tree: the tree hides itself for this file (the
  // header's toggle brings it back) and the sheet is a column to the right
  // of the model — never a drawer over it — at 1440×900 and at 1280×800.
  await expect(page.getByRole("button", { name: "Show files" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Hide files" })).toHaveCount(0);
  await expect(page.getByRole("tree").first()).toBeVisible({ timeout: 120_000 });
  await page.waitForTimeout(1000);
  await shoot("file-cad-default.png", true);
  await expectSheetBesideModel();
  await resizeWindow(1280, 800);
  await expectSheetBesideModel();
  await shoot("file-cad-default-1280x800.png", true);
  // The toggle brings the tree back for this file, and it stays back.
  await page.getByRole("button", { name: "Show files" }).click();
  await expect(page.getByRole("button", { name: "Hide files" })).toBeVisible();
  await resizeWindow(1440, 900);
  await expect(page.getByRole("button", { name: "Hide files" })).toBeVisible();

  // Expanded, the surface is wide enough for everything — which is how a
  // person reviews a part. The tree lists the document's solids once the
  // compile lands.
  await page.getByRole("button", { name: "Expand explorer" }).click();
  await expect(page.getByRole("button", { name: "Restore layout" })).toBeVisible();
  await expect(page.getByRole("treeitem", { name: /import-smoke/ }).first()).toBeVisible();
  await expectSheetBesideModel();
  await page.waitForTimeout(1500);
  await shoot("file-cad.png", true);
  await resizeWindow(1280, 800);
  await shoot("file-cad-1280x800.png", true);
  await resizeWindow(1440, 900);

  // The sheets are live: switching to Measure shows its empty state.
  await page.getByRole("tab", { name: "Measure" }).click();
  await expect(page.getByRole("tab", { name: "Measure" })).toHaveAttribute("aria-selected", "true");
  await shoot("file-cad-measure.png", true);
  await tree.click();
  await page.getByRole("button", { name: "Restore layout" }).click();
});

test("keeps every tab in one strip, and expands it", async () => {
  // A file tab under the strip, not whichever tab happened to be last: these
  // two shots are about the strip and the layout, and a review of *this*
  // repository in the background would make them change on every run. First,
  // too, because the STEP tab is the one open and the viewer's own
  // Tree/Measure tabs inside it are tabs as well.
  await page.getByRole("tab").first().click();
  // Five by now: three file tabs, a terminal and a browser.
  await expect(page.getByRole("tab")).toHaveCount(5);
  await shoot("strip.png", true);

  await page.getByRole("button", { name: "Expand explorer" }).click();
  // Expanded means the explorer owns the window: the sidebar and the session
  // are collapsed to zero.
  await expect(page.getByRole("button", { name: "Restore layout" })).toBeVisible();
  await shoot("expanded.png", true);
  await page.getByRole("button", { name: "Restore layout" }).click();
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
  if (CAD_PYTHON !== null) {
    await page.getByRole("tab", { name: /import-smoke\.step/ }).click();
    await expect(page.getByRole("tab", { name: "Tree" })).toBeVisible({ timeout: 60_000 });
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
 * Last, because it switches projects: the strip belongs to the project, so
 * this leaves a different one selected than every test above it expects.
 */
test("reviews a repository's changes", async () => {
  await page.evaluate(
    (directory) => window.hardcore.projects.addPath({ path: directory }),
    reviewRepo,
  );
  await page.getByText(path.basename(reviewRepo)).first().click();
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeEnabled();

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
  // A CAD file in a narrow pane hides the tree, filter and all.
  if (await filter.isVisible()) {
    await filter.fill("");
  }
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
async function expectSheetBesideModel() {
  const surface = page.locator("[data-cad-surface]");
  const sheet = page.getByRole("tab", { name: "Tree" }).locator("xpath=ancestor::aside[1]");
  await expect(sheet).toBeVisible();
  const surfaceBox = (await surface.boundingBox())!;
  const sheetBox = (await sheet.boundingBox())!;
  const where = `surface ${JSON.stringify(surfaceBox)} sheet ${JSON.stringify(sheetBox)}`;
  expect(sheetBox.width, where).toBeGreaterThanOrEqual(240);
  // The model keeps the rest of the surface: at 1280 the pane is 487px and
  // the model 247, which is a model, not a sliver.
  expect(sheetBox.x, where).toBeGreaterThan(surfaceBox.x + 200);
  expect(Math.abs(sheetBox.x + sheetBox.width - (surfaceBox.x + surfaceBox.width)), where).toBeLessThan(2);
  expect(sheetBox.height, where).toBeGreaterThan(surfaceBox.height * 0.9);
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
}
