import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, type ElectronApplication, type Locator, type Page } from "@playwright/test";

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
  const page = await app.firstWindow();
  page.on("pageerror", (error) => console.error(`[renderer] ${error.message}`));
  await page.waitForLoadState("domcontentloaded");
  return { app, page, lines };
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

/** Screenshot with transitions finished, into the test's output directory. */
export async function shoot(target: Page | Locator, name: string, testInfo: { outputPath(name: string): string }) {
  await target.screenshot({ path: testInfo.outputPath(name), animations: "disabled" });
}
