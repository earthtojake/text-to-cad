/**
 * `releaseWorkspace` for an abandoned create when the project's own folder is
 * gone as well: nothing can be asked of git, so the answer is "not removed",
 * with a reason, and nothing else on disk is touched.
 */
import { mkdtemp, readdir, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterAll, afterEach, expect, it } from "vitest";

import { releaseWorkspace } from "@main/projects/workspace";

import { cleanGitTemplates, committedRepository, gitIn } from "./git-fixtures";

const temporary: string[] = [];
afterEach(async () => {
  for (const directory of temporary.splice(0)) await rm(directory, { recursive: true, force: true });
});
afterAll(cleanGitTemplates);

it("an abandoned release resolves, touching nothing, when the worktree and the project folder are both gone", async () => {
  const base = await realpath(await mkdtemp(path.join(os.tmpdir(), "text-to-cad-release-")));
  temporary.push(base);
  // A bystander repository beside the missing paths: it must come out unchanged.
  const bystander = path.join(base, "bystander");
  await committedRepository(bystander, "one\n");
  await writeFile(path.join(base, "note.txt"), "keep\n");
  const branchesBefore = (await gitIn(bystander, "branch", "--list")).stdout;
  const before = (await readdir(base)).sort();

  const result = await releaseWorkspace(
    {
      worktreePath: path.join(base, "worktrees", "gone-worktree"),
      projectId: path.join(base, "gone-project"),
      branch: "text-to-cad/gone",
      sessionHead: "0".repeat(40),
    },
    { autoDeleteWorktrees: false },
    { abandoned: true },
  );

  expect(result.removed).toBe(false);
  expect(result.reason, "a reason is given rather than a throw").toEqual(expect.any(String));
  expect((await readdir(base)).sort(), "nothing outside was created or removed").toEqual(before);
  expect((await gitIn(bystander, "branch", "--list")).stdout).toBe(branchesBefore);
});
