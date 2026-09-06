import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

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

test("the shell shows three panes", async () => {
  // The panes are the app: sidebar, session, explorer, left to right.
  const panes = page.locator("[data-panel]");
  await expect(panes).toHaveCount(3);

  await expect(page.getByRole("button", { name: "Add project" })).toBeVisible();
  await expect(page.getByText("Projects", { exact: true })).toBeVisible();
  await expect(page.getByText("Add a project to get started")).toBeVisible();
  // The explorer strip belongs to a project (P3), so an app with none has
  // nothing to open a tab from and says so. Scoped to the pane: the session
  // pane's composer carries a project chip that reads the same.
  await expect(page.getByTestId("explorer").getByText("No project")).toBeVisible();

  // Left to right, and the sidebar is the narrow one.
  const boxes = await panes.evaluateAll((nodes) =>
    nodes.map((node) => node.getBoundingClientRect().x),
  );
  expect(boxes).toEqual([...boxes].sort((a, b) => a - b));
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
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await expect(page.getByRole("button", { name: "Close Untitled" })).toBeVisible();
  await page.getByRole("button", { name: "Close Untitled" }).click();
  await expect(page.getByText("Nothing open")).toBeVisible();

  // Put the app back the way the rest of this file expects to find it.
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
