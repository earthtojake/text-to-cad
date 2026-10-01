/**
 * Where a session's working directory comes from (plan §9).
 *
 * Three modes, and the whole difference between them is one path:
 *
 *   - `none`      the project directory. Git is not consulted at all, so a
 *                 folder that is not a repository is a perfectly good project;
 *   - `checkout`  the project directory, on whatever branch it is already on.
 *                 The session shares the tree with the person's editor;
 *   - `worktree`  a fresh branch in a fresh worktree under the worktree root,
 *                 so the agent works on its own copy of the tree.
 *
 * No mode is ever forced. `worktree` is the only one that can fail, and it
 * fails with a sentence rather than a git error — "Project is not a git
 * repository, worktree mode unavailable" is something a person can act on.
 *
 * The layout is the same for every agent (plan §9):
 *
 *     ~/.text-to-cad/worktrees/<project-slug>-<hash>/<slug>
 *
 * with the branch `text-to-cad/<slug>` (`projectWorktreeDir`). `<hash>` is
 * eight hex digits of the project's path: `~/work/robot-arm` and
 * `~/forks/robot-arm` are two projects and get two folders. Builds before the
 * hash used `<project-slug>` alone; those folders are still listed and
 * accepted, but only for worktrees git says belong to the project's own
 * repository (`legacyProjectWorktreeDir`).
 *
 * Both the root and the prefix are settings. The slug comes from the
 * session's first prompt when there is one, because that is what the sidebar
 * calls the thread — a person looking at
 * `~/.text-to-cad/worktrees/text-to-cad-1a2b3c4d/model-the-wrist` knows which
 * thread it belongs to without opening anything.
 *
 * The directory is also the *identity* of the session as far as the agent's
 * own store is concerned: both `codex resume` and `claude --resume` key their
 * threads by cwd, so a worktree is what makes a text-to-cad session resumable
 * from a terminal later.
 */
import { createHash } from "node:crypto";
import { readFileSync, realpathSync, statSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import type { GitMode, Project, Settings } from "../../shared/types";
import * as git from "./git";

/** Where a session runs, and what git calls it. */
export type Workspace = {
  cwd: string;
  /** The branch the session is on, for `checkout` and `worktree`. */
  branch?: string;
  /** Set only for `worktree`: the directory to remove when the session goes. */
  worktreePath?: string;
};

/**
 * The default worktree root, expanded.
 *
 * Stored as null rather than as a home path so the settings row can show the
 * default without writing this machine's home directory into the database —
 * and so a database copied to another machine still points somewhere real.
 */
export function worktreeRoot(settings: Pick<Settings, "worktreeRoot">): string {
  return settings.worktreeRoot ?? path.join(os.homedir(), ".text-to-cad", "worktrees");
}

/** The readable half of a project's worktree folder name. */
function projectSlug(project: Pick<Project, "name" | "path">): string {
  // Directory descriptors derive their name from the basename. Existing
  // session worktree paths remain authoritative if an older build used a
  // custom project name for this folder.
  return git.slugify(project.name) || git.slugify(path.basename(project.path)) || "project";
}

/**
 * `<root>/<project>-<hash>` — one folder per project, whichever agent made
 * it. The hash is of the project's path, so two projects that share a
 * basename never share a folder. New worktrees are always created here.
 */
export function projectWorktreeDir(
  settings: Pick<Settings, "worktreeRoot">,
  project: Pick<Project, "name" | "path">,
): string {
  const hash = createHash("sha256").update(path.resolve(project.path)).digest("hex").slice(0, 8);
  return path.join(worktreeRoot(settings), `${projectSlug(project)}-${hash}`);
}

/**
 * `<root>/<project>` — the folder builds before the hash created. Every
 * same-named project maps to it, so being under it proves nothing on its
 * own: callers also check that git lists the worktree as the project's.
 */
export function legacyProjectWorktreeDir(
  settings: Pick<Settings, "worktreeRoot">,
  project: Pick<Project, "name" | "path">,
): string {
  return path.join(worktreeRoot(settings), projectSlug(project));
}

/** Both folders a project's generated worktrees can be in: current first. */
export function projectWorktreeDirs(
  settings: Pick<Settings, "worktreeRoot">,
  project: Pick<Project, "name" | "path">,
): string[] {
  return [projectWorktreeDir(settings, project), legacyProjectWorktreeDir(settings, project)];
}

/**
 * Is `candidate` somewhere this project's work is allowed to be — the project
 * directory itself, or a directory under its worktree folder?
 *
 * The one answer to that question, asked by three callers: Settings' `New
 * session in this worktree` (a session about to run there), the explorer (a
 * root a tab reads from, plan §9's worktree-aware tree) and the MCP bridge
 * (an agent naming a file in its session's cwd). A renderer or an agent can
 * name any directory on the machine; this is what keeps the answer to the
 * project.
 */
export function rootBelongsToProject(
  settings: Pick<Settings, "worktreeRoot">,
  project: Pick<Project, "name" | "path">,
  candidate: string,
): boolean {
  const requested = realDirectory(candidate);
  if (isProjectDirectory(project, candidate) ||
      git.isUnder(realDirectory(projectWorktreeDir(settings, project)), requested)) {
    return true;
  }
  // The pre-hash folder is shared by every project with this name: a
  // directory there is this project's only when its worktree is one of this
  // repository's.
  const legacy = realDirectory(legacyProjectWorktreeDir(settings, project));
  if (!git.isUnder(legacy, requested)) {
    return false;
  }
  const top = path.relative(legacy, requested).split(path.sep)[0] ?? "";
  return worktreeOfRepository(path.join(legacy, top), project.path);
}

/**
 * Is `worktree` a linked worktree of the repository at `repository`? Read off
 * the `.git` files (`gitdir: <common>/worktrees/<name>`), synchronously, so
 * `rootBelongsToProject` can stay a plain predicate.
 */
function worktreeOfRepository(worktree: string, repository: string): boolean {
  const linked = gitDirOf(worktree);
  const common = commonGitDir(repository);
  if (!linked || !common) {
    return false;
  }
  return git.isUnder(path.join(common, "worktrees"), linked);
}

/** `<dir>/.git` as a directory, or the `gitdir:` a `.git` file names; realpath'd. */
function gitDirOf(directory: string): string | null {
  const dotGit = path.join(directory, ".git");
  try {
    if (statSync(dotGit).isDirectory()) {
      return realpathSync(dotGit);
    }
    const named = /^gitdir:\s*(.+)$/m.exec(readFileSync(dotGit, "utf8"))?.[1]?.trim();
    return named ? realpathSync(path.resolve(directory, named)) : null;
  } catch {
    return null;
  }
}

/** The repository's shared git directory — through `commondir` when it is itself a linked worktree. */
function commonGitDir(repository: string): string | null {
  const own = gitDirOf(repository);
  if (!own) {
    return null;
  }
  try {
    return realpathSync(path.resolve(own, readFileSync(path.join(own, "commondir"), "utf8").trim()));
  } catch {
    return own;
  }
}

/**
 * A directory as the project list names one. `projects.add` resolves the chosen folder to its
 * REAL path (it stores nothing — a project is its sessions' directory), so macOS's `/var/...`
 * and `/tmp/...` come back as `/private/...` — while a renderer or an agent may still
 * name the directory the way it was chosen. Comparisons resolve the symlinks in the part that
 * exists; the part that does not exist yet (a worktree about to be made) is kept as spelled.
 */
export function realDirectory(candidate: string): string {
  return git.realPath(candidate);
}

/** Is `candidate` the project directory itself, however it is spelled? */
function isProjectDirectory(project: Pick<Project, "path">, candidate: string): boolean {
  return git.samePath(realDirectory(candidate), realDirectory(project.path));
}

/**
 * The directory an explorer root names: the project's, or the worktree's
 * when the root belongs to the project. Throws — with a sentence, not a path
 * — for anything else.
 */
export function resolveProjectRoot(
  settings: Pick<Settings, "worktreeRoot">,
  project: Pick<Project, "name" | "path">,
  root: string | null | undefined,
): string {
  if (!root) {
    return project.path;
  }
  if (!rootBelongsToProject(settings, project, root)) {
    throw new git.GitError("that directory does not belong to this project");
  }
  return isProjectDirectory(project, root) ? project.path : path.resolve(root);
}

export type ResolveInput = {
  project: Project;
  gitMode: GitMode;
  settings: Settings;
  /** The first prompt, when the caller has one: the slug is made from it. */
  name?: string | undefined;
  /**
   * An explicit directory — Settings' `New session in this worktree`. It must be
   * the project itself or one of that project's worktrees; anything else is a
   * renderer asking main to run an agent somewhere it was never shown.
   */
  cwd?: string | undefined;
  /** Existing session worktrees, including paths created by older app layouts. */
  knownWorktrees?: readonly string[];
};

/**
 * Turn a mode into a directory, creating the worktree when the mode asks for
 * one.
 *
 * Everything that can go wrong here is a `GitError`, whose message is written
 * to be read by the person who picked the mode.
 */
export async function resolveWorkspace(input: ResolveInput): Promise<Workspace> {
  const { project, gitMode, settings } = input;

  if (input.cwd) {
    return explicitWorkspace(input.cwd, input);
  }

  if (gitMode === "none") {
    return { cwd: project.path };
  }

  const info = await git.repoInfo(project.path);

  if (gitMode === "checkout") {
    // A project that is not a repository is not an error in this mode: the
    // session runs in the folder, exactly as `none` would, and the sidebar
    // shows no branch glyph because there is no branch.
    return info.branch ? { cwd: project.path, branch: info.branch } : { cwd: project.path };
  }

  if (!info.isRepository) {
    throw new git.GitError(info.problem ?? "Project is not a git repository, worktree mode unavailable");
  }

  const created = await git.createWorktree({
    repoPath: project.path,
    parentDir: projectWorktreeDir(settings, project),
    ...(input.name === undefined ? {} : { name: input.name }),
    branchPrefix: settings.branchPrefix,
    fetch: settings.fetchBeforeCreate,
  });
  return { cwd: created.path, branch: created.branch, worktreePath: created.path };
}

/**
 * `New session in this worktree`: the directory is given, and it is checked
 * against the two places it is allowed to be.
 */
async function explicitWorkspace(cwd: string, input: ResolveInput): Promise<Workspace> {
  const requested = path.resolve(cwd);
  if (!rootBelongsToProject(input.settings, input.project, requested) &&
      !input.knownWorktrees?.some(root => git.samePath(realDirectory(root), realDirectory(requested)))) {
    throw new git.GitError("that directory does not belong to this project");
  }

  // The project itself runs at the path the project list records, however it was named here.
  const isWorktree = !isProjectDirectory(input.project, requested);
  const directory = isWorktree ? requested : input.project.path;
  const info = await git.repoInfo(directory);
  return {
    cwd: directory,
    ...(info.branch ? { branch: info.branch } : {}),
    ...(isWorktree ? { worktreePath: directory } : {}),
  };
}

/**
 * Remove a session's worktree, when there is one and it is safe.
 *
 * Called on `sessions.delete` and gated on `autoDeleteWorktrees`: deleting a
 * thread is not the same decision as deleting the branch it was working on,
 * so the default is to leave the directory alone and let Settings show it.
 *
 * Never forced. A worktree with uncommitted changes stays, and the answer
 * says so — the settings page is where someone can look at it and decide.
 *
 * `abandoned` — a create that failed after making the worktree — skips the
 * setting and takes the branch too: nobody chose to keep a worktree no
 * session ever opened, and a branch still where it was cut holds nothing.
 * "Where it was cut" is the session's recorded `sessionHead`, not HEAD — a
 * branch cut from a fetched remote tip is not merged into a checkout that is
 * behind it, and `git branch -d` would keep it for that. A branch with
 * commits of its own stays; with no recorded head, `-d` decides.
 */
export async function releaseWorkspace(
  /** `projectId` is the project's directory: the repository to ask when the folder is gone. */
  session: {
    worktreePath?: string | undefined;
    branch?: string | undefined;
    projectId?: string | undefined;
    sessionHead?: string | null | undefined;
  },
  settings: Pick<Settings, "autoDeleteWorktrees">,
  options: { abandoned?: boolean } = {},
): Promise<{ removed: boolean; reason?: string }> {
  if (!session.worktreePath) {
    return { removed: false };
  }
  if (!settings.autoDeleteWorktrees && !options.abandoned) {
    return { removed: false, reason: "auto-delete is off" };
  }
  try {
    // The project's repository first: with the folder gone, the worktree's own
    // path names no repository, and the branch would be left behind.
    const primary = options.abandoned
      ? await primaryOf([session.projectId, session.worktreePath])
      : undefined;
    await git.removeWorktree(session.worktreePath, session.projectId ? { repoPath: session.projectId } : {});
    if (primary && session.branch) {
      await (session.sessionHead
        ? git.deleteBranchAtBase(primary, session.branch, session.sessionHead)
        : git.deleteMergedBranch(primary, session.branch));
    }
    return { removed: true };
  } catch (error) {
    return { removed: false, reason: error instanceof Error ? error.message : String(error) };
  }
}

/** The primary worktree of the first of `places` that is inside a repository. */
async function primaryOf(places: (string | undefined)[]): Promise<string | undefined> {
  for (const place of places) {
    if (!place) continue;
    const primary = (await git.listWorktrees(place).catch(() => [])).find((worktree) => worktree.primary)?.path;
    if (primary) return primary;
  }
  return undefined;
}
