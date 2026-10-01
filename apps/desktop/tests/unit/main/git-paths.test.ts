/**
 * A review's file path is renderer input. `fileDiff` and `unifiedDiff` read
 * the working copy for it, so a path that climbs out of the repository — or an
 * untracked symlink that points out of it — must never become a read of a
 * file outside the checkout.
 */
import { execFile } from "node:child_process";
import { mkdir, mkdtemp, realpath, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import type * as Execa from "execa";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const execa = vi.hoisted(() => vi.fn());
vi.mock("execa", async (importOriginal) => {
  const actual = await importOriginal<typeof Execa>();
  execa.mockImplementation(actual.execa);
  return { ...actual, execa };
});

import * as git from "@main/projects/git";
import { gitIpc } from "@shared/ipc/git";

const run = promisify(execFile);
const GIT_ENV = {
  ...process.env,
  GIT_AUTHOR_NAME: "text-to-cad Tests",
  GIT_AUTHOR_EMAIL: "tests@example.invalid",
  GIT_COMMITTER_NAME: "text-to-cad Tests",
  GIT_COMMITTER_EMAIL: "tests@example.invalid",
  GIT_CONFIG_GLOBAL: "/dev/null",
  GIT_CONFIG_SYSTEM: "/dev/null",
};

const scratch: string[] = [];
afterEach(async () => {
  await Promise.all(scratch.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});
beforeEach(() => {
  execa.mockClear();
});

/** `<base>/secret.txt` outside, and a committed repository at `<base>/repo`. */
async function fixture(): Promise<{ root: string; secret: string }> {
  const base = await realpath(await mkdtemp(path.join(os.tmpdir(), "t2c-git-paths-")));
  scratch.push(base);
  const secret = path.join(base, "secret.txt");
  await writeFile(secret, "[default]\nAWS_SECRET=hunter2\nregion=x\n");
  const root = path.join(base, "repo");
  await mkdir(root);
  await run("git", ["init", "--quiet", "--initial-branch=main"], { cwd: root, env: GIT_ENV });
  await writeFile(path.join(root, "README.md"), "one\n");
  await run("git", ["add", "-A"], { cwd: root, env: GIT_ENV });
  await run("git", ["commit", "--quiet", "-m", "first"], { cwd: root, env: GIT_ENV });
  return { root, secret };
}

/** Every argv git was started with during the test. */
function gitArgv(): string[][] {
  return execa.mock.calls.map((call) => call[1] as string[]);
}

/** The refusal itself — GitError with its sentence — not any failure on the way. */
const outside = { name: "GitError", message: "that path is outside the repository" };

describe("a review path outside the repository", () => {
  const escapes = ["../secret.txt", "sub/../../secret.txt", "/etc/hosts"];

  it.each(escapes)("fileDiff refuses %s before git sees it, and reads nothing", async (target) => {
    const { root } = await fixture();
    await expect(git.fileDiff(root, target)).rejects.toMatchObject(outside);
    expect(gitArgv().some((argv) => argv.includes(target))).toBe(false);
  });

  it.each(escapes)("unifiedDiff refuses %s before git sees it, and reads nothing", async (target) => {
    const { root } = await fixture();
    await expect(git.unifiedDiff(root, target)).rejects.toMatchObject(outside);
    expect(gitArgv().some((argv) => argv.includes(target))).toBe(false);
  });

  it("refuses a path through a symlinked directory that leaves the repository", async () => {
    const { root, secret } = await fixture();
    await symlink(path.dirname(secret), path.join(root, "out"));
    await expect(git.fileDiff(root, "out/secret.txt")).rejects.toMatchObject(outside);
    await expect(git.unifiedDiff(root, "out/secret.txt")).rejects.toMatchObject(outside);
  });

  it("the request schema refuses absolute and climbing paths", () => {
    for (const channel of [gitIpc.git.fileDiff, gitIpc.git.unifiedDiff]) {
      expect(channel.request.safeParse({ projectId: "p", path: "../x" }).success).toBe(false);
      expect(channel.request.safeParse({ projectId: "p", path: "a/../../x" }).success).toBe(false);
      expect(channel.request.safeParse({ projectId: "p", path: "/etc/hosts" }).success).toBe(false);
      expect(channel.request.safeParse({ projectId: "p", path: "" }).success).toBe(false);
      expect(channel.request.safeParse({ projectId: "p", path: "parts/..wrist.py" }).success).toBe(true);
    }
  });
});

describe("an untracked symlink that points out of the repository", () => {
  it("shows the link text, as git does, instead of the file it points at", async () => {
    const { root, secret } = await fixture();
    await symlink(secret, path.join(root, "creds"));

    const diff = await git.fileDiff(root, "creds");
    expect(diff.after).toBe(secret);
    expect(diff.after).not.toContain("hunter2");
    expect(diff.insertions).toBe(1);

    const patch = await git.unifiedDiff(root, "creds");
    expect(patch).not.toContain("hunter2");

    const listed = await git.status(root);
    expect(listed.files.find((file) => file.path === "creds")).toMatchObject({ insertions: 1, binary: false });
  });
});

describe("where a review's directory sits in its repository", () => {
  it("names the prefix of a project inside the repository, and none at its top", async () => {
    const { root } = await fixture();
    await mkdir(path.join(root, "app"));
    await writeFile(path.join(root, "app", "a.ts"), "one\n");
    // git names the file from the top; the explorer's watcher from the project.
    const inside = await git.status(path.join(root, "app"));
    expect(inside.prefix).toBe("app/");
    expect(inside.files.map((file) => file.path)).toEqual(["app/a.ts"]);
    expect((await git.status(root)).prefix).toBe("");
  });

  it("names a project folder called ..keep by its prefix, not as if it were outside", async () => {
    const { root } = await fixture();
    await mkdir(path.join(root, "..keep"));
    await writeFile(path.join(root, "..keep", "a.ts"), "one\n");
    expect((await git.status(path.join(root, "..keep"))).prefix).toBe("..keep/");
  });
});
