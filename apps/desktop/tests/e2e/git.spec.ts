import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { projectWorktreeDir } from "../../src/main/projects/workspace";
import type { TextToCadApi } from "../../src/shared/ipc";
import { chooseDirectory, launch, mod, newTab as newTabIn, scratch, settleTerminal, shoot as shootInto } from "./launch";

/**
 * Projects, git modes, worktrees and the review (plan §9), on one app and one
 * real repository.
 *
 *   - a folder chosen before a first prompt is a draft, not a saved project;
 *   - a `checkout` session's review is measured from the revisions main
 *     recorded when the session started and when its turn began: a turn runs
 *     (the fake agent writes a file), a person edits through the terminal tab,
 *     and the review shows both in every scope, then commits them;
 *   - a `worktree` session gets a branch and a directory of its own, the
 *     explorer roots there — the file an agent opens through the MCP server,
 *     the tree, the terminal's cwd — and Settings deletes it again;
 *   - the draft screen's own New worktree choice makes one too.
 *
 * Everything is temporary, the worktree root included, so a run never writes
 * to the developer's `~/.text-to-cad`.
 */

declare const window: { textToCad: TextToCadApi };

const gitEnv = {
  ...process.env,
  GIT_AUTHOR_NAME: "text-to-cad Tests",
  GIT_AUTHOR_EMAIL: "tests@example.invalid",
  GIT_COMMITTER_NAME: "text-to-cad Tests",
  GIT_COMMITTER_EMAIL: "tests@example.invalid",
};
const projectName = "text-to-cad-fixture";

let app: ElectronApplication;
let page: Page;
let base: string;
let repo: string;
let other: string;
let worktreeRoot: string;
let projectId: string;
let worktreeSessionId: string;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  base = scratch("git");
  repo = path.join(base, projectName);
  other = path.join(base, "Other project");
  worktreeRoot = path.join(base, "worktrees");
  fs.mkdirSync(repo);
  fs.mkdirSync(other);
  git("init", "--quiet", "--initial-branch=main");
  fs.writeFileSync(path.join(repo, "tracked.txt"), "one\ntwo\nthree\n");
  fs.writeFileSync(path.join(repo, "README.md"), "# Fixture\n");
  git("add", "-A");
  git("commit", "--quiet", "-m", "the state being reviewed against");
  ({ app, page } = await launch({ userData: path.join(base, "user-data") }));
  // The worktree root before anything can create one in the real home directory.
  await page.evaluate((root) => window.textToCad.settings.set({ theme: "dark", worktreeRoot: root, fetchBeforeCreate: false }), worktreeRoot);
});

test.afterAll(async () => {
  await app?.close();
  fs.rmSync(base, { recursive: true, force: true });
});

test("a chosen folder is a draft: no project, no explorer, and its words kept per folder", async () => {
  const added = await chooseDirectory(app, repo);
  projectId = added.id;
  const draft = page.getByPlaceholder("Describe a part to build…", { exact: true });
  await expect(draft).toBeVisible();
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Toggle explorer" })).toHaveCount(0);
  expect(await page.evaluate(() => window.textToCad.projects.list())).toEqual([]);
  await draft.fill("Round the car body");
  await chooseDirectory(app, other);
  await expect(page.getByRole("heading", { name: "What should we build in Other project?" })).toBeVisible();
  await expect(draft).toHaveText("");
  // Re-choosing a folder restores its in-memory draft, still without a saved project.
  await chooseDirectory(app, repo);
  await expect(draft).toHaveText("Round the car body");
  expect(await page.evaluate(() => window.textToCad.projects.list())).toEqual([]);
  await expect(page.getByTestId("sidebar").locator("[data-sidebar-section]")).toHaveCount(0);
  await draft.fill("");
});

test("a checkout session runs in the project, and the review shows the agent's and the person's changes in every scope", async () => {
  const session = await page.evaluate((id) => window.textToCad.sessions.create({ projectId: id, agentId: "claude-code", gitMode: "checkout" }), projectId);
  expect(session.cwd).toBe(repo);
  expect(session.branch).toBe("main");
  expect(session.worktreePath).toBeUndefined();
  // A turn: the fake agent writes a file into the session's cwd. This also records the
  // `Last turn` mark, which is read before the agent runs.
  const target = path.join(repo, "agent.txt");
  const { stopReason } = await page.evaluate(({ id, file }) =>
    window.textToCad.sessions.prompt({ id, content: [{ type: "text" as const, text: `please write ${file}` }] }), { id: session.id, file: target });
  expect(stopReason).toBe("end_turn");
  expect(fs.existsSync(target)).toBe(true);
  // Named from the first prompt, with no git glyph: `main` is the project's own branch.
  await page.locator("[data-session-row]").filter({ hasText: /please write/ }).getByRole("button", { name: /^please write/ }).first().click();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  await page.getByRole("button", { name: "Toggle explorer" }).click();

  // A person editing beside the agent, in the terminal tab.
  await newTab("Terminal");
  await expect(page.locator(".xterm-screen")).toBeVisible();
  await settleTerminal(page);
  await page.locator(".xterm-helper-textarea").click();
  await page.keyboard.type("echo four >> tracked.txt && echo wrote-four");
  await page.keyboard.press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText("wrote-four", { timeout: 20_000 });

  await newTab("Review");
  // All changes is the working tree against HEAD; This session and Last turn are measured from
  // snapshots of the working tree taken when the session and the turn began. The tree was clean
  // then, and both edits came after, so all three scopes list both files. (That the scopes
  // differ once earlier work is uncommitted is held by sessions.test.ts, without a launch.)
  await expect(page.getByRole("button", { name: /All changes/ })).toBeVisible();
  await expectReviewShowsBoth();
  await shoot("git-review-all.png");
  for (const scope of ["This session", "Last turn"]) {
    await chooseScope(scope);
    await expectReviewShowsBoth();
  }
});

test("commits every change from the popover, and Last turn still shows what the turn did", async () => {
  // No remote in this fixture, so the header offers Commit alone, not a push.
  await page.getByRole("button", { name: "Commit", exact: true }).click();
  await page.getByLabel("Commit message").fill("agent and human, one commit");
  await shoot("git-commit-panel.png");
  await page.getByRole("region", { name: "Commit changes" }).getByRole("button", { name: "Commit", exact: true }).click();
  await expect(page.getByLabel("Commit message")).toBeHidden({ timeout: 20_000 });
  await expect.poll(() => execFileSync("git", ["log", "-1", "--pretty=%s"], { cwd: repo, env: gitEnv }).toString().trim(), { timeout: 20_000 })
    .toBe("agent and human, one commit");
  // The scope is measured from where the working tree was when the turn began, so a commit does
  // not empty it: the difference between the scopes, and why the marks are revisions.
  await expectReviewShowsBoth();
  await chooseScope("All changes");
  await expect(page.getByText("No changes")).toBeVisible({ timeout: 20_000 });
  await shoot("git-review-committed.png");
});

/**
 * `<worktreeRoot>/<name>-<hash of the project path>`, computed by main's own helper so the
 * spec cannot drift from it. The project list stores the real path, so the hash is of that.
 */
function worktreeFolder(): string {
  return projectWorktreeDir({ worktreeRoot }, { name: projectName, path: fs.realpathSync(repo) });
}

test("a worktree session gets its own branch, directory and glyph, and the explorer roots there", async () => {
  const session = await page.evaluate((id) => window.textToCad.sessions.create({ projectId: id, agentId: "claude-code", gitMode: "worktree", name: "Model the wrist" }), projectId);
  worktreeSessionId = session.id;
  const worktree = path.join(worktreeFolder(), "model-the-wrist");
  expect(session.cwd).toBe(worktree);
  expect(session.worktreePath).toBe(worktree);
  expect(session.branch).toBe("text-to-cad/model-the-wrist");
  expect(fs.existsSync(path.join(worktree, "tracked.txt"))).toBe(true);
  // The sidebar's trailing glyph, labelled with the branch.
  await expect(page.getByLabel("Worktree · text-to-cad/model-the-wrist")).toBeVisible();

  await page.locator(`[data-session-row="${session.id}"]`).click();
  await expect(page.locator("[data-session-view]")).toBeVisible();
  // The fake agent writes `hello.txt` into the worktree, then calls the MCP server's `open_file`
  // on the relative name — adapter environment, stdio server, bridge token, main's root
  // resolution, the renderer's stores. The file exists only in the worktree.
  const outcome = await page.evaluate(({ id, text }) => window.textToCad.sessions.prompt({ id, content: [{ type: "text", text }] }),
    { id: session.id, text: `write ${path.join(worktree, "hello.txt")} then open hello.txt` });
  expect(outcome.stopReason).toBe("end_turn");
  expect(fs.existsSync(path.join(repo, "hello.txt"))).toBe(false);
  const state = await page.evaluate((id) => window.textToCad.sessions.state({ id }), session.id);
  const openFile = state?.state.turns.flatMap((turn) => turn.parts)
    .find((part) => part.type === "tool_call" && /open_file/.test(String((part as { title?: string }).title))) as { status: string; output: unknown } | undefined;
  expect(openFile?.status, JSON.stringify(openFile?.output)).toBe("completed");
  // The explorer opened it: the worktree in the breadcrumb (its path a hover hint, never a
  // native title), the file's own bytes, and the worktree's tree.
  await expect(page.getByRole("tab", { name: /hello\.txt/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("[data-crumb=worktree]")).toContainText("model-the-wrist");
  await expect(page.locator("[data-crumb=worktree]")).not.toHaveAttribute("title", /./);
  await page.locator("[data-crumb=worktree]").hover();
  await expect(page.getByRole("tooltip")).toHaveText(worktree);
  await page.mouse.move(0, 0);
  await expect(page.locator(".monaco-editor").first()).toContainText("hello", { timeout: 15_000 });
  await page.getByTestId("tree-toggle").click();
  await expect(page.locator('[data-path="hello.txt"]')).toBeVisible();
  // A terminal opened now starts in the worktree: its footer says so.
  await newTab("Terminal");
  await expect(page.getByText(worktree, { exact: true })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("tab", { name: /hello\.txt/ }).click();
  await shoot("worktree-explorer.png");

  // A local session in the same project has its own tabs, over the checkout.
  await page.keyboard.press(`${mod}+n`);
  await expect(page.getByTestId("explorer")).toHaveCount(0);
  const local = await page.evaluate((id) => window.textToCad.sessions.create({ projectId: id, agentId: "claude-code", gitMode: "none" }), projectId);
  await page.locator(`[data-session-row="${local.id}"]`).getByRole("button").first().click();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  await expect(page.getByRole("tab")).toHaveCount(0);
  await page.getByRole("button", { name: "Toggle explorer" }).click();
  await newTab("File");
  await expect(page.locator("[data-crumb=worktree]")).toHaveCount(0);
  await expect(page.locator('[data-path="tracked.txt"]')).toBeVisible();
  await expect(page.locator('[data-path="hello.txt"]')).toHaveCount(0);
  await page.locator(`[data-session-row="${worktreeSessionId}"]`).getByRole("button").first().click();
  await expect(page.getByRole("tab", { name: /hello\.txt/ })).toBeVisible();
  await expect(page.locator("[data-crumb=worktree]")).toContainText("model-the-wrist");
});

test("the worktree is listed in Settings, and Delete takes it away once no session is on it", async () => {
  const worktree = path.join(worktreeFolder(), "model-the-wrist");
  await page.keyboard.press(`${mod}+,`);
  await page.getByRole("button", { name: "Git and worktrees" }).click();
  await expect(page.getByText(`Worktrees · ${projectName}`)).toBeVisible();
  const card = page.getByText("text-to-cad/model-the-wrist", { exact: true });
  await card.scrollIntoViewIfNeeded();
  await shoot("git-settings-worktrees.png", true);
  // A session is still open on it, and it holds the agent's uncommitted file: Delete is refused
  // before it is pressed, for each reason.
  await expect(page.getByRole("button", { name: "Delete" }).first()).toBeDisabled();
  await page.evaluate((id) => window.textToCad.sessions.delete({ id }), worktreeSessionId);
  fs.rmSync(path.join(worktree, "hello.txt"));
  // Settings re-reads on remount: leaving and coming back proves the list is not a snapshot.
  await page.getByRole("button", { name: "General" }).click();
  await page.getByRole("button", { name: "Git and worktrees" }).click();
  await expect(page.getByRole("button", { name: "Delete" }).first()).toBeEnabled();
  await page.getByRole("button", { name: "Delete" }).first().click();
  await expect(page.getByText(`Worktrees · ${projectName}`)).toBeHidden({ timeout: 20_000 });
  expect(fs.existsSync(worktree)).toBe(false);
  // The branch is left behind: the checkout is recreatable, the commits on it are not.
  expect(execFileSync("git", ["branch", "--list", "text-to-cad/model-the-wrist"], { cwd: repo, env: gitEnv }).toString())
    .toContain("text-to-cad/model-the-wrist");
  await page.getByRole("button", { name: "Back to app" }).click();
});

test("the new-session screen's New worktree makes the session in a worktree of its own", async () => {
  await chooseDirectory(app, repo);
  await page.locator("[data-context-strip]").getByRole("button", { name: "Local", exact: true }).click();
  await page.getByRole("menuitemradio", { name: /New worktree/ }).click();
  await expect(page.locator('[data-composer-row] [data-chip="model"]')).toBeVisible({ timeout: 30_000 });
  const draft = page.getByPlaceholder("Describe a part to build…", { exact: true });
  await draft.fill("write a file");
  await draft.press("Enter");
  await expect(page.locator("[data-session-view]")).toBeVisible({ timeout: 30_000 });
  const sessions = await page.evaluate((id) => window.textToCad.sessions.list({ projectId: id }), projectId);
  const made = sessions.find((session) => session.title.startsWith("write a file"));
  expect(made?.cwd).not.toBe(repo);
  expect(made?.worktreePath).toBe(made?.cwd);
});

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function git(...args: string[]) {
  execFileSync("git", args, { cwd: repo, stdio: "ignore", env: gitEnv });
}

/**
 * Both the agent's file and the person's edit, with git's own counts, and both diffs drawn. A
 * new file's count comes from the file: `git diff --no-index` exits 1 for "the files differ",
 * and reading that as a failure showed every added file as `+0 −0`.
 */
async function expectReviewShowsBoth() {
  await expect(page.getByRole("button", { name: /tracked\.txt/ }).last()).toContainText("+1");
  await expect(page.getByRole("button", { name: /agent\.txt/ }).last()).toContainText("+1");
  // Each file's block once it has drawn (`data-review-ready`, review-diff.tsx), and only then
  // the count: the editor's DOM is the end of a chain — status, the file's own diff read, the
  // loader, the widget, the worker's diff — and polling for the DOM alone could not say which
  // link a slow run was still on. tracked.txt is modified, so a diff; agent.txt is new, so its
  // one side rather than a diff against an empty file.
  await expectDrawn("tracked.txt", "modified");
  await expectDrawn("agent.txt", "added");
  await expect(page.locator("[data-review-diff=modified] .monaco-diff-editor")).toHaveCount(1);
  await expect(page.locator("[data-review-diff=added] .monaco-editor")).toHaveCount(1);
}

/** One file's section has its diff read, as `kind`, and drawn. */
async function expectDrawn(file: string, kind: "modified" | "added") {
  const block = page.locator(`[data-review-file="${file}"] [data-review-diff]`);
  await expect(block).toHaveAttribute("data-review-diff", kind, { timeout: 30_000 });
  await expect(block).toHaveAttribute("data-review-ready", "true", { timeout: 30_000 });
}

async function chooseScope(label: string) {
  await page.getByRole("button", { name: /All changes|Last turn|This session|Since/ }).click();
  await page.getByRole("menuitemcheckbox", { name: label }).click();
  await expect(page.getByRole("button", { name: new RegExp(label) })).toBeVisible();
}

async function shoot(name: string, whole = false) {
  await shootInto(whole ? page : page.getByTestId("explorer"), name, test.info());
}

async function newTab(label: "File" | "Review" | "Terminal") {
  await newTabIn(page, label);
}
