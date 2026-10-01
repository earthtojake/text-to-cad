/**
 * Why a folder has no repository: `status` and `repoInfo`
 * tell git missing, a deleted folder, dubious ownership and a timeout apart
 * from a folder that is simply not a repository.
 */
import { chmod, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import * as git from "@main/projects/git";

const cleanups: (() => Promise<void> | void)[] = [];
afterEach(async () => {
  for (const undo of cleanups.splice(0).reverse()) await undo();
});

async function scratch(): Promise<string> {
  const dir = await realpath(await mkdtemp(path.join(os.tmpdir(), "text-to-cad-problems-")));
  cleanups.push(() => rm(dir, { recursive: true, force: true }));
  return dir;
}

/** PATH set to `dir` alone (plus node's, which the shim needs not), restored after. */
function pathOnly(dir: string) {
  const before = process.env.PATH;
  process.env.PATH = dir;
  cleanups.push(() => {
    process.env.PATH = before;
  });
}

describe("why a folder has no repository", () => {
  it("says git is missing when no git is on the PATH", async () => {
    const folder = await scratch();
    const empty = await scratch();
    pathOnly(empty);
    expect(await git.repositoryRoot(folder)).toBeNull();
    expect(await git.status(folder)).toMatchObject({ isRepository: false, problem: "git is not installed or not on PATH" });
    expect(await git.repoInfo(folder)).toMatchObject({ isRepository: false, problem: "git is not installed or not on PATH" });
  });

  it("says the folder is gone when the directory no longer exists", async () => {
    const folder = path.join(await scratch(), "vanished");
    expect(await git.status(folder)).toMatchObject({ isRepository: false, problem: "vanished no longer exists" });
    expect(await git.repoInfo(folder)).toMatchObject({ problem: "vanished no longer exists" });
  });

  it("gives git's ownership refusal as a sentence", async () => {
    const folder = await scratch();
    const bin = await scratch();
    const shim = path.join(bin, "git");
    await writeFile(shim, "#!/bin/sh\necho \"fatal: detected dubious ownership in repository at '$PWD'\" >&2\nexit 128\n");
    await chmod(shim, 0o755);
    pathOnly(bin);
    const answer = await git.status(folder);
    expect(answer.isRepository).toBe(false);
    expect(answer.problem).toMatch(/another user owns it/);
  });

  it("stays silent for a folder that is just not a repository", async () => {
    const folder = await scratch();
    expect(await git.status(folder)).not.toHaveProperty("problem");
  });

  it("carries the reason into worktree mode's refusal", async () => {
    const folder = path.join(await scratch(), "vanished");
    await expect(git.createWorktree({ repoPath: folder, parentDir: await scratch() })).rejects.toThrow("vanished no longer exists");
  });
});
