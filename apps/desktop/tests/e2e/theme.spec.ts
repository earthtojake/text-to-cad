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
 * The colour scheme, end to end: who is allowed to write it, and whether it
 * ever moves on its own.
 *
 * The report this file exists for: "the light/dark mode seems to randomly
 * change when i start using the desktop app for no apparent reason. it should
 * be set to system by default, which is dark mode for my desktop." Two things
 * could do that and both are checked here.
 *
 * The one that was real: the theme is a settings row in main's sqlite, so the
 * renderer could only apply it from React's first passive effect — one paint
 * after `ready-to-show` put the window on screen. Every launch, every reload
 * and every dev-server hot reload started light and then flipped. So this
 * suite does not assert "it ends up dark"; it SAMPLES the document ten times a
 * second and asserts the class never once disagreed with the resolved
 * preference, boot and reload included.
 *
 * The one that was not, and is now impossible: the embedded CAD surface has a
 * colour-scheme preference of its own and used to be able to write `<html>`
 * with it. In this app only the app writes the document
 * (`src/renderer/hooks/use-theme.ts`); the surface renders from the
 * `colorScheme` prop it is handed and may only read
 * (`packages/ui/docs/cad-renderer.md`). Its signature is the two
 * attributes only IT writes — `data-theme` and `data-theme-preference` — so
 * their absence after a file, a theme panel, a slider and a preset is the
 * assertion.
 *
 * `emulateMedia` is what stands in for "dark mode for my desktop": the suite
 * has to pass on a machine and a CI runner whatever their own appearance is.
 */

// The e2e suite is typechecked as node (tsconfig.node.json), which has no DOM
// lib: what runs inside `page.evaluate` is declared here, as the explorer
// suite declares its own `window`.
declare const document: {
  documentElement: { getAttribute(name: string): string | null };
};

declare const window: {
  matchMedia(query: string): { matches: boolean };
  localStorage: { getItem(key: string): string | null };
  __schemeSamples: { dark: boolean; colorScheme: string; prefersDark: boolean }[];
  __schemeFrames: number;
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string; name: string }> };
    settings: {
      get(): Promise<{ theme: string }>;
      set(patch: { theme?: string }): Promise<unknown>;
    };
    runtime: { status(): Promise<{ state: string }> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const repoRoot = path.resolve(appRoot, "..", "..");
const projectName = path.basename(repoRoot);
const STEP = "models/examples/imported/import-smoke.step";

/**
 * The document's scheme, sampled on every animation frame — every paint —
 * from the first line of the page.
 *
 * Installed as an init script so it survives a reload and is running before
 * the renderer's own modules: a flash that lasts one frame is a flash a person
 * sees, and `expect(html).toHaveClass()` after the fact cannot see it at all.
 *
 * Two details earn their comments. `readyState === "loading"` is skipped
 * because there is no `<html>` at document-creation time and no state it
 * could be in that would be right — the earliest honest checkpoint is
 * "interactive", by which the deferred module script has run and
 * `applyCachedTheme` with it. And only CHANGES are kept, so a minute of
 * frames is a handful of entries rather than four thousand; `total` is the
 * count of frames actually judged.
 */
const SAMPLER = `
window.__schemeSamples = [];
window.__schemeFrames = 0;
const sample = () => {
  requestAnimationFrame(sample);
  if (document.readyState === "loading" || !document.documentElement) {
    return;
  }
  const now = {
    dark: document.documentElement.classList.contains("dark"),
    colorScheme: document.documentElement.style.colorScheme,
    prefersDark: window.matchMedia("(prefers-color-scheme: dark)").matches,
  };
  window.__schemeFrames += 1;
  const last = window.__schemeSamples[window.__schemeSamples.length - 1];
  if (
    !last
    || last.dark !== now.dark
    || last.colorScheme !== now.colorScheme
    || last.prefersDark !== now.prefersDark
  ) {
    window.__schemeSamples.push(now);
  }
};
sample();
`;

/** The two attributes only the embedded surface ever writes. */
async function surfaceWroteTheDocument(target: Page): Promise<Record<string, string | null>> {
  return target.evaluate(() => ({
    theme: document.documentElement.getAttribute("data-theme"),
    preference: document.documentElement.getAttribute("data-theme-preference"),
  }));
}

/**
 * Every distinct state the document has been in since the last drain that
 * disagreed with the theme the app resolved. `expected` is null for "whatever
 * the OS is asking for", which is what `system` means.
 */
async function drainDisagreements(target: Page, expected: "light" | "dark" | null) {
  return target.evaluate((want) => {
    const samples = window.__schemeSamples.splice(0, window.__schemeSamples.length);
    const total = window.__schemeFrames;
    window.__schemeFrames = 0;
    const wanted = (sample: { prefersDark: boolean }) => want ?? (sample.prefersDark ? "dark" : "light");
    return {
      total,
      wrong: samples.filter(
        (sample) => (sample.dark ? "dark" : "light") !== wanted(sample) || sample.colorScheme !== wanted(sample),
      ),
    };
  }, expected);
}

/**
 * No sample since the last drain was the wrong colour.
 *
 * Wait for actual sampled frames: a fixed delay need not contain a frame on
 * a busy CI runner. Keep every sample while waiting, including any wrong one.
 */
async function expectNeverMoved(target: Page, expected: "light" | "dark" | null, what: string) {
  await target.waitForFunction(() => window.__schemeFrames >= 2);
  const seen = await drainDisagreements(target, expected);
  expect(seen.total, `${what}: the sampler never ran`).toBeGreaterThan(0);
  expect(seen.wrong, `${what}: ${seen.wrong.length} of ${seen.total} samples were the wrong scheme`).toEqual([]);
}

/**
 * Forget everything sampled so far.
 *
 * Called on either side of a deliberate change — the OS moving, the
 * preference being set — because those frames were right against the old
 * expectation and are being replaced by a new one. Never called in the middle
 * of a step: that would be the assertion looking away.
 */
async function forgetSamples(target: Page) {
  await target.evaluate(() => {
    window.__schemeSamples.length = 0;
    window.__schemeFrames = 0;
  });
}

/** The window's own ground, as Electron reports it: `#rrggbb`, lower case. */
async function windowBackground(instance: ElectronApplication): Promise<string> {
  const colour = await instance.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()[0]?.getBackgroundColor(),
  );
  return String(colour || "").toLowerCase();
}

let app: ElectronApplication;
let page: Page;
let userData: string;
let cadReady = false;

/**
 * A user-data directory that OUTLIVES the first app: the restart test opens a
 * second app on it, which is the only way to check what the very first frame
 * of a launch looks like.
 */
test.beforeAll(async () => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-theme-e2e-"));
  app = await launch();
  await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), repoRoot);
  await expect(page.getByText(projectName).first()).toBeVisible();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  await page.getByRole("button", { name: "Toggle explorer" }).click();
  await expect(page.getByTestId("explorer")).toBeVisible();
});

test.afterAll(async () => {
  test.setTimeout(300_000);
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
});

/**
 * The app, on `userData`, with the OS in dark and the sampler installed.
 *
 * The sampler and `emulateMedia` are both per-page and both have to be in
 * place before the load whose first paint is being judged, so the window is
 * reloaded once after they are set. That reload is also the interesting
 * case — it is what a dev-server hot reload does.
 */
async function launch(): Promise<ElectronApplication> {
  // Without `CAD_DESKTOP_PYTHON`, as the explorer suite does: the app resolves
  // its own runtime (the bundle beside it, or the checkout's `.venv`).
  const { CAD_DESKTOP_PYTHON: _unset, ...inherited } = process.env;
  const started = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...inherited, NODE_ENV: "test" },
  });
  page = await started.firstWindow();
  await page.addInitScript(SAMPLER);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
  return started;
}

test.describe.configure({ mode: "serial" });

test("comes up dark on an OS in dark, with no light frame and nothing set", async () => {
  // The default, unwritten: nothing in this suite has touched the setting.
  expect((await page.evaluate(() => window.hardcore.settings.get())).theme).toBe("system");
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  expect(await page.evaluate(() => window.matchMedia("(prefers-color-scheme: dark)").matches)).toBe(true);
  // Including the load itself. This is the assertion that fails without the
  // pre-paint applier in `src/renderer/main.tsx`.
  await expectNeverMoved(page, "dark", "boot");
  // And the cache that made the first frame right, written from what main
  // stored rather than from the fallback the renderer guessed.
  await expect
    .poll(() => page.evaluate(() => window.localStorage.getItem("hardcore.theme")))
    .toBe("system");
});

test("stays dark through a STEP file, its theme panel, a slider and a preset", async () => {
  test.setTimeout(300_000);
  const status = await page.evaluate(() => window.hardcore.runtime.status());
  cadReady = status.state === "ready";
  test.skip(!cadReady, "no CAD runtime on this machine: no bundle under resources/runtime and no .venv");

  await newTab("File");
  await page.getByLabel("Filter files").fill(STEP);
  await page.getByRole("option", { name: STEP, exact: false }).first().click();
  await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("tab", { name: "Geometry" })).toBeVisible({ timeout: 120_000 });
  await expectNeverMoved(page, "dark", "the CAD surface mounting");
  /*
    Mounting the surface wrote NEITHER of the two attributes it writes when it
    owns a document. It has a stored preference of its own — the standalone
    viewer's `cad-viewer:color-scheme`, which defaults to the OS — and a write
    from here is what turned the whole app light on a mount, on a storage
    event from a second window, and on every theme edit.
  */
  expect(await surfaceWroteTheDocument(page)).toEqual({ theme: null, preference: null });

  // The theme panel: the viewer's own scene settings, drawn in the tab's
  // panel column. Everything in it paints the SCENE and nothing around it.
  const themePanel = page.locator("header [data-file-panel='cad-theme']");
  await themePanel.click();
  await expect(themePanel).toHaveAttribute("aria-pressed", "true");
  await expectNeverMoved(page, "dark", "opening the theme panel");

  // A slider — the report's "when i click a slide". A theme setting write goes
  // to the viewer's own storage, which used to be read back as a colour scheme.
  const sliders = page.locator("[data-file-panel-container] [role=slider]");
  const dragged = Math.min(await sliders.count(), 4);
  expect(dragged, "the theme panel has sliders to drag").toBeGreaterThan(0);
  for (let index = 0; index < dragged; index += 1) {
    const box = await sliders.nth(index).boundingBox();
    if (!box) continue;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 32, box.y + box.height / 2, { steps: 6 });
    await page.mouse.up();
  }
  await expectNeverMoved(page, "dark", "dragging the theme panel's sliders");

  /*
    And a preset. Cinematic is the case that matters: a genuinely dark stage,
    which the surface once read the luminance of and wrote to the document —
    a theme that decided what the app looked like. A dark studio inside a
    light window is a legal picture (the user's rule), so the app's scheme
    must not move at all.
  */
  const preset = page.locator("[data-file-panel-container]").getByRole("combobox").first();
  await preset.click();
  await page.getByRole("option", { name: "Cinematic" }).click();
  await expect(preset).toContainText("Cinematic");
  await expect
    .poll(() => page.evaluate(() => window.localStorage.getItem("cad-viewer:theme")))
    .toContain("cinematic");
  await expectNeverMoved(page, "dark", "picking the Cinematic preset");
  expect(await surfaceWroteTheDocument(page)).toEqual({ theme: null, preference: null });

  // Back to System — the one preset that follows the app — which is the
  // other direction of the same rule.
  await preset.click();
  await page.getByRole("option", { name: "System" }).click();
  await expect(preset).toContainText("System");
  await expectNeverMoved(page, "dark", "putting the preset back to System");
});

test("stays dark across tabs, routes, a project and a reload", async () => {
  test.setTimeout(300_000);
  // A second tab, and back: the CAD surface unmounts and remounts, which is
  // where a document write on mount would show.
  await newTab("File");
  await page.getByLabel("Filter files").fill("AGENTS.md");
  await page.getByRole("option", { name: "AGENTS.md", exact: false }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: "AGENTS.md" })).toBeVisible();
  await expectNeverMoved(page, "dark", "a second file tab");

  if (cadReady) {
    await page.getByRole("tab", { name: /import-smoke\.step/ }).click();
    await expect(page.locator("[data-cad-surface]")).toBeVisible();
    await page.getByRole("tab", { name: /AGENTS\.md/ }).click();
    await expectNeverMoved(page, "dark", "switching between the two tabs");
  }

  /*
    Settings — the app's other full-window route, which replaces the whole
    tree — and the Appearance page the preference is set from, opened and
    closed without touching it. A route swap is the biggest re-render this app
    has, and `<html>` is above both routes.
  */
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "General" })).toBeVisible();
  await page.getByRole("button", { name: "Appearance", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Appearance" })).toBeVisible();
  // System is the pressed card, which is what the setting says and is the
  // first place a person would look after reading this report.
  await expect(page.getByRole("button", { name: "System", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expectNeverMoved(page, "dark", "Settings and its Appearance page");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("explorer")).toBeVisible();
  await expectNeverMoved(page, "dark", "closing Settings");

  // A reload: what a dev-server hot reload does, and the case the pre-paint
  // applier is for. The sampler is an init script, so it is running for the
  // first frame of the new document.
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  await expectNeverMoved(page, "dark", "a reload");
  expect((await page.evaluate(() => window.hardcore.settings.get())).theme).toBe("system");
});

test("follows the OS while it is System, and stops when it is not", async () => {
  // The OS moving under a running app. `system` is resolved live, never read
  // once at boot.
  await forgetSamples(page);
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
  await forgetSamples(page);
  await expectNeverMoved(page, "light", "the OS switching to light");

  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await forgetSamples(page);
  await expectNeverMoved(page, "dark", "the OS switching back to dark");
  // ...and the setting was never written by any of it: `system` is a
  // preference, not a snapshot of the OS.
  expect((await page.evaluate(() => window.hardcore.settings.get())).theme).toBe("system");

  // A chosen theme detaches from the OS in both directions.
  await page.evaluate(() => window.hardcore.settings.set({ theme: "light" }));
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
  await forgetSamples(page);
  await expectNeverMoved(page, "light", "Light chosen under an OS in dark");
  await expect
    .poll(() => page.evaluate(() => window.localStorage.getItem("hardcore.theme")))
    .toBe("light");
});

test("paints the stored theme on the first frame of a restart", async () => {
  test.setTimeout(300_000);
  /*
    The previous test left the preference on Light with the OS in dark, which
    is the sharpest version of this: a restart that reads the setting over IPC
    and applies it in an effect shows a DARK window first (the OS's answer for
    `system`, and main's `backgroundColor`) and then goes light.

    Both halves are checked — the window's own ground, which main paints from
    the same row, and the document, from the first sample of the new page.
  */
  await app.close();
  app = await launch();
  expect(await windowBackground(app), "the empty frame is the light ground").toBe("#ffffff");
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  await expectNeverMoved(page, "light", "a restart on a stored Light");

  // And back to System, which is what the app ships with.
  await page.evaluate(() => window.hardcore.settings.set({ theme: "system" }));
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await forgetSamples(page);
  await expectNeverMoved(page, "dark", "System restored");
  await app.close();
  app = await launch();
  // System with the machine's own appearance behind it: main resolves it
  // through `nativeTheme`, which is the same answer the page's
  // `prefers-color-scheme` gives before Playwright emulates anything.
  expect(await windowBackground(app)).toBe(
    (await app.evaluate(({ nativeTheme }) => nativeTheme.shouldUseDarkColors)) ? "#0a0a0a" : "#ffffff",
  );
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  await expectNeverMoved(page, null, "a restart on System");
  expect((await page.evaluate(() => window.hardcore.settings.get())).theme).toBe("system");
});

async function newTab(label: "File" | "Review" | "Browser" | "Terminal") {
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: label }).click();
}
