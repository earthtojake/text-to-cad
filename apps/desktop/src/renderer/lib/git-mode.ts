/**
 * The git mode as the UI shows it (plan §9): the sidebar's trailing glyph, the
 * composer's chip, and which modes a project can actually offer.
 *
 * A module rather than a component, because two features need the same answer
 * and neither owns it: the sidebar draws the glyph on a session row (P2), the
 * composer draws the chip above the transcript (P2), and both have to agree
 * with what main did when the session was created (P7).
 *
 * Nothing here talks to IPC except `useProjectGitInfo`, which is a read of one
 * channel. The glyph functions are pure so they can be unit-tested without a
 * renderer.
 */
import { useEffect, useState } from "react";

import type { ProjectGitInfo } from "@shared/ipc/git";
import type { GitMode, Session } from "@shared/types";

/* -------------------------------------------------------------------------- */
/* The glyph                                                                   */
/* -------------------------------------------------------------------------- */

/**
 * Which trailing glyph a session row gets (plan §2, Codex's sidebar).
 *
 *   - `worktree`  the thread runs in its own worktree;
 *   - `branch`    the thread runs in the checkout, on a branch that is not the
 *                 project's default — worth saying, because a commit there
 *                 lands somewhere other than where the person is looking;
 *   - `null`      everything else. A thread on the default branch, or in a
 *                 folder that is not a repository, has nothing to warn about,
 *                 and a glyph on every row is a glyph that says nothing.
 *
 * `running` is not handled here: a spinner replaces the glyph while a turn is
 * in flight, and that is the row's business, not git's.
 */
export type GitGlyph = "worktree" | "branch" | null;

export function gitGlyphFor(
  session: Pick<Session, "gitMode" | "branch">,
  project?: Pick<ProjectGitInfo, "branch" | "defaultBranch"> | null,
): GitGlyph {
  if (session.gitMode === "worktree") {
    return "worktree";
  }
  if (session.gitMode !== "checkout" || !session.branch) {
    return null;
  }
  // The remote's default branch when there is one, and otherwise the branch
  // the project is on right now. A repository with no remote has no "default"
  // to speak of, and in a checkout session those two are the same branch
  // anyway — so the glyph appears exactly when the thread is somewhere the
  // person is not looking, which is the only time it says anything.
  const ordinary = project?.defaultBranch ?? project?.branch ?? null;
  return ordinary && session.branch === ordinary ? null : "branch";
}

/** What the glyph's tooltip says. */
export function gitGlyphLabel(session: Pick<Session, "gitMode" | "branch">): string {
  if (session.gitMode === "worktree") {
    return session.branch ? `Worktree · ${session.branch}` : "Worktree";
  }
  return session.branch ?? "";
}

/* -------------------------------------------------------------------------- */
/* The chip                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * What a person chooses between: **Local** or **New worktree**. Two choices,
 * not three — "the project's own folder" and "a folder of its own" is the
 * whole decision, and whether that folder happens to be a git checkout is a
 * fact about the project, not a third option to weigh (`localGitMode`).
 *
 * `GitMode` keeps its three values because main's `projects/workspace.ts`
 * genuinely does three different things with a directory; `none` and
 * `checkout` are simply never offered as a pair.
 */
export const GIT_MODE_LABELS: Record<GitMode, string> = {
  none: "Local",
  checkout: "Local",
  worktree: "New worktree",
};

/** Which `GitMode` "Local" is here: the checkout, or a folder that has none. */
export function localGitMode(info: ProjectGitInfo | null): GitMode {
  return info && !info.isRepository ? "none" : "checkout";
}

/**
 * The mode a session would actually run in. Anything but an available
 * `worktree` is Local — a mode a project cannot offer is not a mode, and the
 * chip disables it with the reason rather than starting a session that fails.
 */
export function resolveGitMode(mode: GitMode, info: ProjectGitInfo | null): GitMode {
  if (mode === "worktree" && gitModeAvailability("worktree", info).available) {
    return "worktree";
  }
  return localGitMode(info);
}

/**
 * Whether a project can offer a mode, and why not when it cannot.
 *
 * Local is always available: a project is a directory, and git is optional
 * (plan §9) — without a repository it is `none`, with one it is `checkout`.
 * Only `worktree` can genuinely fail, and it fails for two different reasons
 * that need two different sentences.
 */
export function gitModeAvailability(
  mode: GitMode,
  info: ProjectGitInfo | null,
): { available: boolean; reason?: string } {
  if (mode !== "worktree" || !info) {
    return { available: true };
  }
  if (!info.isRepository) {
    return { available: false, reason: "Project is not a git repository, worktree mode unavailable" };
  }
  if (info.unborn) {
    return { available: false, reason: "This repository has no commits yet to branch from" };
  }
  return { available: true };
}

/* -------------------------------------------------------------------------- */
/* The data                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * A project's git shape, refreshed when the project changes.
 *
 * Deliberately not a store: it is one read of one channel, nothing pushes it,
 * and the two components that want it want it at different times. `null` while
 * it loads, and `null` forever for a project that has gone — callers treat
 * both as "assume the mode is fine", which is what the availability rules
 * above already do.
 */
export function useProjectGitInfo(projectId: string | null | undefined): ProjectGitInfo | null {
  const [info, setInfo] = useState<ProjectGitInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    const settle = (next: ProjectGitInfo | null) => {
      if (!cancelled) {
        setInfo(next);
      }
    };
    // Resolved rather than returned early for a null project: an effect that
    // sets state synchronously in its own body cascades a render, and the
    // answer for "no project" is the same `null` the failure path writes.
    void (projectId
      ? window.hardcore.git.projectInfo({ projectId })
      : Promise.resolve(null)
    )
      .then(settle)
      .catch(() => settle(null));
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return info;
}
