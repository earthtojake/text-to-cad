/**
 * The writes in `src/main/projects/git.ts` — commit and push — against real
 * repositories: what their failures say, and what they do with the remote.
 */
import fsp, { mkdtemp, readFile, realpath, rm, stat, truncate, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { endTrackedChildren, killTrackedChildren } from "@main/children";
import * as git from "@main/projects/git";

import { cleanGitTemplates, committedRepository, GIT_ENV, gitIn } from "./git-fixtures";

const previousEnv = { ...process.env };
const temporary: string[] = [];

beforeEach(() => {
  Object.assign(process.env, GIT_ENV);
});
afterEach(async () => {
  process.env = { ...previousEnv };
  for (const directory of temporary.splice(0)) {
    await rm(directory, { recursive: true, force: true });
  }
});
afterAll(cleanGitTemplates);

async function scratch(): Promise<string> {
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), "t2c-git-writes-")));
  temporary.push(directory);
  return directory;
}

async function repository(): Promise<string> {
  const root = path.join(await scratch(), "project");
  await committedRepository(root);
  return root;
}

describe("commitAll's errors", () => {
  it("says what a pre-commit hook printed, not 'git commit failed'", async () => {
    const root = await repository();
    const hook = path.join(root, ".git", "hooks", "pre-commit");
    await writeFile(hook, '#!/bin/sh\necho "no console.log"\nexit 1\n', { mode: 0o755 });
    await writeFile(path.join(root, "a.txt"), "a\n");

    await expect(git.commitAll(root, "add a")).rejects.toThrow(/no console\.log/);
  });

  it("says there was nothing to commit on a clean tree", async () => {
    const root = await repository();

    await expect(git.commitAll(root, "nothing")).rejects.toThrow(/nothing to commit/);
  });
});

describe("a commit in flight at quit", () => {
  it("is asked to stop, so it drops its index.lock instead of leaving one", async () => {
    const root = await repository();
    const pidFile = path.join(root, "..", "filter.pid");
    const script = path.join(root, "..", "slow-clean.sh");
    // `git add -A` holds .git/index.lock while it runs a clean filter, so a
    // filter that never finishes is a commit caught with the lock in hand.
    await writeFile(script, `#!/bin/sh\necho $$ > "${pidFile}"\nexec sleep 60\n`, { mode: 0o755 });
    await gitIn(root, "config", "filter.slow.clean", script);
    await writeFile(path.join(root, ".gitattributes"), "*.txt filter=slow\n");
    await writeFile(path.join(root, "a.txt"), "a\n");
    const lock = path.join(root, ".git", "index.lock");

    const committing = git.commitAll(root, "add a").catch((error: unknown) => error);
    try {
      await vi.waitFor(async () => {
        await readFile(pidFile, "utf8");
        await stat(lock);
      }, { timeout: 15_000 });

      endTrackedChildren();
      await committing;

      await expect(stat(lock)).rejects.toMatchObject({ code: "ENOENT" });
    } finally {
      const pid = Number((await readFile(pidFile, "utf8").catch(() => "")).trim());
      if (pid > 0) process.kill(pid, "SIGKILL");
      killTrackedChildren();
    }
  });
});

describe("counting an untracked file", () => {
  it("does not read a huge one whole on every status", async () => {
    const root = await repository();
    // 50 MB of nothing: a sparse file costs no disk, and a whole read costs 50 MB of memory.
    const big = path.join(root, "part.step");
    await truncate(big, 50 * 1024 * 1024).catch(async () => {
      await writeFile(big, "");
      await truncate(big, 50 * 1024 * 1024);
    });
    const text = path.join(root, "notes.txt");
    await writeFile(text, "line\n".repeat(300_000));
    const reads = vi.spyOn(fsp, "readFile");
    try {
      const status = await git.status(root);
      const byPath = new Map(status.files.map((file) => [file.path, file]));

      expect(reads.mock.calls.map(([file]) => String(file)).filter((file) => /part\.step$|notes\.txt$/.test(file))).toEqual([]);
      expect(byPath.get("part.step")).toMatchObject({ binary: true });
      expect(byPath.get("notes.txt")).toMatchObject({ insertions: 300_000, binary: false });
    } finally {
      reads.mockRestore();
    }
  });

  it("refuses to load a file past the viewer's size into a diff editor", async () => {
    const root = await repository();
    await writeFile(path.join(root, "export.txt"), "row\n".repeat(1_500_000));

    await expect(git.fileDiff(root, "export.txt")).rejects.toThrow(/too large/);
  });
});

describe("push", () => {
  it("goes to the only remote there is, whatever it is called", async () => {
    const root = await repository();
    const remote = path.join(root, "..", "fork.git");
    await gitIn(root, "init", "--quiet", "--bare", "--initial-branch=main", remote);
    await gitIn(root, "remote", "add", "fork", remote);

    await git.push(root);

    expect((await gitIn(remote, "rev-parse", "main")).stdout.trim()).toBe((await git.head(root)) ?? "");
    expect((await gitIn(root, "rev-parse", "--abbrev-ref", "main@{upstream}")).stdout.trim()).toBe("fork/main");
  });
});
