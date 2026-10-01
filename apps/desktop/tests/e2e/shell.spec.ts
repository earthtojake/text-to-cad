import fs from "node:fs";
import path from "node:path";

import { expect, test, type ElectronApplication, type Page } from "@playwright/test";

import { TITLEBAR_HEIGHT, TRAFFIC_LIGHTS_INSET, trafficLightPosition } from "../../src/shared/titlebar";
import { PANE_LIMITS } from "../../src/shared/types";
import { dragSeparator, launch, mod, scratch, setContentSize, shoot as shootInto } from "./launch";
import { selectFixtureSession } from "./session-fixture";

/**
 * The window itself, on one app: the colour scheme from the first frame, the
 * traffic lights' corner, the panes' drag rules, Settings, and the keyboard.
 *
 * What is here is what a real window is needed for — AppKit's lights, real
 * layout under a real pointer, the menu's and the renderer's shortcuts, main's
 * database behind a switch. The rules underneath are unit tests: the pane
 * geometry (`tests/unit/renderer/panes.test.ts`), the theme resolution
 * (`theme.test.ts`), the sidebar's sections, filters and glyphs
 * (`sidebar.test.tsx`), Settings' search (`settings.test.tsx`) and the
 * history stack (`history.test.ts`).
 *
 * Screenshots go to each test's output directory; they are the review of how
 * the shell looks, which no assertion here can be.
 */

// `page.evaluate` bodies run in the renderer; this file is compiled with the
// node tsconfig, which has no DOM lib, so what they touch is declared here.
interface DomRect { left: number; top: number; right: number; width: number; height: number }
interface DomNode {
  id: string;
  parentElement: DomNode | null;
  nodeName: string;
  textContent: string | null;
  style: { cssText: string };
  getAttribute(name: string): string | null;
  getBoundingClientRect(): DomRect;
  querySelectorAll(selector: string): DomNode[];
  appendChild(child: DomNode): void;
  remove(): void;
}
declare const document: {
  body: DomNode;
  documentElement: DomNode;
  createElement(tag: string): DomNode;
  getElementById(id: string): DomNode | null;
  querySelector(selector: string): DomNode | null;
  querySelectorAll(selector: string): DomNode[];
};
declare function getComputedStyle(node: DomNode): { getPropertyValue(name: string): string };
declare const window: {
  localStorage: { getItem(key: string): string | null };
  __schemeSamples: { dark: boolean; colorScheme: string; prefersDark: boolean }[];
  __schemeFrames: number;
  textToCad: {
    projects: { addPath(request: { path: string }): Promise<{ id: string }> };
    settings: { get(): Promise<{ theme: string }>; set(patch: Record<string, unknown>): Promise<unknown> };
    agents: { list(): Promise<{ installed: boolean }[]> };
    sessions: { delete(request: { id: string }): Promise<void> };
  };
};

const isMac = process.platform === "darwin";

let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;
/** The room the window's own controls need, as the running app measured it. */
let inset: number;

/**
 * The document's scheme, sampled on every animation frame from the first line
 * of the page — an init script, so it survives a reload and runs before the
 * renderer's own modules. A flash that lasts one frame is one a person sees;
 * `toHaveClass` after the fact cannot see it at all. Only changes are kept.
 */
const SAMPLER = `
window.__schemeSamples = [];
window.__schemeFrames = 0;
const sample = () => {
  requestAnimationFrame(sample);
  if (document.readyState === "loading" || !document.documentElement) return;
  const now = {
    dark: document.documentElement.classList.contains("dark"),
    colorScheme: document.documentElement.style.colorScheme,
    prefersDark: window.matchMedia("(prefers-color-scheme: dark)").matches,
  };
  window.__schemeFrames += 1;
  const last = window.__schemeSamples[window.__schemeSamples.length - 1];
  if (!last || last.dark !== now.dark || last.colorScheme !== now.colorScheme || last.prefersDark !== now.prefersDark) {
    window.__schemeSamples.push(now);
  }
};
sample();
`;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  userData = scratch("shell");
  project = scratch("shell-project");
  for (const name of ["one.md", "two.md", "three.md"]) fs.writeFileSync(path.join(project, name), `# ${name}\n`);
  ({ app, page } = await launch({ userData }));
  // "Dark mode for my desktop", whatever this machine's own appearance is. The sampler and the
  // emulation are per page and have to be in place before the load being judged.
  await page.addInitScript(SAMPLER);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
  inset = await readInset();
});

test.afterAll(async () => {
  await app?.close();
  for (const dir of [userData, project]) fs.rmSync(dir, { recursive: true, force: true });
});

/* -------------------------------------------------------------------------- */
/* The colour scheme                                                           */
/* -------------------------------------------------------------------------- */

/**
 * "The light/dark mode seems to randomly change when I start using the app."
 * It did: the theme is a row in main's sqlite, so the renderer applied it one
 * paint after the window was shown, on every launch and reload. The sampler
 * asserts the document never once disagreed with the resolved preference.
 */
test("comes up dark on an OS in dark, with no light frame and nothing set", async () => {
  expect((await page.evaluate(() => window.textToCad.settings.get())).theme).toBe("system");
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await expectNeverMoved("dark", "boot");
  // The cache that made the first frame right, written from what main stored.
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem("text-to-cad.theme"))).toBe("system");
});

test("the scheme holds across Settings and a reload, follows the OS on System, and a chosen one detaches", async () => {
  // Settings replaces the whole tree — the biggest re-render the app has — and `<html>` is above it.
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Appearance", exact: true }).click();
  await expect(page.getByRole("button", { name: "System", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expectNeverMoved("dark", "Settings and its Appearance page");
  await page.keyboard.press("Escape");
  await expect(page.getByText("Choose a folder to get started")).toBeVisible();
  // A reload is what a dev-server hot reload does, and the case the pre-paint applier is for.
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
  await expect(page.getByText("Choose a folder to get started")).toBeVisible();
  await expectNeverMoved("dark", "a reload");

  // The OS moving under a running app: `system` is resolved live, and never written.
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
  await forgetSamples();
  await expectNeverMoved("light", "the OS switching to light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await forgetSamples();
  expect((await page.evaluate(() => window.textToCad.settings.get())).theme).toBe("system");
  // A chosen theme detaches from the OS.
  await setTheme("light");
  await forgetSamples();
  await expectNeverMoved("light", "Light chosen under an OS in dark");
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem("text-to-cad.theme"))).toBe("light");
  await setTheme("dark");
});

/* -------------------------------------------------------------------------- */
/* Before a session                                                            */
/* -------------------------------------------------------------------------- */

test("before a session: two panes, no explorer, and the chooser in both halves", async () => {
  // A strip belongs to a session: with none bound, neither the panel nor anything that would
  // open it — the title bar's toggle, the palette's row, Mod+Alt+B — is there.
  await expect(page.locator("[data-panel]")).toHaveCount(2);
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Toggle explorer" })).toHaveCount(0);
  await expect(page.getByTestId("sidebar").getByRole("button", { name: "Open folder…" })).toBeVisible();
  await expect(page.locator("[data-no-project]").getByRole("button", { name: "Open folder…" })).toBeVisible();
  await page.keyboard.press(`${mod}+K`);
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeVisible();
  await expect(page.getByRole("option", { name: "Toggle sidebar" })).toBeVisible();
  await expect(page.getByRole("option", { name: "Open folder…" })).toBeVisible();
  await expect(page.getByRole("option", { name: "Toggle explorer" })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeHidden();
  await page.keyboard.press(`${mod}+Alt+b`);
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  // The sidebar's collapse is in its title strip, level with the session's bar.
  const [toggleBox, titleBox] = await Promise.all([
    page.getByTestId("sidebar").getByRole("button", { name: "Toggle sidebar" }).boundingBox(),
    page.locator("[data-session-header] [data-session-title]").boundingBox(),
  ]);
  expect(Math.abs(toggleBox!.y + toggleBox!.height / 2 - (titleBox!.y + titleBox!.height / 2))).toBeLessThan(6);
  for (const theme of ["light", "dark"] as const) {
    await setTheme(theme);
    await shoot(`shell-${theme}.png`);
  }
});

/* -------------------------------------------------------------------------- */
/* The traffic lights' corner, and the panes' drag rules                        */
/* -------------------------------------------------------------------------- */

/**
 * With `titleBarStyle: "hiddenInset"` AppKit paints the lights over the
 * top-left of the window; a control there is one nobody can press. The room
 * is not typed into this file: main pins the cluster and Chromium reports
 * where content may start (`--titlebar-inset`), and this fails if that and
 * `src/shared/titlebar.ts` drift apart.
 *
 * The drags are the panes' fixed bug: a drag under a minimum sometimes snapped
 * back and sometimes closed a pane without recording it, leaving no toggle to
 * press. A drag stops at the minimum; 40px past it the pane closes, its toggle
 * appears, and the toggle brings back the width it had.
 */
test("the lights' corner stays clear, and a drag stops at the minimum or closes past it", async () => {
  const position = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]!.getWindowButtonPosition());
  if (!isMac) {
    expect(position).toBeNull();
    expect(inset).toBe(0);
  } else {
    expect(position).toEqual(trafficLightPosition());
    expect(position!.y * 2).toBeLessThanOrEqual(TITLEBAR_HEIGHT);
    expect(inset, "update src/shared/titlebar.ts and the .platform-mac fallback in globals.css together").toBe(TRAFFIC_LIGHTS_INSET);
    expect(position!.x).toBeLessThan(inset);
  }
  await expectLeftmost("sidebar", "[data-sidebar-titlebar]");
  await shootTitlebar("titlebar-sidebar.png");

  const sidebar = page.getByTestId("sidebar");
  const separator = page.locator("[data-separator=sidebar]");
  const width = async () => ((await sidebar.count()) === 0 ? 0 : ((await sidebar.boundingBox())?.width ?? 0));
  expect(await width()).toBe(PANE_LIMITS.sidebar.default);
  // Short of the minimum it narrows and stays narrowed: the half that used to pop back open.
  await dragSeparator(page, separator, -30);
  expect(await width()).toBe(PANE_LIMITS.sidebar.default - 30);
  // Under the minimum but not past the overshoot: it stops at the minimum.
  await dragSeparator(page, separator, -(PANE_LIMITS.sidebar.default - 30 - PANE_LIMITS.sidebar.min) - 20);
  expect(await width(), "a drag under the minimum did not stop at it").toBe(PANE_LIMITS.sidebar.min);
  await expectLeftmost("sidebar", "[data-sidebar-titlebar]");
  // Past the overshoot, in one gesture: closed, and the session's bar takes the corner and the toggle.
  await dragSeparator(page, separator, -PANE_LIMITS.overshoot - 8);
  expect(await width(), "the sidebar did not close past its overshoot").toBe(0);
  await expectLeftmost("session", "[data-session-header]");
  await shootTitlebar("titlebar-session.png");
  await page.locator("[data-session-header]").getByRole("button", { name: "Toggle sidebar" }).click();
  await expect(sidebar).toHaveCount(1);
  expect(await width(), "the toggle did not bring back the width the drag stopped at").toBe(PANE_LIMITS.sidebar.min);
  // Wide, and clamped at the maximum; then back to the default.
  await dragSeparator(page, separator, 1000);
  expect(await width()).toBe(PANE_LIMITS.sidebar.max);
  await dragSeparator(page, separator, PANE_LIMITS.sidebar.default - PANE_LIMITS.sidebar.max);
  expect(await width()).toBe(PANE_LIMITS.sidebar.default);

  // The window at its minimum, with the session's bar leftmost.
  await collapseSidebar(true);
  await setContentSize(app, page, 900, 600);
  await expectLeftmost("session", "[data-session-header]");
  await collapseSidebar(false);
  await expectLeftmost("sidebar", "[data-sidebar-titlebar]");
  await setContentSize(app, page, 1440, 900);

  // Settings replaces the shell and reserves the corner itself; the palette over everything
  // puts nothing there.
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "General" })).toBeVisible();
  await expectClear("settings");
  await expectFirstControlClears("[data-settings-header]");
  await expectDragRegion("[data-settings-header]");
  await shootTitlebar("titlebar-settings.png");
  await page.getByRole("button", { name: "Back to app" }).click();
  await expect(page.getByText("Choose a folder to get started")).toBeVisible();
  await page.keyboard.press(`${mod}+K`);
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeVisible();
  await expectClear("palette");
  await page.keyboard.press("Escape");
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeHidden();
});

/* -------------------------------------------------------------------------- */
/* Settings                                                                    */
/* -------------------------------------------------------------------------- */

const PAGES: [slug: string, label: string][] = [
  ["general", "General"],
  ["agents", "Agents"],
  ["appearance", "Appearance"],
  ["git", "Git & Worktrees"],
  ["shortcuts", "Keyboard shortcuts"],
  ["about", "About & Updates"],
];

test("Settings: every page renders, and what it shows comes from main", async () => {
  await page.keyboard.press(`${mod}+Comma`);
  await expect(page.getByRole("heading", { name: "General" })).toBeVisible();
  for (const [slug, label] of PAGES) {
    await open(label);
    if (slug === "agents") {
      // The list is main's PATH probe. Empty groups are absent: a clean runner has no
      // installed CLI but still lists the registry's recommended agents.
      await expect.poll(() => page.evaluate(async () => (await window.textToCad.agents.list()).length)).toBeGreaterThan(0);
      const installed = await page.evaluate(async () => (await window.textToCad.agents.list()).filter((agent) => agent.installed).length);
      const installedGroup = page.getByText(/^Installed \(\d+\)$/);
      if (installed > 0) await expect(installedGroup).toHaveText(`Installed (${installed})`);
      else await expect(installedGroup).toHaveCount(0);
      await expect(page.getByText("Looking for agents on this machine…")).toHaveCount(0);
    }
    if (slug === "about") {
      // The runtime block probes the interpreter; the shot is of its answer. The updater's
      // path, main to page: an unpackaged build has no `app-update.yml` and is never told
      // to replace itself.
      await expect(page.getByText("Checking…")).toHaveCount(0, { timeout: 90_000 });
      await expect(page.getByText("Updates are delivered to installed builds")).toBeVisible();
    }
    await shoot(`settings-${slug}.png`);
  }

  // A switch round-trips through main's database: leave the page and come back, and the value
  // is sqlite's, not a component's memory.
  await open("Git & Worktrees");
  const fetchBefore = () => page.getByRole("switch", { name: "Fetch before creating" });
  await expect(fetchBefore()).toBeChecked();
  await fetchBefore().click();
  await expect(fetchBefore()).not.toBeChecked();
  await open("General");
  await open("Git & Worktrees");
  await expect(fetchBefore()).not.toBeChecked();
  await fetchBefore().click();
  await expect(fetchBefore()).toBeChecked();

  // The accent is the token the whole app is painted with.
  await open("Appearance");
  const primary = () => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--primary"));
  const stock = await primary();
  await page.getByRole("button", { name: "Violet" }).click();
  await expect.poll(primary).not.toBe(stock);
  await page.getByRole("button", { name: "Neutral" }).click();
  await expect.poll(primary).toBe(stock);

  // The agent drawer, for an installed agent and a signed-out one: what a session is given,
  // read-only, and nothing installed into the agent's own configuration.
  await open("Agents");
  for (const [slug, name] of [["codex", "Codex"], ["claude-code", "Claude Code"]] as const) {
    await page.getByRole("button", { name, exact: true }).first().click();
    const drawer = page.getByRole("dialog");
    for (const section of ["Installation", "Authentication", "MCP servers", "Advanced"]) await expect(drawer.getByText(section)).toBeVisible();
    await expect(drawer.getByText("Skills", { exact: true })).toBeVisible();
    await expect(drawer.getByText(/plugin/i)).toHaveCount(0);
    await expect(drawer.getByRole("button", { name: /reinstall/i })).toHaveCount(0);
    await expect(drawer.getByText("npx", { exact: true })).toBeVisible();
    await shoot(`settings-agent-${slug}.png`);
    // Escape closes the drawer, not the route behind it...
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Agents" })).toBeVisible();
  }
  // ...and then Settings, once nothing is on top of it.
  await page.keyboard.press("Escape");
  await expect(page.getByText("Choose a folder to get started")).toBeVisible();
});

/* -------------------------------------------------------------------------- */
/* A session's explorer, and the keyboard                                      */
/* -------------------------------------------------------------------------- */

test("a session owns the explorer: its toggles, its strip and its shortcuts", async () => {
  const session = await selectFixtureSession(page, project);
  // Selecting a session brings the toggle with that session's own state — closed.
  const header = page.locator("[data-session-header]");
  const toggle = header.getByRole("button", { name: "Toggle explorer" });
  await expect(toggle).toBeVisible();
  await expect(page.locator("[data-panel]")).toHaveCount(2);
  const toggleBox = (await toggle.boundingBox())!;
  await toggle.click();
  await expect(page.getByTestId("explorer")).toHaveCount(1);
  // Open, the toggle is the strip's last control, where the title bar's was.
  await expect(header.getByRole("button", { name: "Toggle explorer" })).toHaveCount(0);
  const inStrip = page.locator("[data-tab-strip]").getByRole("button", { name: "Toggle explorer" });
  const stripBox = (await inStrip.boundingBox())!;
  expect(Math.abs(stripBox.x - toggleBox.x)).toBeLessThan(4);
  expect(Math.abs(stripBox.y - toggleBox.y)).toBeLessThan(4);
  // A session and its explorer do not move the corner.
  await expectLeftmost("sidebar", "[data-sidebar-titlebar]");

  // Three files, then Mod+1..9 and Mod+W. 9 is the last tab, however many there are.
  for (const name of ["one.md", "two.md", "three.md"]) {
    await newTab("File");
    await page.getByLabel("Filter files").fill(name);
    await page.getByRole("option", { name, exact: false }).first().click();
    await expect(page.getByRole("tab", { name: new RegExp(name.replace(".", "\\.")) })).toBeVisible();
  }
  const selected = () => page.locator("[role=tab] [aria-selected=true]");
  await page.keyboard.press(`${mod}+1`);
  await expect(selected()).toContainText("one.md");
  await page.keyboard.press(`${mod}+2`);
  await expect(selected()).toContainText("two.md");
  await page.keyboard.press(`${mod}+9`);
  await expect(selected()).toContainText("three.md");
  await page.keyboard.press(`${mod}+W`);
  await expect(page.getByRole("tab")).toHaveCount(2);

  // The toggle answers in every state, from wherever it is drawn: there is one of it in the
  // document at a time, so "the toggle did nothing" cannot be a state.
  await inStrip.click();
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  await header.getByRole("button", { name: "Toggle explorer" }).click();
  await expect(page.getByTestId("explorer")).toHaveCount(1);
  await page.keyboard.press(`${mod}+B`);
  await expect(page.getByTestId("sidebar")).toHaveCount(0);
  await expectLeftmost("session", "[data-session-header]");
  await page.keyboard.press(`${mod}+Alt+b`);
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  await page.keyboard.press(`${mod}+Alt+b`);
  await expect(page.getByTestId("explorer")).toHaveCount(1);
  await page.keyboard.press(`${mod}+B`);
  await expect(page.getByTestId("sidebar")).toHaveCount(1);

  // The strip under pressure, in the pane a person has the problem in: the explorer at its
  // floor and seven tabs, twice its width. `+` stays at the strip's right edge, just inside
  // the toggle, rather than scrolling off with the tabs.
  const explorerSeparator = page.locator("[data-separator=explorer]");
  const explorerWidth = async () => (await page.getByTestId("explorer").boundingBox())?.width ?? 0;
  await dragSeparator(page, explorerSeparator, (await explorerWidth()) - PANE_LIMITS.explorer.min + 20);
  expect(await explorerWidth(), "the explorer went under its floor").toBe(PANE_LIMITS.explorer.min);
  for (let index = 0; index < 5; index += 1) await newTab("File");
  await expect(page.getByRole("tab")).toHaveCount(7);
  const strip = page.locator("[data-tab-strip]");
  const [stripRow, plusBox, firstBox] = await Promise.all([
    strip.boundingBox(), page.locator("[data-new-tab]").boundingBox(), page.getByRole("tab").first().boundingBox(),
  ]);
  expect(firstBox!.x, "the strip did not overflow; the pin is untested").toBeLessThan(stripRow!.x);
  const pinned = (await strip.getByRole("button", { name: "Toggle explorer" }).boundingBox())!;
  expect(pinned.x + pinned.width).toBeLessThanOrEqual(stripRow!.x + stripRow!.width + 1);
  expect(plusBox!.x + plusBox!.width).toBeLessThanOrEqual(pinned.x + 1);
  expect(plusBox!.x + plusBox!.width).toBeGreaterThan(pinned.x - 24);
  await shoot("strip-overflow.png");

  // The session never collapses: the same separator dragged to the window's left edge stops
  // at the session's floor.
  const sessionWidth = async () => (await page.getByTestId("session").boundingBox())?.width ?? 0;
  const roomy = await sessionWidth();
  await dragSeparator(page, explorerSeparator, -4000);
  expect(await sessionWidth()).toBeLessThan(roomy);
  expect(await sessionWidth()).toBeGreaterThanOrEqual(PANE_LIMITS.session.min);
  expect(await sessionWidth()).toBeLessThanOrEqual(PANE_LIMITS.session.min + 2);
  await expect(page.getByTestId("explorer")).toHaveCount(1);

  await page.evaluate((id) => window.textToCad.sessions.delete({ id }), session.id);
  await expect(page.getByText("Choose a folder to get started")).toBeVisible();
});

test("in the composer, Shift+Enter is a newline, Enter sends, Escape stops, and Mod+N starts over", async () => {
  await page.evaluate((dir) => window.textToCad.projects.addPath({ path: dir }), project);
  // Sending needs an agent, and the chip fills in once the detector has probed.
  await expect(page.locator("[data-new-session] [data-composer-row] [data-chip=model]")).toBeVisible({ timeout: 30_000 });
  const composer = page.getByPlaceholder("Do anything");
  await composer.click();
  await composer.fill("first line");
  await page.keyboard.press("Shift+Enter");
  await page.keyboard.type("second line");
  // The composer is an editor: the break is a hard break, and the draft it prints is the form's field.
  await expect(page.locator('[data-composer] textarea[name="message"]')).toHaveValue("first line\nsecond line");
  await expect(page.locator("[data-session-view]")).toHaveCount(0);
  await composer.fill("slow");
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-session-view]")).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  await page.getByPlaceholder("Send another message — it goes next").click();
  await page.keyboard.press("Escape");
  await expect(page.locator("[data-stopped]")).toBeVisible();
  await expect(page.locator("[data-session-view]")).toHaveAttribute("data-session-status", "idle");
  await page.keyboard.press(`${mod}+N`);
  await expect(page.getByRole("heading", { name: /What should we build in/ })).toBeVisible();
  await expect(page.locator("[data-session-view]")).toHaveCount(0);
});

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

async function shoot(name: string) {
  await shootInto(page, name, test.info());
}

async function open(label: string) {
  await page.getByRole("button", { name: label, exact: true }).click();
  await expect(page.getByRole("heading", { name: label })).toBeVisible();
}

async function newTab(label: "File" | "Terminal") {
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: label }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
}

async function setTheme(theme: "dark" | "light") {
  await page.evaluate((value) => window.textToCad.settings.set({ theme: value }), theme);
  await expect(page.locator("html")).toHaveClass(theme === "dark" ? /\bdark\b/ : /^(?!.*\bdark\b).*$/);
}

/** No frame since the last drain disagreed with the expected scheme; waits for sampled frames. */
async function expectNeverMoved(expected: "light" | "dark", what: string) {
  await page.waitForFunction(() => window.__schemeFrames >= 2);
  const seen = await page.evaluate((want) => {
    const samples = window.__schemeSamples.splice(0, window.__schemeSamples.length);
    const total = window.__schemeFrames;
    window.__schemeFrames = 0;
    return { total, wrong: samples.filter((sample) => (sample.dark ? "dark" : "light") !== want || sample.colorScheme !== want) };
  }, expected);
  expect(seen.total, `${what}: the sampler never ran`).toBeGreaterThan(0);
  expect(seen.wrong, `${what}: ${seen.wrong.length} samples were the wrong scheme`).toEqual([]);
}

/** Forget what was sampled against the previous expectation, on either side of a deliberate change. */
async function forgetSamples() {
  await page.evaluate(() => {
    window.__schemeSamples.length = 0;
    window.__schemeFrames = 0;
  });
}

async function collapseSidebar(collapsed: boolean) {
  const sidebar = page.getByTestId("sidebar");
  if (collapsed === ((await sidebar.count()) === 0)) return;
  const toggle = collapsed
    ? sidebar.getByRole("button", { name: "Toggle sidebar" })
    : page.locator("[data-session-header]").getByRole("button", { name: "Toggle sidebar" });
  await toggle.click();
  await expect(sidebar).toHaveCount(collapsed ? 0 : 1);
}

/** What the renderer reserved, in CSS pixels. */
async function readInset(): Promise<number> {
  return page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.cssText = "position:fixed;left:0;top:0;height:1px;width:var(--titlebar-inset);visibility:hidden";
    document.body.appendChild(probe);
    const width = probe.getBoundingClientRect().width;
    probe.remove();
    return Math.round(width);
  });
}

/** Nothing interactive under the lights, the bar's first control past them, and the strip draggable. */
async function expectLeftmost(leftmost: "sidebar" | "session", bar: string) {
  await expect(page.locator("[data-shell]")).toHaveAttribute("data-leftmost", leftmost);
  await expectClear(leftmost);
  await expectFirstControlClears(bar);
  await expectDragRegion(bar);
}

/**
 * No interactive element anywhere on the page overlaps the reserved corner —
 * the whole document, because a dialog, toast or menu over the corner is the
 * same defect.
 */
async function expectClear(label: string) {
  const trespassers = await page.evaluate(([reserved, height]) => {
    const found: { label: string; x: number; y: number }[] = [];
    const selector = "button, [role=button], a[href], input, select, textarea, [contenteditable=true], [role=tab], [role=option], [role=menuitem], [data-separator]";
    for (const node of Array.from(document.querySelectorAll(selector))) {
      const rect = node.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0 || rect.right <= 0) continue;
      if (rect.top + rect.height / 2 > height) continue;
      if (rect.left < reserved) {
        found.push({ label: (node.getAttribute("aria-label") ?? node.textContent ?? node.nodeName).trim().slice(0, 40), x: Math.round(rect.left), y: Math.round(rect.top) });
      }
    }
    return found;
  }, [inset, TITLEBAR_HEIGHT] as const);
  expect(trespassers, `${label}: these controls are under the traffic lights`).toEqual([]);
}

async function expectFirstControlClears(bar: string) {
  const first = await page.evaluate((selector) => {
    const strip = document.querySelector(selector);
    if (!strip) return null;
    for (const node of Array.from(strip.querySelectorAll("button, [role=button], input"))) {
      const rect = node.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) return { x: Math.round(rect.left) };
    }
    return null;
  }, bar);
  expect(first, `${bar} has no control to check`).not.toBeNull();
  expect(first!.x, `${bar}'s first control starts inside the lights' room`).toBeGreaterThanOrEqual(inset);
}

/**
 * The strip is the window's drag handle and its controls are not. Chromium
 * subtracts a `no-drag` element's whole box, so the opt-out may be a wrapper:
 * what matters is that one is met on the way up from each control.
 */
async function expectDragRegion(bar: string) {
  const regions = await page.evaluate((selector) => {
    const strip = document.querySelector(selector);
    if (!strip) return null;
    const region = (node: DomNode) => getComputedStyle(node).getPropertyValue("-webkit-app-region").trim();
    const optedOut = (node: DomNode) => {
      for (let current: DomNode | null = node; current; current = current.parentElement) {
        if (region(current) === "no-drag") return true;
        if (current === strip) return false;
      }
      return false;
    };
    return {
      strip: region(strip),
      dragging: Array.from(strip.querySelectorAll("button")).filter((node) => !optedOut(node))
        .map((node) => (node.getAttribute("aria-label") ?? node.textContent ?? "").trim()),
    };
  }, bar);
  expect(regions, `${bar} is not in the document`).not.toBeNull();
  expect(regions!.strip, `${bar} is not a drag region`).toBe("drag");
  expect(regions!.dragging, `these controls in ${bar} drag the window instead`).toEqual([]);
}

/**
 * The corner, photographed with the reserved room drawn on it: the lights are
 * AppKit's and never appear in a screenshot of the web contents.
 */
async function shootTitlebar(name: string) {
  await page.evaluate(([reserved, height]) => {
    const marker = document.createElement("div");
    marker.id = "titlebar-marker";
    marker.style.cssText = `position:fixed;left:0;top:0;width:${reserved}px;height:${height}px;` +
      "background:rgba(255,64,64,0.28);outline:1px solid rgba(255,64,64,0.9);pointer-events:none;z-index:2147483647";
    document.body.appendChild(marker);
  }, [inset, TITLEBAR_HEIGHT] as const);
  await page.screenshot({ path: test.info().outputPath(name), animations: "disabled", clip: { x: 0, y: 0, width: 720, height: 96 } });
  await page.evaluate(() => document.getElementById("titlebar-marker")?.remove());
}
