/**
 * Settings, end to end, in the real app (plan §10).
 *
 * Every page is visited in both themes and photographed, because most of what
 * can go wrong on these pages is not assertable: a card that lost its border in
 * light mode, a control that overflows its row, a dot whose colour means
 * nothing against the background it landed on. The assertions here are the
 * behaviours; the screenshots in `__screenshots__/settings-*.png` are the
 * review.
 *
 * The agent drawer is shot for two agents on purpose: one installed and one
 * that is installed but signed out, which are the two states the Installation
 * and Authentication sections exist to tell apart.
 */
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

/** `page.evaluate` bodies run in the renderer; see the note in shell.spec.ts. */
declare const window: {
  hardcore: { settings: { set(patch: Record<string, unknown>): Promise<unknown> } };
};
declare const document: { documentElement: object };
declare function getComputedStyle(element: object): { getPropertyValue(name: string): string };

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");

/** Nav label per page, in the order the nav lists them. */
const PAGES: [slug: string, label: string][] = [
  ["general", "General"],
  ["agents", "Agents"],
  ["appearance", "Appearance"],
  ["git", "Git & Worktrees"],
  ["shortcuts", "Keyboard shortcuts"],
  ["about", "About & Updates"],
];

let app: ElectronApplication;
let page: Page;
let userData: string;

test.beforeAll(async () => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-settings-e2e-"));
  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test" },
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  await setTheme("dark");
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "General" })).toBeVisible();
});

test.afterAll(async () => {
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
});

test("every page renders, in both themes", async () => {
  for (const theme of ["dark", "light"] as const) {
    await setTheme(theme);
    for (const [slug, label] of PAGES) {
      await page.getByRole("button", { name: label, exact: true }).click();
      await expect(page.getByRole("heading", { name: label })).toBeVisible();
      // The agent list arrives from a PATH probe; wait for it once so the
      // Agents shot is of the answer rather than of the spinner.
      if (slug === "agents") {
        await expect(page.getByText(/^Installed \(\d+\)$/)).toBeVisible();
      }
      // The runtime block probes the interpreter (`import cadgen` takes
      // seconds); the About shot is of the answer, whichever it is.
      if (slug === "about") {
        await expect(page.getByText("Checking…")).toHaveCount(0, { timeout: 90_000 });
      }
      await shoot(`settings-${slug}${theme === "light" ? "-light" : ""}.png`);
    }
  }
  await setTheme("dark");
});

test("General says what telemetry sends, and only that", async () => {
  await open("General");
  await expect(page.getByText("Share usage data")).toBeVisible();
  for (const event of ["App launched", "Session created", "File opened", "Settings changed"]) {
    await expect(page.getByText(event, { exact: true })).toBeVisible();
  }
  await expect(page.getByText("never the name or the path")).toBeVisible();
});

test("a switch round-trips through main's database", async () => {
  await open("Git & Worktrees");
  const fetchBefore = page.getByRole("switch", { name: "Fetch before creating" });
  await expect(fetchBefore).toBeChecked();
  await fetchBefore.click();
  await expect(fetchBefore).not.toBeChecked();

  // Leave the page and come back: the value came from sqlite, not from a
  // component that remembered it.
  await open("General");
  await open("Git & Worktrees");
  await expect(page.getByRole("switch", { name: "Fetch before creating" })).not.toBeChecked();
  await page.getByRole("switch", { name: "Fetch before creating" }).click();
});

test("the accent changes the token the whole app is painted with", async () => {
  await open("Appearance");
  const primary = () =>
    page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--primary"));

  const stock = await primary();
  await page.getByRole("button", { name: "Violet" }).click();
  await expect.poll(primary).not.toBe(stock);
  await shoot("settings-appearance-accent.png");

  await page.getByRole("button", { name: "Neutral" }).click();
  await expect.poll(primary).toBe(stock);
});

test("search finds a row on a page that is not open", async () => {
  await open("General");
  await expect(page.getByText("Branch prefix")).toHaveCount(0);

  await page.getByPlaceholder("Search settings").fill("branch prefix");
  await expect(page.getByText("Branch prefix")).toBeVisible();
  // A row that does not match is gone, not dimmed.
  await expect(page.getByText("Launch at login")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "About & Updates" })).toHaveCount(0);
  await shoot("settings-search.png");

  await page.getByPlaceholder("Search settings").fill("");
  await expect(page.getByText("Launch at login")).toBeVisible();
});

test("the agent drawer shows an installed agent and a signed-out one", async () => {
  await open("Agents");

  for (const theme of ["dark", "light"] as const) {
    await setTheme(theme);
    for (const [slug, name] of [
      ["codex", "Codex"],
      ["claude-code", "Claude Code"],
    ] as const) {
      await page.getByRole("button", { name, exact: true }).first().click();
      const drawer = page.getByRole("dialog");
      await expect(drawer.getByText("Installation")).toBeVisible();
      await expect(drawer.getByText("Authentication")).toBeVisible();
      await expect(drawer.getByText("Hardcore plugin")).toBeVisible();
      await expect(drawer.getByText("MCP servers")).toBeVisible();
      await expect(drawer.getByText("Advanced")).toBeVisible();
      // The launch line the app would run, from the registry.
      await expect(drawer.getByText("npx", { exact: true })).toBeVisible();
      await shoot(`settings-agent-${slug}${theme === "light" ? "-light" : ""}.png`);
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
    }
  }
  await setTheme("dark");

  // Escape closed the drawer and not the whole Settings route behind it.
  await expect(page.getByRole("heading", { name: "Agents" })).toBeVisible();
});

test("Escape leaves Settings once nothing is on top of it", async () => {
  await page.keyboard.press("Escape");
  await expect(page.getByText("Add a project to get started")).toBeVisible();

  // And the shortcut brings it back.
  await page.keyboard.press(process.platform === "darwin" ? "Meta+," : "Control+,");
  await expect(page.getByRole("heading", { name: "Agents" })).toBeVisible();
});

async function open(label: string) {
  await page.getByRole("button", { name: label, exact: true }).click();
  await expect(page.getByRole("heading", { name: label })).toBeVisible();
}

async function setTheme(theme: "dark" | "light") {
  await page.evaluate((value) => window.hardcore.settings.set({ theme: value }), theme);
  await expect(page.locator("html")).toHaveClass(
    theme === "dark" ? /\bdark\b/ : /^(?!.*\bdark\b).*$/,
  );
}

/** Screenshot with transitions finished (see the note in shell.spec.ts). */
async function shoot(name: string) {
  await page.screenshot({ path: path.join(screenshots, name), animations: "disabled" });
}
