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

import type { GitMode, Session } from "@shared/types";
import type { ProjectGitInfo } from "@shared/ipc/git";

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
  defaultBranch?: string | null,
): GitGlyph {
  if (session.gitMode === "worktree") {
    return "worktree";
  }
  if (session.gitMode !== "checkout" || !session.branch) {
    return null;
  }
  // Without a default to compare against, any branch is worth naming: the
  // alternative is hiding the one piece of information the glyph carries
  // because the project's info has not loaded yet.
  return defaultBranch && session.branch === defaultBranch ? null : "branch";
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

export const GIT_MODE_LABELS: Record<GitMode, string> = {
  none: "Plain directory",
  checkout: "Current branch",
  worktree: "New worktree",
};

/**
 * Whether a project can offer a mode, and why not when it cannot.
 *
 * `none` is always available: a project is a directory, and git is optional
 * (plan §9). `checkout` needs a repository only to have a branch to name — a
 * folder without one still runs, so it is offered too, and the chip simply has
 * no branch to print. Only `worktree` can genuinely fail, and it fails for two
 * different reasons that need two different sentences.
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

/** The chip's text: `text-to-cad · hardcore/model-the-wrist`, Codex-style. */
export function gitModeSummary(
  mode: GitMode,
  info: ProjectGitInfo | null,
  session?: Pick<Session, "branch" | "gitMode"> | null,
): string {
  if (session) {
    return session.branch ?? GIT_MODE_LABELS[session.gitMode];
  }
  if (mode === "checkout" && info?.branch) {
    return info.branch;
  }
  return GIT_MODE_LABELS[mode];
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
