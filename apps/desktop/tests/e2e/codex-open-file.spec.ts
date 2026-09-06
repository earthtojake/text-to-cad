import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

/**
 * The gate the whole app exists for (plan §13, P5): a real agent, in a real
 * session, shows the person a file by calling the Hardcore MCP server's
 * `open_file` — and the explorer opens it in the viewer.
 *
 * Real Codex, on purpose. The fake agent could call the tool, but the point
 * is that the adapter forwards our stdio server from `session/new`, Codex
 * spawns it with the environment we gave, the bridge accepts the token, and
 * the renderer opens the tab. Every one of those is a seam a fake would paper
 * over. Skipped when there is no signed-in `codex` on the machine, so the
 * suite is green on a runner without one.
 *
 * The project is a scratch directory with one STEP copied in, never this
 * repository: an agent with a shell must not be pointed at a checkout.
 */

declare const window: {
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string; name: string }> };
    settings: { set(patch: Record<string, unknown>): Promise<unknown> };
    sessions: {
      create(input: { projectId: string; agentId: string; cwd: string; gitMode: "none" }): Promise<{ id: string }>;
      setApprovalMode(input: { id: string; mode: "approve-for-me" }): Promise<void>;
      prompt(input: { id: string; content: Array<{ type: "text"; text: string }> }): Promise<{ stopReason: string }>;
      state(input: { id: string }): Promise<{ turns: Array<{ role: string; parts: Array<Record<string, unknown>> }> } | null>;
      close(input: { id: string }): Promise<void>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const repoRoot = path.resolve(appRoot, "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");
const STEP_SOURCE = path.join(repoRoot, "models", "examples", "imported", "import-smoke.step");

const CAD_PYTHON =
  process.env.CAD_DESKTOP_PYTHON ??
  [path.join(repoRoot, ".venv", "bin", "python"), path.resolve(repoRoot, "..", "..", "..", ".venv", "bin", "python")].find(
    (candidate) => fs.existsSync(candidate),
  ) ??
  null;

function codexSignedIn(): boolean {
  try {
    execFileSync("codex", ["login", "status"], { stdio: "ignore", timeout: 15_000 });
    return true;
  } catch {
    return false;
  }
}

let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;
let sessionId: string | null = null;

test.beforeAll(async () => {
  // A real model turn costs credits; opt in the way codex.spec.ts does, so a
  // default run never spends them (the build once ran into Codex's usage limit).
  test.skip(process.env.HARDCORE_E2E_CODEX !== "1", "set HARDCORE_E2E_CODEX=1 to run the real Codex session");
  test.skip(!codexSignedIn(), "codex is not installed or not signed in");
  test.skip(!fs.existsSync(STEP_SOURCE) || fs.statSync(STEP_SOURCE).size < 1000, "the STEP fixture is an LFS pointer; git lfs checkout it");

  project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-codex-project-"));
  fs.mkdirSync(path.join(project, "STEP"));
  fs.copyFileSync(STEP_SOURCE, path.join(project, "STEP", "part.step"));
  fs.writeFileSync(path.join(project, "README.md"), "# Scratch\n\nOne STEP under STEP/.\n");

  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-codex-e2e-"));
  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test", ...(CAD_PYTHON ? { CAD_DESKTOP_PYTHON: CAD_PYTHON } : {}) },
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
});

test.afterAll(async () => {
  // See explorer.spec.ts: quitting is slow and variable, and not this test's business.
  test.setTimeout(300_000);
  if (sessionId) {
    await page.evaluate((id) => window.hardcore.sessions.close({ id }), sessionId).catch(() => {});
  }
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
  fs.rmSync(project, { recursive: true, force: true });
});

test("a Codex session opens a STEP in the explorer through open_file", async () => {
  test.setTimeout(300_000);

  const added = await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), project);
  await expect(page.getByText(path.basename(project)).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeEnabled();

  const session = await page.evaluate(
    ({ projectId, cwd }) => window.hardcore.sessions.create({ projectId, agentId: "codex", cwd, gitMode: "none" }),
    { projectId: added.id, cwd: project },
  );
  sessionId = session.id;
  await page.evaluate((id) => window.hardcore.sessions.setApprovalMode({ id, mode: "approve-for-me" }), session.id);

  // The prompt names the tool, so the run is about the plumbing rather than
  // about whether the model chooses to look at a file.
  const prompt = "Use the open_file tool to show me STEP/part.step, then reply with exactly: opened";
  const outcome = await page.evaluate(
    ({ id, text }) => window.hardcore.sessions.prompt({ id, content: [{ type: "text", text }] }),
    { id: session.id, text: prompt },
  );
  expect(outcome.stopReason).toBe("end_turn");

  // The explorer opened it: a tab named after the file, rendered by the viewer.
  await expect(page.getByRole("tab", { name: /part\.step/ })).toBeVisible({ timeout: 30_000 });
  if (CAD_PYTHON) {
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 90_000 });
    await expect(page.getByRole("tab", { name: "Tree" })).toBeVisible({ timeout: 90_000 });
  }

  // And the session recorded the tool call, with the server's answer in it.
  const state = await page.evaluate((id) => window.hardcore.sessions.state({ id }), session.id);
  const parts = state?.turns.flatMap((turn) => turn.parts) ?? [];
  const toolCalls = parts.filter((part) => part.type === "tool_call") as Array<{ title: string; name: string | null; status: string; output: unknown }>;
  const openFile = toolCalls.find((call) => /open_file/.test(`${call.title} ${call.name ?? ""}`));
  expect(openFile, JSON.stringify(toolCalls.map((call) => ({ title: call.title, name: call.name, status: call.status })))).toBeDefined();
  expect(openFile!.status).toBe("completed");

  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(screenshots, "codex-open-file.png"), animations: "disabled" });
});
