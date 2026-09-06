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
 *     ~/.hardcore/worktrees/<project-name>/<slug>
 *
 * with the branch `hardcore/<slug>`. Both the root and the prefix are
 * settings. The slug comes from the session's first prompt when there is one,
 * because that is what the sidebar calls the thread — a person looking at
 * `~/.hardcore/worktrees/text-to-cad/model-the-wrist` knows which thread it
 * belongs to without opening anything.
 *
 * The directory is also the *identity* of the session as far as the agent's
 * own store is concerned: both `codex resume` and `claude --resume` key their
 * threads by cwd, so a worktree is what makes a Hardcore session resumable
 * from a terminal later.
 */
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
  return settings.worktreeRoot ?? path.join(os.homedir(), ".hardcore", "worktrees");
}

/** `<root>/<project>` — one folder per project, whichever agent made it. */
export function projectWorktreeDir(
  settings: Pick<Settings, "worktreeRoot">,
  project: Pick<Project, "name" | "path">,
): string {
  // The directory's basename is the fallback, not the display name: a project
  // renamed to "Robot arm (v2)" must not move every worktree it already has.
  const name = git.slugify(project.name) || git.slugify(path.basename(project.path)) || "project";
  return path.join(worktreeRoot(settings), name);
}

export type ResolveInput = {
  project: Project;
  gitMode: GitMode;
  settings: Settings;
  /** The first prompt, when the caller has one: the slug is made from it. */
  name?: string | undefined;
  /**
   * An explicit directory — Settings' `New chat in this worktree`. It must be
   * the project itself or one of that project's worktrees; anything else is a
   * renderer asking main to run an agent somewhere it was never shown.
   */
  cwd?: string | undefined;
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
    throw new git.GitError("Project is not a git repository, worktree mode unavailable");
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
 * `New chat in this worktree`: the directory is given, and it is checked
 * against the two places it is allowed to be.
 */
async function explicitWorkspace(cwd: string, input: ResolveInput): Promise<Workspace> {
  const requested = path.resolve(cwd);
  const parent = projectWorktreeDir(input.settings, input.project);
  const allowed =
    git.samePath(requested, input.project.path) || git.isUnder(parent, requested);
  if (!allowed) {
    throw new git.GitError("that directory does not belong to this project");
  }

  const info = await git.repoInfo(requested);
  const isWorktree = !git.samePath(requested, input.project.path);
  return {
    cwd: requested,
    ...(info.branch ? { branch: info.branch } : {}),
    ...(isWorktree ? { worktreePath: requested } : {}),
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
 */
export async function releaseWorkspace(
  session: { worktreePath?: string | undefined },
  settings: Pick<Settings, "autoDeleteWorktrees">,
): Promise<{ removed: boolean; reason?: string }> {
  if (!session.worktreePath) {
    return { removed: false };
  }
  if (!settings.autoDeleteWorktrees) {
    return { removed: false, reason: "auto-delete is off" };
  }
  try {
    await git.removeWorktree(session.worktreePath);
    return { removed: true };
  } catch (error) {
    return { removed: false, reason: error instanceof Error ? error.message : String(error) };
  }
}
