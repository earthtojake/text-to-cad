import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

/**
 * The explorer in a worktree session (plan §9).
 *
 * A session in `worktree` mode works in `~/.hardcore/worktrees/<project>/
 * <slug>`, outside the project directory, and everything the explorer shows
 * for it has to come from there: the file an agent's `open_file` names, the
 * tree beside it, the terminal's cwd, the CAD viewer. The root is the
 * concept that carries this (`ExplorerRoot` in `src/shared/types.ts`) — the
 * strip follows the active session's root, every tab keeps its own.
 *
 * The agent is `tests/fake-agent`, which on the word "open" spawns the
 * Hardcore MCP server `session/new` carried and calls its `open_file` — so
 * the path is the real one: adapter environment, stdio server, bridge
 * token, main's root resolution, the renderer's stores.
 */

declare const window: {
  hardcore: {
    projects: { addPath(request: { path: string }): Promise<{ id: string; name: string }> };
    settings: { set(patch: Record<string, unknown>): Promise<unknown> };
    sessions: {
      create(request: {
        projectId: string;
        agentId: string;
        gitMode: string;
        name?: string;
      }): Promise<{ id: string; cwd: string; branch?: string; worktreePath?: string }>;
      prompt(request: { id: string; content: { type: "text"; text: string }[] }): Promise<{ stopReason: string }>;
      state(input: { id: string }): Promise<{ turns: Array<{ role: string; parts: Array<Record<string, unknown>> }> } | null>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

const gitEnv = {
  ...process.env,
  GIT_AUTHOR_NAME: "Hardcore Tests",
  GIT_AUTHOR_EMAIL: "tests@example.invalid",
  GIT_COMMITTER_NAME: "Hardcore Tests",
  GIT_COMMITTER_EMAIL: "tests@example.invalid",
};

let app: ElectronApplication;
let page: Page;
let base: string;
let repo: string;
let worktreeRoot: string;
let projectId: string;
const projectName = "worktree-fixture";

test.beforeAll(async () => {
  base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-worktree-e2e-")));
  repo = path.join(base, projectName);
  worktreeRoot = path.join(base, "worktrees");
  fs.mkdirSync(repo, { recursive: true });

  const git = (...args: string[]) => execFileSync("git", args, { cwd: repo, stdio: "ignore", env: gitEnv });
  git("init", "--quiet", "--initial-branch=main");
  fs.writeFileSync(path.join(repo, "tracked.txt"), "one\ntwo\nthree\n");
  fs.writeFileSync(path.join(repo, "README.md"), "# Fixture\n");
  git("add", "-A");
  git("commit", "--quiet", "-m", "the checkout");

  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${path.join(base, "user-data")}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: fakeAgent },
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate((root) => window.hardcore.settings.set({ theme: "dark", worktreeRoot: root }), worktreeRoot);

  const project = await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), repo);
  projectId = project.id;
  await expect(page.getByText(projectName).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeEnabled();
});

test.afterAll(async () => {
  test.setTimeout(300_000);
  await app?.close();
  fs.rmSync(base, { recursive: true, force: true });
});

test("an agent in a worktree opens the file it wrote there, and the explorer roots at the worktree", async () => {
  test.setTimeout(120_000);

  const session = await page.evaluate(
    (id) => window.hardcore.sessions.create({ projectId: id, agentId: "claude-code", gitMode: "worktree", name: "Model the wrist" }),
    projectId,
  );
  const worktree = path.join(worktreeRoot, projectName, "model-the-wrist");
  expect(session.worktreePath).toBe(worktree);

  // The thread is selected the way a person selects it, so the explorer's
  // root follows it (the strip switches roots with the session).
  await page.locator(`[data-session-row="${session.id}"]`).click();
  await expect(page.locator("[data-session-view]")).toBeVisible();

  // The fake agent writes `hello.txt` into the worktree (fs/write_text_file
  // takes an absolute path, as ACP's does) and then calls `open_file` on the
  // *relative* name through the MCP server, which resolves it against the
  // session's cwd. The file exists only in the worktree.
  const outcome = await page.evaluate(
    ({ id, text }) => window.hardcore.sessions.prompt({ id, content: [{ type: "text", text }] }),
    { id: session.id, text: `write ${path.join(worktree, "hello.txt")} then open hello.txt` },
  );
  expect(outcome.stopReason).toBe("end_turn");
  expect(fs.existsSync(path.join(worktree, "hello.txt"))).toBe(true);
  expect(fs.existsSync(path.join(repo, "hello.txt"))).toBe(false);

  // The tool call completed — the bridge accepted the path, which is outside
  // the project directory and inside the session's worktree.
  const state = await page.evaluate((id) => window.hardcore.sessions.state({ id }), session.id);
  const parts = state?.turns.flatMap((turn) => turn.parts) ?? [];
  const openFile = parts.find((part) => part.type === "tool_call" && /open_file/.test(String(part.title))) as
    | { status: string; output: unknown }
    | undefined;
  expect(openFile, JSON.stringify(parts.map((part) => [part.type, part.title, part.status]))).toBeDefined();
  expect(openFile!.status, JSON.stringify(openFile!.output)).toBe("completed");

  // And the explorer opened it: a tab named after the file, the worktree in
  // the breadcrumb, the file's own bytes, and the worktree's tree beside it.
  await expect(page.getByRole("tab", { name: /hello\.txt/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("[data-crumb=worktree]")).toContainText("model-the-wrist");
  await expect(page.locator("[data-crumb=worktree]")).toHaveAttribute("title", worktree);
  await expect(page.locator(".monaco-editor").first()).toContainText("hello", { timeout: 15_000 });
  await expect(page.locator('[data-path="tracked.txt"]')).toBeVisible();
  await expect(page.locator('[data-path="hello.txt"]')).toBeVisible();

  // A terminal opened now starts in the worktree: its footer says so.
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: "Terminal" }).click();
  await expect(page.getByText(worktree, { exact: true })).toBeVisible({ timeout: 15_000 });

  // A new file tab opened from the strip is in the worktree too.
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: "File" }).click();
  await expect(page.locator("[data-crumb=worktree]")).toContainText("model-the-wrist");

  await page.getByRole("tab", { name: /hello\.txt/ }).click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(screenshots, "worktree-explorer.png"), animations: "disabled" });
});

test("the new-session state roots the explorer at the project again", async () => {
  // Leaving the thread for the project's new-session state: the root goes
  // back to the checkout, and a file tab opened now has no worktree crumb.
  await page.keyboard.press(process.platform === "darwin" ? "Meta+n" : "Control+n");
  await expect(page.locator("[data-new-session]")).toBeVisible();
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: "File" }).click();
  await expect(page.locator("[data-crumb=worktree]")).toHaveCount(0);
  await expect(page.locator('[data-path="hello.txt"]')).toHaveCount(0);
  await expect(page.locator('[data-path="tracked.txt"]')).toBeVisible();
});
