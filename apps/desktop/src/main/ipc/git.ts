/**
 * `git.*`: the review tab's reads, the commit and push behind its popover, and
 * the worktrees Settings › Git & Worktrees lists (plan §9).
 *
 * Two resolutions happen here and nowhere else.
 *
 * **Which directory.** Every request names a project; one that also names a
 * session is answered for *that session's* working directory. A thread in
 * `worktree` mode is not looking at the project's checkout — it is looking at
 * its own, and a review that showed the checkout's diff would be showing
 * another thread's work.
 *
 * **Which revision.** The `turn` and `session` scopes are the two revisions
 * recorded on the session row (`src/main/acp/sessions.ts`): where the working
 * tree was when the newest turn began, and when the session was created. They
 * become an open-ended `range`, which git measures against the working tree —
 * so an edit the agent has not committed is in the answer, which is the whole
 * point of reviewing a turn.
 */
import path from "node:path";

import { projects, sessions, settings } from "../db/repositories";
import { loginEnv } from "../agents/shell-env";
import * as git from "../projects/git";
import { projectWorktreeDir } from "../projects/workspace";
import type { IpcHandlers } from "../../shared/ipc";
import type { gitIpc, Worktree } from "../../shared/ipc/git";
import { resolveDiffScope } from "../../shared/types";
import type { Project, Session } from "../../shared/types";
import { fsCall, rootOf } from "./explorer";
import type { IpcContext } from "./register";
import { IpcError } from "./register";

/* -------------------------------------------------------------------------- */
/* Where to run                                                                */
/* -------------------------------------------------------------------------- */

function projectOf(projectId: string): Project {
  const project = projects.list().find((candidate) => candidate.id === projectId);
  if (!project) {
    throw new IpcError("that project is no longer open");
  }
  return project;
}

/**
 * The session a request names, checked against the project it claims.
 *
 * The pair is checked rather than trusted: a session id is a string from the
 * renderer, and answering a `git.commit` for a session in a different project
 * would commit in a directory the caller never asked about.
 */
function sessionOf(projectId: string, sessionId: string | undefined): Session | null {
  if (!sessionId) {
    return null;
  }
  const session = sessions.get(sessionId);
  if (!session || session.projectId !== projectId) {
    return null;
  }
  return session;
}

/** The working directory a request is answered for. */
function cwdFor(request: { projectId: string; sessionId?: string }): string {
  const session = sessionOf(request.projectId, request.sessionId);
  return session?.cwd ?? rootOf(request.projectId);
}

/* -------------------------------------------------------------------------- */
/* Worktrees                                                                   */
/* -------------------------------------------------------------------------- */

/**
 * A project's worktrees, as the settings page shows them.
 *
 * Only the ones under this project's worktree directory: a worktree the person
 * made themselves, somewhere else, is theirs, and a Delete button beside it
 * would be Hardcore offering to remove something it never created.
 */
async function worktreesOf(project: Project): Promise<Worktree[]> {
  const fs = await import("node:fs/promises");
  const parent = projectWorktreeDir(settings.get(), project);
  const open = sessions.list(project.id);

  const rows: Worktree[] = [];
  for (const worktree of await git.listWorktrees(project.path)) {
    if (worktree.primary || !git.isUnder(parent, worktree.path)) {
      continue;
    }
    const stat = await fs.stat(worktree.path).catch(() => null);
    rows.push({
      path: worktree.path,
      branch: worktree.branch,
      lastUsedAt: stat ? Math.round(stat.mtimeMs) : null,
      openSessions: open.filter((session) => git.samePath(session.cwd, worktree.path)).length,
      dirty: await git.isDirty(worktree.path),
      locked: worktree.locked,
    });
  }
  // Newest first: the one being worked in is the one being looked for.
  return rows.sort((left, right) => (right.lastUsedAt ?? 0) - (left.lastUsedAt ?? 0));
}

/**
 * Enforce the keep limit for one project (Settings › Auto-delete).
 *
 * Called after a worktree is created rather than on a timer: the limit is
 * about how many pile up, and the moment one more appears is the moment to
 * check. Worktrees with an open session are handed to the sweep as protected.
 */
export async function pruneProjectWorktrees(project: Project): Promise<void> {
  const stored = settings.get();
  if (!stored.autoDeleteWorktrees) {
    return;
  }
  await git
    .pruneWorktrees({
      repoPath: project.path,
      parentDir: projectWorktreeDir(stored, project),
      keep: stored.worktreeKeepLimit,
      protectedPaths: sessions.list(project.id).map((session) => session.cwd),
    })
    .catch(() => undefined);
}

/* -------------------------------------------------------------------------- */
/* Handlers                                                                    */
/* -------------------------------------------------------------------------- */

export const gitHandlers = {
  git: {
    projectInfo: ({ projectId }) =>
      fsCall(async () => {
        const project = projectOf(projectId);
        const info = await git.repoInfo(project.path);
        const parent = projectWorktreeDir(settings.get(), project);
        const worktrees = info.isRepository
          ? (await git.listWorktrees(project.path)).filter(
              (worktree) => !worktree.primary && git.isUnder(parent, worktree.path),
            )
          : [];
        return {
          isRepository: info.isRepository,
          branch: info.branch,
          upstream: info.upstream,
          defaultBranch: info.defaultBranch,
          dirty: info.dirty,
          detached: info.detached,
          unborn: info.unborn,
          hasRemote: info.hasRemote,
          hasGh: (await git.ghAvailable(await loginEnv())) !== null,
          worktreeCount: worktrees.length,
          worktreeDir: parent,
        };
      }),

    status: ({ projectId, sessionId, scope }) =>
      fsCall(() =>
        git.status(
          cwdFor({ projectId, ...(sessionId ? { sessionId } : {}) }),
          resolveDiffScope(scope, sessionOf(projectId, sessionId)),
        ),
      ),

    fileDiff: ({ projectId, sessionId, path: target, scope }) =>
      fsCall(() =>
        git.fileDiff(
          cwdFor({ projectId, ...(sessionId ? { sessionId } : {}) }),
          target,
          resolveDiffScope(scope, sessionOf(projectId, sessionId)),
        ),
      ),

    unifiedDiff: ({ projectId, sessionId, path: target, scope }) =>
      fsCall(async () => ({
        patch: await git.unifiedDiff(
          cwdFor({ projectId, ...(sessionId ? { sessionId } : {}) }),
          target,
          resolveDiffScope(scope, sessionOf(projectId, sessionId)),
        ),
      })),

    commit: ({ projectId, sessionId, message, push }) =>
      fsCall(async () => {
        const cwd = cwdFor({ projectId, ...(sessionId ? { sessionId } : {}) });
        const result = await git.commitAll(cwd, message);
        if (push) {
          await git.push(cwd);
        }
        return result;
      }),

    pullRequest: ({ projectId, sessionId, title, body }) =>
      fsCall(async () => {
        const cwd = cwdFor({ projectId, ...(sessionId ? { sessionId } : {}) });
        const stored = settings.get();
        return git.createPullRequest(cwd, {
          title,
          // The settings' instructions are guidance for the person writing the
          // description, so they are a placeholder in the UI, not something
          // appended to a body they wrote. Only what they typed is sent.
          body: body ?? "",
          draft: stored.draftPullRequests,
          env: await loginEnv(),
        });
      }),

    worktrees: ({ projectId }) => fsCall(() => worktreesOf(projectOf(projectId))),

    removeWorktree: ({ projectId, path: target, force }) =>
      fsCall(async () => {
        const project = projectOf(projectId);
        const parent = projectWorktreeDir(settings.get(), project);
        if (!git.isUnder(parent, path.resolve(target))) {
          throw new IpcError("that worktree does not belong to this project");
        }
        await git.removeWorktree(target, force === undefined ? {} : { force });
      }),
  },
} satisfies IpcHandlers<typeof gitIpc, IpcContext>;
