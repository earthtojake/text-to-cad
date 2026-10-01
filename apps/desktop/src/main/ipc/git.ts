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
 * point of reviewing a turn. A session with no recorded mark resolves to
 * `unmarked`, answered with an empty status that names the missing mark —
 * never the working tree under the scope's name.
 */
import path from "node:path";

import { projects, sessions, settings } from "../db/repositories";
import { loginEnv } from "../agents/shell-env";
import * as git from "../projects/git";
import { projectWorktreeDir, projectWorktreeDirs, resolveWorkspace, type Workspace } from "../projects/workspace";
import type { IpcHandlers } from "../../shared/ipc";
import type { gitIpc, Worktree } from "../../shared/ipc/git";
import { resolveDiffScope } from "../../shared/types";
import type { GitMode, Project, Session } from "../../shared/types";
import { fsCall, rootOf } from "./explorer";
import type { IpcContext } from "./register";
import { IpcError } from "./register";

/* -------------------------------------------------------------------------- */
/* Where to run                                                                */
/* -------------------------------------------------------------------------- */

function projectOf(projectId: string): Project {
  const project = projects.get(projectId);
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

/**
 * The working directory a request is answered for.
 *
 * A session id that names no session of this project is refused, never
 * answered in the project's checkout: a review tab left open on a deleted
 * worktree session would otherwise commit — and push — its `Commit` into the
 * main checkout.
 */
function cwdFor(request: { projectId: string; sessionId?: string }): string {
  if (request.sessionId) {
    const session = sessionOf(request.projectId, request.sessionId);
    if (!session) {
      throw new IpcError("that session is no longer open");
    }
    return session.cwd;
  }
  return rootOf(request.projectId);
}

/* -------------------------------------------------------------------------- */
/* Worktrees                                                                   */
/* -------------------------------------------------------------------------- */

/**
 * A project's worktrees, as the settings page shows them.
 *
 * Only generated or session-recorded worktrees: a worktree the person
 * made themselves, somewhere else, is theirs, and a Delete button beside it
 * would be text-to-cad offering to remove something it never created.
 */
async function worktreesOf(project: Project): Promise<Worktree[]> {
  const parents = projectWorktreeDirs(settings.get(), project);
  // Every project's sessions, as Delete's refusal counts them: a session of
  // another project can be running in this one's worktree.
  const open = sessions.list();

  // Listed by the project's own repository, so a worktree in the shared
  // pre-hash folder shows here only when it is this project's.
  const shown = (await git.listWorktrees(project.path)).filter((worktree) => !worktree.primary &&
    (parents.some((parent) => git.isUnder(parent, worktree.path)) ||
      open.some(session => session.worktreePath && git.samePath(session.worktreePath, worktree.path))));
  const rows = await Promise.all(shown.map(async (worktree): Promise<Worktree> => {
    const [lastUsedAt, dirty] = await Promise.all([
      git.lastWrittenAt(worktree.path),
      // Ignored files count: removing the worktree would delete them too. A
      // folder deleted by hand has nothing left to lose — git cannot be asked
      // about it (`hasUnsavedWork` would say null and pin Delete off for good),
      // and `removeWorktree` unregisters it — so it is clean. A folder that
      // could not be read is unknown.
      git.folderGone(worktree.path).catch(() => null).then((gone) => gone === true ? false : git.hasUnsavedWork(worktree.path)),
    ]);
    return {
      path: worktree.path,
      branch: worktree.branch,
      lastUsedAt: lastUsedAt === null ? null : Math.round(lastUsedAt),
      openSessions: git.sessionsUsing(open, worktree.path).length,
      dirty,
      locked: worktree.locked,
    };
  }));
  // Newest first: the one being worked in is the one being looked for.
  return rows.sort((left, right) => (right.lastUsedAt ?? 0) - (left.lastUsedAt ?? 0));
}

/**
 * Worktrees made for a session whose row is not written yet. Between
 * `git worktree add` and `repo.upsert` a new worktree belongs to no session,
 * so without this the sweep its own creation triggers — or a concurrent
 * create's — could remove it before its session ever opened.
 */
const creating = new Map<string, number>();

/** Mark a worktree as being created; the answer unmarks it once its row exists (or its create failed). */
export function markCreating(worktreePath: string): () => void {
  creating.set(worktreePath, (creating.get(worktreePath) ?? 0) + 1);
  let done = false;
  return () => {
    if (done) return;
    done = true;
    const left = (creating.get(worktreePath) ?? 1) - 1;
    if (left > 0) creating.set(worktreePath, left);
    else creating.delete(worktreePath);
  };
}

/**
 * Enforce the keep limit for one project (Settings › Auto-delete).
 *
 * Called after a worktree is created rather than on a timer: the limit is
 * about how many pile up, and the moment one more appears is the moment to
 * check. Every session's directories are handed to the sweep as protected —
 * every project's, not only this one's: a session whose *project* is one of
 * these worktree folders, or that runs somewhere inside one, is using it just
 * the same (the rule `releaseWorkspace` and `removeWorktree` already keep).
 */
export async function pruneProjectWorktrees(project: Project): Promise<void> {
  const stored = settings.get();
  if (!stored.autoDeleteWorktrees) {
    return;
  }
  await git
    .pruneWorktrees({
      repoPath: project.path,
      parentDir: projectWorktreeDirs(stored, project),
      keep: stored.worktreeKeepLimit,
      // Read again before each removal, so a create that began after the
      // sweep did is protected too.
      protectedPaths: () => [
        // An archived thread is not open: it does not hold a worktree.
        ...sessions.list().filter((session) => !session.archived).flatMap((session) =>
          [session.cwd, session.projectId, session.worktreePath].filter((root): root is string => Boolean(root))),
        ...creating.keys(),
      ],
    })
    .catch(() => undefined);
}

/** Each created worktree's unmark and project, until its session row is written. */
const settling = new Map<Workspace, { done: () => void; project: Project }>();

/**
 * P7: the git mode as a directory, and a worktree when the mode asks (plan
 * §9) — `SessionManager`'s `workspace` dependency.
 *
 * A new worktree has no session row yet — that is written after this
 * returns — so it is marked as being created until `sessionWorkspaceSettled`.
 * The keep-limit sweep is not run here: dating every candidate worktree is
 * git and file-system work the session's start has no reason to wait for.
 */
export async function sessionWorkspace(input: {
  projectId: string;
  gitMode: GitMode;
  name?: string | undefined;
  cwd?: string | undefined;
}): Promise<Workspace> {
  const project = projects.get(input.projectId);
  if (!project) {
    throw new Error("that project is no longer open");
  }
  const workspace = await resolveWorkspace({
    project,
    gitMode: input.gitMode,
    settings: settings.get(),
    name: input.name,
    cwd: input.cwd,
    knownWorktrees: sessions.list(project.id).flatMap(session => session.worktreePath ? [session.worktreePath] : []),
  });
  if (workspace.worktreePath) {
    settling.set(workspace, { done: markCreating(workspace.worktreePath), project });
  }
  return workspace;
}

/**
 * The row for `workspace` is written (or its create failed): the worktree
 * is a session's now, or nobody's. One more worktree exists, so this is the
 * moment the keep limit can be exceeded, and the sweep starts — unawaited,
 * after the row, so the new one is protected as a session's directory and
 * the session's start never waits on it.
 */
export function sessionWorkspaceSettled(workspace: Workspace): void {
  const entry = settling.get(workspace);
  if (!entry) {
    return;
  }
  settling.delete(workspace);
  entry.done();
  void pruneProjectWorktrees(entry.project);
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
        const parents = projectWorktreeDirs(settings.get(), project);
        const worktrees = info.isRepository
          ? (await git.listWorktrees(project.path)).filter(
              (worktree) => !worktree.primary && (parents.some((dir) => git.isUnder(dir, worktree.path)) ||
                sessions.list(project.id).some(session => session.worktreePath && git.samePath(session.worktreePath, worktree.path))),
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
        // A push that failed after its commit leaves a clean tree and commits
        // the remote lacks; asking again with `push` sends them rather than
        // failing on "nothing to commit".
        if (push) {
          const state = await git.pushState(cwd);
          if (!state.dirty && state.ahead > 0) {
            await git.push(cwd);
            // Said aloud: a message typed for files that were gone by now was not used.
            return { sha: (await git.head(cwd)) ?? "", pushedOnly: true, pushed: state.ahead };
          }
        }
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
        const requested = path.resolve(target);
        const parents = projectWorktreeDirs(settings.get(), project);
        const recorded = sessions.list(project.id).some(session =>
          session.worktreePath && git.samePath(session.worktreePath, requested));
        // Under one of the project's folders (or recorded by one of its
        // sessions) AND a linked worktree of the project's own repository: the
        // pre-hash folder is shared by every same-named project, so the folder
        // alone does not say whose it is.
        const own = (await git.listWorktrees(project.path)).some(worktree =>
          !worktree.primary && git.samePath(worktree.path, requested));
        if (!own || (!parents.some((parent) => git.isUnder(parent, requested)) && !recorded)) {
          throw new IpcError("that worktree does not belong to this project");
        }
        // Not even forced: pulling the directory out from under a session
        // leaves an agent running in a folder that no longer exists.
        const using = git.sessionsUsing(sessions.list(), requested);
        if (using.length > 0) {
          throw new IpcError(
            `${using.length} session${using.length === 1 ? " is" : "s are"} still using that worktree`,
          );
        }
        await git.removeWorktree(requested, { repoPath: project.path, ...(force === undefined ? {} : { force }) });
      }),
  },
} satisfies IpcHandlers<typeof gitIpc, IpcContext>;
