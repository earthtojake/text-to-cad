import { execFileSync } from "node:child_process";
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
 * Git modes, worktrees and the review (plan §9), end to end in the built app.
 *
 * Two sessions, because the two halves of P7 are two different shapes:
 *
 *   - a `checkout` session, whose review is measured from the revisions main
 *     recorded when the session started and when its turn began. A turn runs
 *     (the fake agent writes a file), a person edits through the terminal tab,
 *     and the review has to show both under `All changes`, `This session` and
 *     `Last turn` — then commit them from the popover;
 *   - a `worktree` session, which gets a branch and a directory of its own,
 *     a worktree glyph in the sidebar, a card in Settings › Git & Worktrees,
 *     and a Delete that takes the directory away again.
 *
 * Everything the suite touches is temporary: the repository, the user-data
 * directory, and — importantly — the worktree root, which is pointed at a
 * temporary directory before the first session so a test run never writes to
 * the developer's `~/.hardcore`.
 *
 * The agent is `tests/fake-agent/index.mjs`, reached through
 * `HARDCORE_FAKE_AGENT`. A session needs an agent to exist at all, and a real
 * one would make this suite a test of somebody's login state.
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
      prompt(request: {
        id: string;
        content: { type: "text"; text: string }[];
      }): Promise<{ stopReason: string }>;
    };
    git: {
      worktrees(request: {
        projectId: string;
      }): Promise<{ path: string; branch: string | null }[]>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");
const fakeAgent = path.join(appRoot, "tests", "fake-agent", "index.mjs");

/**
 * The fixture repository's identity, so the suite does not depend on the
 * machine's `user.name` being set — on a fresh CI runner `git commit` fails
 * without one.
 */
const gitEnv = {
  ...process.env,
  GIT_AUTHOR_NAME: "Hardcore Tests",
  GIT_AUTHOR_EMAIL: "tests@example.invalid",
  GIT_COMMITTER_NAME: "Hardcore Tests",
  GIT_COMMITTER_EMAIL: "tests@example.invalid",
};

let app: ElectronApplication;
let page: Page;
let userData: string;
let repo: string;
let worktreeRoot: string;
let projectId: string;
const projectName = "text-to-cad-fixture";

test.beforeAll(async () => {
  const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-git-e2e-")));
  repo = path.join(base, projectName);
  worktreeRoot = path.join(base, "worktrees");
  userData = path.join(base, "user-data");
  fs.mkdirSync(repo, { recursive: true });

  const git = (...args: string[]) =>
    execFileSync("git", args, { cwd: repo, stdio: "ignore", env: gitEnv });
  git("init", "--quiet", "--initial-branch=main");
  fs.writeFileSync(path.join(repo, "tracked.txt"), "one\ntwo\nthree\n");
  git("add", "-A");
  git("commit", "--quiet", "-m", "the state being reviewed against");

  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: fakeAgent },
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");

  // Dark for comparability with the other suites' screenshots — and the
  // worktree root, before anything can create one in the real home directory.
  await page.evaluate(
    (root) => window.hardcore.settings.set({ theme: "dark", worktreeRoot: root }),
    worktreeRoot,
  );

  const project = await page.evaluate(
    (root) => window.hardcore.projects.addPath({ path: root }),
    repo,
  );
  projectId = project.id;
  await expect(page.getByText(projectName).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "New tab", exact: true })).toBeEnabled();
});

test.afterAll(async () => {
  await app?.close();
  fs.rmSync(path.dirname(repo), { recursive: true, force: true });
});

test.describe.configure({ mode: "serial" });

/* -------------------------------------------------------------------------- */
/* checkout mode, and the review's scopes                                      */
/* -------------------------------------------------------------------------- */

test("a checkout session runs in the project, on the branch it is already on", async () => {
  const session = await page.evaluate(
    (id) =>
      window.hardcore.sessions.create({
        projectId: id,
        agentId: "claude-code",
        gitMode: "checkout",
      }),
    projectId,
  );
  expect(session.cwd).toBe(repo);
  expect(session.branch).toBe("main");
  expect(session.worktreePath).toBeUndefined();

  // A turn: the fake agent writes a file into the session's cwd. This is also
  // what records the `Last turn` mark, which is read *before* the agent runs.
  const target = path.join(repo, "agent.txt");
  const { stopReason } = await page.evaluate(
    ({ id, file }) =>
      window.hardcore.sessions.prompt({
        id,
        content: [{ type: "text" as const, text: `please write ${file}` }],
      }),
    { id: session.id, file: target },
  );
  expect(stopReason).toBe("end_turn");
  expect(fs.existsSync(target)).toBe(true);

  // The sidebar names the thread from the first prompt, with no git glyph:
  // `main` is the project's own branch, and a glyph on every row says nothing.
  const row = page.getByRole("button", { name: /please write/ });
  await expect(row).toBeVisible();
  await row.click();
});

test("a change made in the terminal tab lands in the review, in every scope", async () => {
  await page.getByRole("button", { name: "New tab of another kind" }).click();
  await page.getByRole("menuitem", { name: "Terminal" }).click();
  await expect(page.locator(".xterm-screen")).toBeVisible();
  await settleTerminal();
  await page.locator(".xterm-helper-textarea").click();

  // A person editing beside the agent — the case the review has to cover as
  // well as the agent's own diffs.
  await page.keyboard.type("echo four >> tracked.txt && echo wrote-four");
  await page.keyboard.press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText("wrote-four", { timeout: 20_000 });

  await page.getByRole("button", { name: "New tab of another kind" }).click();
  await page.getByRole("menuitem", { name: "Review" }).click();

  // All changes: the working tree against HEAD.
  await expect(page.getByRole("button", { name: /All changes/ })).toBeVisible();
  await expectReviewShowsBoth();
  await shoot("git-review-all.png");

  // This session: measured from the revision recorded when the session was
  // created. Nothing has been committed since, so it is the same two files —
  // and the point is that the number *agrees* rather than that it differs.
  await chooseScope("This session");
  await expectReviewShowsBoth();
  await shoot("git-review-session.png");

  // Last turn: measured from the revision recorded when the prompt was sent.
  await chooseScope("Last turn");
  await expectReviewShowsBoth();
  await shoot("git-review-turn.png");
});

test("commits every change from the popover", async () => {
  await page.getByRole("button", { name: "Commit or push" }).click();
  await page.getByLabel("Commit message").fill("agent and human, one commit");
  await page.getByRole("button", { name: "Commit", exact: true }).click();
  // The popover closes when the commit lands, which is also when the review
  // behind it has been asked to re-read.
  await expect(page.getByLabel("Commit message")).toBeHidden({ timeout: 20_000 });

  await expect
    .poll(
      () => execFileSync("git", ["log", "-1", "--pretty=%s"], { cwd: repo, env: gitEnv }).toString().trim(),
      { timeout: 20_000 },
    )
    .toBe("agent and human, one commit");

  // The commit does not empty `Last turn`: the scope is measured from where
  // the working tree was when the turn began, so what the turn did is still
  // what it shows. This is the difference between the two scopes, and the
  // reason the marks are revisions rather than "uncommitted".
  await expectReviewShowsBoth();
  await shoot("git-review-turn-after-commit.png");

  // `All changes` is HEAD against the working tree, and that is now empty.
  await chooseScope("All changes");
  await expect(page.getByText("No changes")).toBeVisible({ timeout: 20_000 });
  await shoot("git-review-committed.png");
});

/* -------------------------------------------------------------------------- */
/* worktree mode                                                               */
/* -------------------------------------------------------------------------- */

test("a worktree session gets its own branch, directory and sidebar glyph", async () => {
  const session = await page.evaluate(
    (id) =>
      window.hardcore.sessions.create({
        projectId: id,
        agentId: "claude-code",
        gitMode: "worktree",
        name: "Model the wrist",
      }),
    projectId,
  );

  const expected = path.join(worktreeRoot, projectName, "model-the-wrist");
  expect(session.cwd).toBe(expected);
  expect(session.worktreePath).toBe(expected);
  expect(session.branch).toBe("hardcore/model-the-wrist");
  // A real checkout, not an empty directory.
  expect(fs.existsSync(path.join(expected, "tracked.txt"))).toBe(true);

  // The sidebar's trailing glyph, labelled with the branch.
  await expect(
    page.getByLabel("Worktree · hardcore/model-the-wrist"),
  ).toBeVisible();
  await page.screenshot({
    animations: "disabled",
    path: path.join(screenshots, "git-sidebar-glyph.png"),
  });
});

test("the worktree appears in Settings, and Delete takes it away", async () => {
  const expected = path.join(worktreeRoot, projectName, "model-the-wrist");

  await page.keyboard.press(process.platform === "darwin" ? "Meta+," : "Control+,");
  await page.getByRole("button", { name: "Git & Worktrees" }).click();
  await expect(page.getByText(`Worktrees · ${projectName}`)).toBeVisible();
  const card = page.getByText("hardcore/model-the-wrist", { exact: true });
  await expect(card).toBeVisible();
  // The card is below three cards of settings; a screenshot of the top of the
  // page is a screenshot of P6's rows, not of this one.
  await card.scrollIntoViewIfNeeded();
  await shoot("git-settings-worktrees.png", true);

  // The session is still open on it, so Delete is refused before it is
  // pressed rather than after: pulling the directory out from under a running
  // agent is not a thing a settings page should offer.
  const remove = page.getByRole("button", { name: "Delete" }).first();
  await expect(remove).toBeDisabled();

  // Close the thread, and the row becomes deletable.
  await page.evaluate(async () => {
    const sessions = (await (
      window as unknown as {
        hardcore: { sessions: { list(r: object): Promise<{ id: string; gitMode: string }[]> } };
      }
    ).hardcore.sessions.list({})) as { id: string; gitMode: string }[];
    const worktree = sessions.find((session) => session.gitMode === "worktree");
    if (worktree) {
      await (
        window as unknown as {
          hardcore: { sessions: { delete(r: { id: string }): Promise<void> } };
        }
      ).hardcore.sessions.delete({ id: worktree.id });
    }
  });

  // Settings re-reads on remount; leaving and coming back is what a person
  // would do, and it is what proves the list is not a snapshot.
  await page.getByRole("button", { name: "General" }).click();
  await page.getByRole("button", { name: "Git & Worktrees" }).click();
  await expect(page.getByRole("button", { name: "Delete" }).first()).toBeEnabled();
  await page.getByRole("button", { name: "Delete" }).first().click();

  await expect(page.getByText(`Worktrees · ${projectName}`)).toBeHidden({ timeout: 20_000 });
  expect(fs.existsSync(expected)).toBe(false);
  // The branch is left behind: the checkout is recreatable, the commits on it
  // are not.
  const branches = execFileSync("git", ["branch", "--list", "hardcore/model-the-wrist"], {
    cwd: repo,
    env: gitEnv,
  });
  expect(branches.toString()).toContain("hardcore/model-the-wrist");
  // The same view as the shot above, with the card gone: the pull-request card
  // is what is now at the bottom of the page.
  await page.getByText("Create draft pull requests").scrollIntoViewIfNeeded();
  await shoot("git-settings-empty.png", true);
});

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Both the agent's file and the person's edit, with git's own counts, and both
 * diffs actually drawn.
 *
 * The diff editors are waited for because the screenshots are the point: a
 * review caught mid-fetch is a picture of "Reading the diff…", which says
 * nothing about whether the review works.
 */
async function expectReviewShowsBoth() {
  await expect(page.getByRole("button", { name: /tracked\.txt/ }).last()).toContainText("+1");
  await expect(page.getByRole("button", { name: /agent\.txt/ }).last()).toContainText("+1");
  await expect(page.locator(".monaco-diff-editor")).toHaveCount(2, { timeout: 30_000 });
}

async function chooseScope(label: string) {
  await page.getByRole("button", { name: /All changes|Last turn|This session|Since/ }).click();
  await page.getByRole("menuitemcheckbox", { name: label }).click();
  await expect(page.getByRole("button", { name: new RegExp(label) })).toBeVisible();
}

/** The explorer pane, or the whole window when the shot is about the window. */
async function shoot(name: string, whole = false) {
  const target = whole ? page : page.getByTestId("explorer");
  await target.screenshot({ path: path.join(screenshots, name), animations: "disabled" });
}

/**
 * Wait until the shell is at a prompt — the same reasoning as the explorer
 * suite's copy: a login shell runs the user's profile first, in bursts with
 * gaps, and typing into a gap gets the keystrokes echoed twice.
 */
async function settleTerminal() {
  let previous = "";
  let stableFor = 0;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const current = await page.locator(".xterm-rows").innerText();
    const lines = current.split("\n").filter((line) => line.trim() !== "");
    if (/[$%>#]\s*$/.test(lines.at(-1) ?? "")) {
      return;
    }
    stableFor = current !== "" && current === previous ? stableFor + 1 : 0;
    if (stableFor >= 20) {
      return;
    }
    previous = current;
    await page.waitForTimeout(150);
  }
}
