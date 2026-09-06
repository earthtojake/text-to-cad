import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

/**
 * Every shortcut the Shortcuts page lists, pressed in the built app.
 *
 * The page prints `src/renderer/lib/shortcuts.ts`; this is the check that
 * each row does what it says. The menu carries the accelerators for the ones
 * that must work with focus inside a webview or an editor, and the renderer
 * carries a copy for when the menu is hidden — Playwright's `keyboard.press`
 * reaches the renderer's copy, which is the one a person hits with the
 * composer focused.
 */
declare const window: {
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    settings: { set(patch: Record<string, unknown>): Promise<unknown> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");
const mod = process.platform === "darwin" ? "Meta" : "Control";

let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;

test.beforeAll(async () => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-e2e-keys-"));
  project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-keys-"));
  for (const name of ["one.md", "two.md", "three.md"]) {
    fs.writeFileSync(path.join(project, name), `# ${name}\n`);
  }
  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: fakeAgent },
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
  await page.evaluate((dir) => window.hardcore.projects.addPath({ path: dir }), project);
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeEnabled();
});

test.afterAll(async () => {
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
  fs.rmSync(project, { recursive: true, force: true });
});

test.describe.configure({ mode: "serial" });

test("Cmd+, opens Settings and Escape closes it", async () => {
  await page.keyboard.press(`${mod}+Comma`);
  await expect(page.getByRole("heading", { name: "General" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: /What should we build in/ })).toBeVisible();
});

test("Cmd+K opens the palette and Escape closes it", async () => {
  await page.keyboard.press(`${mod}+K`);
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeHidden();
});

test("Cmd+1..9 switch tabs and Cmd+W closes the active one", async () => {
  for (const name of ["one.md", "two.md", "three.md"]) {
    await newTab(page, "File");
    await page.getByLabel("Filter files").fill(name);
    await page.getByRole("option", { name, exact: false }).first().click();
  }
  await expect(page.getByRole("tab")).toHaveCount(3);
  const selected = () => page.locator("[role=tab] [aria-selected=true]");

  await page.keyboard.press(`${mod}+1`);
  await expect(selected()).toContainText("one.md");
  await page.keyboard.press(`${mod}+2`);
  await expect(selected()).toContainText("two.md");
  // 9 is the last tab, however many there are.
  await page.keyboard.press(`${mod}+9`);
  await expect(selected()).toContainText("three.md");

  await page.keyboard.press(`${mod}+W`);
  await expect(page.getByRole("tab")).toHaveCount(2);
  await expect(page.getByRole("tab", { name: /three\.md/ })).toHaveCount(0);
});

test("Shift+Enter is a newline, Enter sends, Escape stops the turn", async () => {
  // Sending needs an agent, and the chip fills in once the detector has probed.
  await expect(page.locator("[data-context-strip] [data-chip=agent]")).not.toContainText("Choose an agent");
  const composer = page.getByPlaceholder("Do anything");
  await composer.click();
  await composer.fill("first line");
  await page.keyboard.press("Shift+Enter");
  await page.keyboard.type("second line");
  await expect(composer).toHaveValue("first line\nsecond line");
  // Still the new-session state: a newline did not send.
  await expect(page.locator("[data-session-view]")).toHaveCount(0);

  await composer.fill("slow");
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-session-view]")).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();

  // Escape in the composer stops the running turn.
  await page.getByPlaceholder("Send another message — it goes next").click();
  await page.keyboard.press("Escape");
  await expect(page.locator("[data-stopped]")).toBeVisible();
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
});

test("Cmd+N starts a new chat", async () => {
  await expect(page.locator("[data-session-view]")).toBeVisible();
  await page.keyboard.press(`${mod}+N`);
  await expect(page.getByRole("heading", { name: /What should we build in/ })).toBeVisible();
  await expect(page.locator("[data-session-view]")).toHaveCount(0);
});

test("Cmd+B and Cmd+Alt+B toggle the side panes", async () => {
  const sidebar = page.locator("[data-panel][data-panel-id=sidebar], [data-panel]").first();
  const before = (await sidebar.boundingBox())?.width ?? 0;
  expect(before).toBeGreaterThan(0);
  await page.keyboard.press(`${mod}+B`);
  await expect.poll(async () => (await sidebar.boundingBox())?.width ?? 0).toBe(0);
  await page.keyboard.press(`${mod}+B`);
  await expect.poll(async () => (await sidebar.boundingBox())?.width ?? 0).toBeGreaterThan(0);

  const explorer = page.getByTestId("explorer");
  await page.keyboard.press(`${mod}+Alt+B`);
  await expect.poll(async () => (await explorer.boundingBox())?.width ?? 0).toBe(0);
  await page.keyboard.press(`${mod}+Alt+B`);
  await expect.poll(async () => (await explorer.boundingBox())?.width ?? 0).toBeGreaterThan(0);
});

/**
 * Open a tab of one kind. `+` is a menu of the four kinds now, so every open
 * is two clicks — which is also the only way to reach a review or a terminal.
 */
async function newTab(page: Page, label: "File" | "Review" | "Browser" | "Terminal") {
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: label }).click();
}
