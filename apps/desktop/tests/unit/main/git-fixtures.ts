/**
 * Real git repositories for the git and workspace suites, built once per test
 * file and copied per test.
 *
 * A one-commit repository costs three `git` processes (init, add, commit), a
 * pushed one five more, a remote a commit ahead of it five more again; the
 * suites used to pay that in every test. Here each shape is built the first
 * time a file asks for it, in a template directory, and every test gets a
 * recursive copy: a repository is only files, and a copy of one is the same
 * repository. The one absolute path a copy carries — `origin`'s URL, a path
 * to a bare repository beside it — is rewritten to the copy's own remote, so
 * no test can push into the template or another test's remote.
 *
 * Each test file gets its own copy of this module (vitest isolates modules per
 * file), so its templates are its own; `cleanGitTemplates` in the file's
 * `afterAll` removes them.
 */
import { execFile } from "node:child_process";
import { cp, mkdir, mkdtemp, readFile, realpath, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import { removeTree } from "./temp-dirs";

const run = promisify(execFile);

/** A fixed identity: a fresh CI runner has no `user.name` and `git commit` fails without one. */
export const GIT_ENV = {
  ...process.env,
  GIT_AUTHOR_NAME: "text-to-cad Tests",
  GIT_AUTHOR_EMAIL: "tests@example.invalid",
  GIT_COMMITTER_NAME: "text-to-cad Tests",
  GIT_COMMITTER_EMAIL: "tests@example.invalid",
  GIT_CONFIG_GLOBAL: "/dev/null",
  GIT_CONFIG_SYSTEM: "/dev/null",
};

export function gitIn(cwd: string, ...args: string[]) {
  return run("git", args, { cwd, env: GIT_ENV });
}

type Template = { root: string; remote?: string; serverTip?: string };

const templates = new Map<string, Promise<Template>>();
const templateDirs: string[] = [];

function memo(key: string, build: () => Promise<Template>): Promise<Template> {
  let made = templates.get(key);
  if (!made) {
    made = build();
    templates.set(key, made);
  }
  return made;
}

async function templateBase(): Promise<string> {
  // Not `tempDir`: a file's `cleanTempDirs` after each test would take the
  // templates with it.
  const base = await realpath(await mkdtemp(path.join(os.tmpdir(), "text-to-cad-git-template-")));
  templateDirs.push(base);
  return base;
}

/** main, one commit, `README.md` holding `readme`. */
function committedTemplate(readme: string): Promise<Template> {
  return memo(`committed:${readme}`, async () => {
    const root = path.join(await templateBase(), "project");
    await mkdir(root, { recursive: true });
    await gitIn(root, "init", "--quiet", "--initial-branch=main");
    await writeFile(path.join(root, "README.md"), readme);
    await gitIn(root, "add", "-A");
    await gitIn(root, "commit", "--quiet", "-m", "first");
    return { root };
  });
}

/**
 * That repository with a bare `origin` it has pushed `main` to (and tracks);
 * with `ahead`, someone else has since pushed a commit adding `theirs.txt`
 * that this checkout has not fetched.
 */
function pushedTemplate(readme: string, ahead: boolean): Promise<Template> {
  return memo(`pushed:${readme}:${ahead}`, async () => {
    const committed = await committedTemplate(readme);
    const base = await templateBase();
    const root = path.join(base, "project");
    const remote = path.join(base, "remote.git");
    await cp(committed.root, root, { recursive: true });
    // The bare remote's HEAD is git's compiled-in default branch unless said
    // otherwise (CI has no `init.defaultBranch`); a clone of it would then
    // sit on an unborn `master` and the push below would have no `main`.
    await gitIn(base, "init", "--quiet", "--bare", "--initial-branch=main", remote);
    await gitIn(root, "remote", "add", "origin", remote);
    await gitIn(root, "push", "--quiet", "-u", "origin", "main");
    if (!ahead) return { root, remote };
    const other = path.join(base, "other");
    await gitIn(base, "clone", "--quiet", "--branch", "main", remote, other);
    await writeFile(path.join(other, "theirs.txt"), "new\n");
    await gitIn(other, "add", "-A");
    await gitIn(other, "commit", "--quiet", "-m", "theirs");
    await gitIn(other, "push", "--quiet", "origin", "main");
    const serverTip = (await gitIn(other, "rev-parse", "HEAD")).stdout.trim();
    return { root, remote, serverTip };
  });
}

/** Copy a template's checkout to `root` (and its remote to `remote`), repointing `origin`. */
async function place(template: Template, root: string, remote?: string): Promise<void> {
  await cp(template.root, root, { recursive: true });
  if (template.remote && remote) {
    await cp(template.remote, remote, { recursive: true });
    const config = path.join(root, ".git", "config");
    const text = await readFile(config, "utf8");
    if (!text.includes(template.remote)) throw new Error(`origin is not ${template.remote} in ${config}`);
    await writeFile(config, text.split(template.remote).join(remote));
  }
}

/** A repository at `root` (which must not exist yet) on `main` with one commit: `README.md` = `readme`. */
export async function committedRepository(root: string, readme = "one\n"): Promise<void> {
  await place(await committedTemplate(readme), root);
}

/**
 * {@link committedRepository}, plus a bare repository at `remote` as its
 * `origin`, with `main` pushed and tracked. With `ahead`, the remote has one
 * more commit (adding `theirs.txt`) the checkout has not fetched; its id is
 * `serverTip`.
 */
export async function pushedRepository(
  root: string,
  remote: string,
  options: { readme?: string; ahead?: boolean } = {},
): Promise<{ serverTip: string | undefined }> {
  const template = await pushedTemplate(options.readme ?? "one\n", options.ahead ?? false);
  await place(template, root, remote);
  return { serverTip: template.serverTip };
}

/** A fresh, `realpath`ed temporary directory, recorded in `temporary` for the file's `afterEach` to remove. */
export async function scratchDir(prefix: string, temporary: string[]): Promise<string> {
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), prefix)));
  temporary.push(directory);
  return directory;
}

/** A repository with one commit (`README.md` = `one\ntwo\n`), and a directory beside it for its worktrees. */
export async function repositoryWithWorktrees(temporary: string[]): Promise<{ root: string; worktrees: string }> {
  const base = await scratchDir("text-to-cad-git-", temporary);
  const root = path.join(base, "project");
  const worktrees = path.join(base, "worktrees");
  await committedRepository(root, "one\ntwo\n");
  return { root, worktrees };
}

/** Remove this file's templates. Call from `afterAll`. */
export function cleanGitTemplates(): void {
  templates.clear();
  for (const dir of templateDirs.splice(0)) removeTree(dir);
}
