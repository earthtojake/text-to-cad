import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test as base, type ElectronApplication, type Locator, type Page } from "@playwright/test";

/**
 * The one way the suite starts the built app.
 *
 * Every spec used to carry its own copy of this: the entry point, a
 * throwaway `--user-data-dir`, `NODE_ENV=test` and the fake agent. A launch
 * is the most expensive thing a spec does short of a CAD compile, so a spec
 * launches once and runs its tests against that one app (serially) unless a
 * relaunch is the thing under test.
 */
// `page.evaluate` bodies run in the renderer. This file is compiled with the
// node tsconfig, which has no DOM lib, so the few shapes those bodies touch are
// declared here, module-scoped.
declare const document: { querySelectorAll(selector: string): Iterable<{ getBoundingClientRect(): { x: number; width: number } }> };
declare const window: { innerWidth: number; innerHeight: number };
declare function requestAnimationFrame(callback: () => void): number;

export const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
export const repoRoot = path.resolve(appRoot, "..", "..");
export const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");
export const mod = process.platform === "darwin" ? "Meta" : "Control";

/**
 * What a failed test leaves behind.
 *
 * The suite launches Electron itself (`_electron.launch` in a `beforeAll`), so
 * Playwright's own `use: { trace }` has no page fixture to attach to and
 * records nothing useful for these specs (its `trace.zip` has no DOM snapshots).
 * Every app `launch()` starts is therefore traced here, in one chunk per test,
 * and the chunk is written out (`trace-N.zip`, with DOM snapshots and
 * screenshots) only when the test failed; a green test discards its chunk, so a
 * passing run writes nothing. No separate PNG of the windows: Playwright's own
 * `screenshot: "only-on-failure"` writes `test-failed-N.png`, and the trace holds the rest.
 * Import `test` from this file, not from `@playwright/test`, to get it.
 */
const traced = new Set<ElectronApplication>();

async function startChunks() {
  for (const app of traced) await app.context().tracing.startChunk().catch(() => traced.delete(app));
}

export const test = base.extend<{ failureEvidence: void }>({
  failureEvidence: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, use, testInfo) => {
      await startChunks();
      await use();
      const failed = testInfo.status !== testInfo.expectedStatus;
      let n = 0;
      for (const app of [...traced]) {
        n += 1;
        const context = app.context();
        await context.tracing
          .stopChunk(failed ? { path: testInfo.outputPath(`trace-${n}.zip`) } : undefined)
          .catch(() => traced.delete(app));
      }
    },
    { auto: true },
  ],
});

/**
 * Put an app this suite started itself (a spec that bundles its own main entry
 * or must control the launch) under the same failure trace as `launch()`'s:
 * call it right after `electron.launch`, and import `test` from this file.
 */
export async function traceApp(app: ElectronApplication): Promise<void> {
  await app.context().tracing.start({ screenshots: true, snapshots: true, sources: false });
  await app.context().tracing.startChunk().catch(() => undefined);
  traced.add(app);
  app.on("close", () => traced.delete(app));
}

export type Launched = { app: ElectronApplication; page: Page; lines: string[] };

export async function launch(options: {
  userData: string;
  /** Extra environment; `undefined` removes an inherited variable. */
  env?: Record<string, string | undefined>;
  /** Arguments for the fake agent (`--load-delay 1200`, `--mode-option`). */
  fakeArgs?: string;
}): Promise<Launched> {
  const env: Record<string, string> = {};
  const merged = {
    ...process.env,
    NODE_ENV: "test",
    TEXT_TO_CAD_FAKE_AGENT: fakeAgent,
    ...(options.fakeArgs ? { TEXT_TO_CAD_FAKE_AGENT_ARGS: options.fakeArgs } : {}),
    ...options.env,
  };
  for (const [key, value] of Object.entries(merged)) {
    if (typeof value === "string") env[key] = value;
  }
  const app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${options.userData}`],
    env,
  });
  // Main narrates what it starts on stdout (`[viewer] started …`, `[acp] load …`);
  // specs that assert on that narration read it from here.
  const lines: string[] = [];
  app.process().stdout?.on("data", (chunk: Buffer) => lines.push(...String(chunk).split("\n")));
  app.process().stderr?.on("data", (chunk: Buffer) => lines.push(...String(chunk).split("\n")));
  await traceApp(app);
  const page = await app.firstWindow();
  page.on("pageerror", (error) => console.error(`[renderer] ${error.message}`));
  await page.waitForLoadState("domcontentloaded");
  return { app, page, lines };
}

/** What main's e2e door answers with: the chosen folder, as `projects.add` would. */
export type ChosenDirectory = { id: string; name: string; path: string; createdAt: number };

/**
 * Choose a folder the way the native chooser does — main resolves it, selects
 * it and broadcasts `ui.directorySelected` — without the chooser, which
 * Playwright cannot drive. No renderer channel takes a path, so this goes in
 * through main: the `NODE_ENV=test` door `installE2eDoor` puts on main's
 * global (src/main/test-door.ts).
 */
export async function chooseDirectory(app: ElectronApplication, directory: string): Promise<ChosenDirectory> {
  return app.evaluate(
    (_electron, chosen) =>
      (globalThis as unknown as { __textToCadE2E: { choose(directory: string): Promise<ChosenDirectory> } }).__textToCadE2E.choose(chosen),
    directory,
  );
}

/** A scratch directory, realpath'd: Electron resolves paths, and macOS's /var is a link. */
export function scratch(prefix: string): string {
  return fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), `text-to-cad-${prefix}-`)));
}

/**
 * Drag a separator `by` pixels, and wait for the pane it moves to settle
 * rather than for a fixed time: the width is read until two frames agree.
 */
export async function dragSeparator(page: Page, separator: Locator, by: number) {
  const box = (await separator.boundingBox())!;
  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + box.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + by, y, { steps: 10 });
  await page.mouse.up();
  await settledLayout(page);
}

/** Two consecutive animation frames with the same pane geometry. */
export async function settledLayout(page: Page) {
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          new Promise<boolean>((resolve) => {
            const read = () =>
              JSON.stringify(
                [...document.querySelectorAll("[data-panel], [data-testid=sidebar], [data-testid=explorer]")].map((node) => {
                  const rect = node.getBoundingClientRect();
                  return [rect.x, rect.width];
                }),
              );
            const first = read();
            requestAnimationFrame(() => requestAnimationFrame(() => resolve(read() === first)));
          }),
      ),
    )
    .toBe(true);
}

/** Resize the window and wait until the renderer has laid out at that size. */
export async function setContentSize(app: ElectronApplication, page: Page, width: number, height: number) {
  await app.evaluate(({ BrowserWindow }, size) => {
    BrowserWindow.getAllWindows()[0]!.setContentSize(size.width, size.height);
  }, { width, height });
  await expect.poll(() => page.evaluate(() => [window.innerWidth, window.innerHeight])).toEqual([width, height]);
  await settledLayout(page);
}

/**
 * Wait until a terminal tab's shell is at a prompt.
 *
 * The terminal is a login shell, so it runs the person's profile first, in
 * bursts with gaps; typing into a gap gets the keystrokes echoed twice. The
 * signal is a last line ending in a prompt character, or — for a prompt
 * shaped like nothing in particular — the screen unchanged for three reads a
 * second apart.
 */
export async function settleTerminal(page: Page) {
  let previous = "";
  let quietReads = 0;
  await expect
    .poll(
      async () => {
        const current = await page.locator(".xterm-rows").innerText();
        const lines = current.split("\n").filter((line) => line.trim() !== "");
        quietReads = current !== "" && current === previous ? quietReads + 1 : 0;
        previous = current;
        // Three seconds of silence for a prompt with no telltale character: a
        // slow `nvm` pauses for well over a second in the middle of a profile.
        return /[$%>#]\s*$/.test(lines.at(-1) ?? "") || quietReads >= 3;
      },
      { intervals: [100, 250, 1_000], timeout: 30_000 },
    )
    .toBe(true);
}

/** `+` is a menu of the tab kinds; a closing Radix menu can swallow the next click, so wait it out. */
export async function newTab(page: Page, label: string) {
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: label }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
}

/** Set the theme through the settings and wait for the document to wear it. */
export async function setTheme(page: Page, theme: "dark" | "light") {
  await page.evaluate((value) => (window as unknown as { textToCad: { settings: { set(patch: { theme: string }): Promise<unknown> } } }).textToCad.settings.set({ theme: value }), theme);
  await expect(page.locator("html")).toHaveClass(theme === "dark" ? /\bdark\b/ : /^(?!.*\bdark\b).*$/);
}

/** Screenshot with transitions finished, into the test's output directory. */
export async function shoot(target: Page | Locator, name: string, testInfo: { outputPath(name: string): string }) {
  await target.screenshot({ path: testInfo.outputPath(name), animations: "disabled" });
}
