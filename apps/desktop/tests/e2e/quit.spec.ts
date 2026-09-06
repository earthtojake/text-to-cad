import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type Page } from "@playwright/test";

/**
 * Quitting has a budget: two seconds from `app.quit()` to the process being
 * gone, with a real repository watched, a shell running, a session mid-turn
 * and the CAD viewer up — and nothing of ours left behind.
 *
 * P5 measured this at ten seconds to minutes. Two causes, both fixed in
 * main: a child with a pipe to this process held the exit until its own
 * timeout (a cadgen version probe, sixty seconds — `src/main/children.ts`),
 * and Chromium's shutdown after WebGL takes tens of seconds on this macOS
 * (`src/main/quit-deadline.ts`).
 *
 * The clock stops when the kernel says the process is gone (`kill -0`), not
 * when Playwright's process object emits `exit` — that event trails the
 * real exit by four seconds here, which is Playwright's business, not the
 * app's.
 */
declare const window: {
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string }> };
    settings: { set(patch: Record<string, unknown>): Promise<unknown> };
    sessions: {
      create(request: { projectId: string; agentId: string; gitMode: string }): Promise<{ id: string }>;
      prompt(request: { id: string; content: { type: "text"; text: string }[] }): Promise<{ stopReason: string }>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const repoRoot = path.resolve(appRoot, "..", "..");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");
const STEP = "models/examples/imported/import-smoke.step";

const CAD_PYTHON =
  process.env.CAD_DESKTOP_PYTHON ??
  [path.join(repoRoot, ".venv", "bin", "python"), path.resolve(repoRoot, "..", "..", "..", ".venv", "bin", "python")].find((candidate) =>
    fs.existsSync(candidate),
  ) ??
  null;

/** The whole budget, from `app.quit()` to the process being gone. */
const QUIT_BUDGET_MS = 2_000;

test("the app quits in under two seconds with everything running, leaving no child behind", async () => {
  test.setTimeout(240_000);
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-quit-e2e-"));
  const app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: fakeAgent },
  });
  // Main's own log: how long its teardown took.
  app.process().stdout?.on("data", (chunk: Buffer) => {
    for (const line of chunk.toString().split("\n")) {
      if (line.includes("[quit]")) {
        console.info(line);
      }
    }
  });
  const page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");

  // The watcher over this repository.
  const project = await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), repoRoot);
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeEnabled();

  // A shell.
  await newTab(page, "Terminal");
  await expect(page.locator(".xterm-screen")).toBeVisible();

  // A live adapter, mid-turn: the fake's `slow` prompt runs until it is stopped.
  const session = await page.evaluate(
    (projectId) => window.hardcore.sessions.create({ projectId, agentId: "codex", gitMode: "none" }),
    project.id,
  );
  void page.evaluate((id) => window.hardcore.sessions.prompt({ id, content: [{ type: "text", text: "slow" }] }), session.id).catch(() => {});

  // The CAD viewer child and a WebGL context, when an interpreter is available.
  if (CAD_PYTHON) {
    await page.evaluate((python) => window.hardcore.settings.set({ cadPythonOverride: python }), CAD_PYTHON);
    await newTab(page, "File");
    const filter = page.getByLabel("Filter files");
    await filter.fill(STEP);
    await page.getByRole("option", { name: STEP, exact: false }).first().click();
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 90_000 });
  }

  const pid = app.process().pid!;
  const tree = descendants(pid);
  expect(tree.length, "the app should have children to end").toBeGreaterThan(3);
  const exited = new Promise<void>((resolve) => app.process().once("exit", () => resolve()));

  const started = Date.now();
  // The real thing: the menu's Quit, Cmd+Q, the dock — all `app.quit()`.
  await app.evaluate(({ app: electronApp }) => electronApp.quit()).catch(() => {
    // The connection drops before the evaluate resolves; the exit is what counts.
  });
  await expect.poll(() => alive(pid), { timeout: 60_000, intervals: [25] }).toBe(false);
  const elapsed = Date.now() - started;
  console.info(`[quit] process gone after ${elapsed}ms`);

  // Nothing outlives the app: not the viewer, the adapter, the shell or the
  // MCP server, and not Chromium's helpers either (the deadline kills those
  // too — a utility process left to notice on its own took over thirty
  // seconds). The one descendant meant to survive is cadgen's build daemon,
  // the viewer's grandchild, which outlives it by design with an idle
  // timeout of its own.
  const ours = (entry: { command: string }) => !entry.command.includes("cadgen.daemon");
  await expect.poll(() => tree.filter((entry) => ours(entry) && alive(entry.pid)).map((entry) => entry.command), { timeout: 5_000 }).toEqual([]);
  console.info(`[quit] everything gone after ${Date.now() - started}ms`);
  expect(elapsed).toBeLessThan(QUIT_BUDGET_MS);

  await exited;
  fs.rmSync(userData, { recursive: true, force: true });
});

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/** Every descendant of `pid`, with a short name for the failure message. */
function descendants(pid: number): { pid: number; command: string }[] {
  const out: { pid: number; command: string }[] = [];
  let children: string[];
  try {
    children = execFileSync("pgrep", ["-P", String(pid)], { encoding: "utf8" }).trim().split(/\s+/).filter(Boolean);
  } catch {
    children = [];
  }
  for (const child of children) {
    let command = "?";
    try {
      const full = execFileSync("ps", ["-o", "command=", "-p", child], { encoding: "utf8" }).trim();
      const type = /--type=([\w-]+)/.exec(full)?.[1];
      command = type ? `helper:${type}` : `${full.split(" ")[0]?.split("/").pop() ?? "?"} ${full.replace(/^\S+/, "").slice(0, 50)}`;
    } catch {
      /* gone already */
    }
    out.push({ pid: Number(child), command });
    out.push(...descendants(Number(child)));
  }
  return out;
}

/**
 * Open a tab of one kind. `+` is a menu of the four kinds now, so every open
 * is two clicks — which is also the only way to reach a review or a terminal.
 */
async function newTab(page: Page, label: "File" | "Review" | "Browser" | "Terminal") {
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: label }).click();
}
