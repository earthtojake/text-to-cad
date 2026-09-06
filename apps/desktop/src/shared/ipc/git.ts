/**
 * `git.*`: what the review tab reads and what the git modes need (plan §9).
 *
 * Its own branch, split out of `./explorer.ts` when P7 landed: the review's
 * reads and the worktree machinery are the same subject, and the explorer's
 * branch is already the biggest in the contract.
 *
 * Every request names a **project**, and optionally a **session**. The project
 * is how main turns a path into a real one; the session, when given, is what
 * moves the whole answer into that session's working directory — a thread in
 * `worktree` mode is not reviewing the project's checkout, it is reviewing its
 * own (plan §9).
 */
import { z } from "zod";

// `DiffScope` is a domain type, not a wire type: the review tab stores it and
// the session row's marks resolve two of its cases (src/shared/types.ts).
import { DiffScopeSchema } from "../types";
import { invoke } from "./define";

export type { DiffScope } from "../types";

/* -------------------------------------------------------------------------- */
/* Shapes                                                                      */
/* -------------------------------------------------------------------------- */

export const ChangeStatusSchema = z.enum([
  "added",
  "modified",
  "deleted",
  "renamed",
  "untracked",
]);
export type ChangeStatus = z.infer<typeof ChangeStatusSchema>;

export const ChangedFileSchema = z.object({
  path: z.string(),
  oldPath: z.string().optional(),
  status: ChangeStatusSchema,
  insertions: z.number(),
  deletions: z.number(),
  binary: z.boolean(),
});
export type ChangedFile = z.infer<typeof ChangedFileSchema>;

export const GitStatusSchema = z.object({
  isRepository: z.boolean(),
  branch: z.string().nullable(),
  unborn: z.boolean(),
  ahead: z.number(),
  behind: z.number(),
  files: z.array(ChangedFileSchema),
  insertions: z.number(),
  deletions: z.number(),
});
export type GitStatus = z.infer<typeof GitStatusSchema>;

export const FileDiffSchema = z.object({
  path: z.string(),
  oldPath: z.string().optional(),
  status: ChangeStatusSchema,
  insertions: z.number(),
  deletions: z.number(),
  binary: z.boolean(),
  before: z.string().nullable(),
  after: z.string().nullable(),
});
export type FileDiff = z.infer<typeof FileDiffSchema>;

/**
 * A project's git shape, for the composer's mode chip and the settings page.
 *
 * One answer rather than four channels: the chip needs all of it before it can
 * draw, and "is this a repository, on what branch, tracking what, and can it
 * be branched from" is one question asked four ways.
 */
export const ProjectGitInfoSchema = z.object({
  isRepository: z.boolean(),
  branch: z.string().nullable(),
  upstream: z.string().nullable(),
  defaultBranch: z.string().nullable(),
  dirty: z.boolean(),
  detached: z.boolean(),
  /** No commits yet, so `worktree` mode has nothing to branch from. */
  unborn: z.boolean(),
  hasRemote: z.boolean(),
  /** `gh` is on the PATH, so `Create pull request` can be offered. */
  hasGh: z.boolean(),
  /** Hardcore's worktrees for this project (never the checkout itself). */
  worktreeCount: z.number().int().nonnegative(),
  /** `<worktree root>/<project>`, expanded — what Settings prints. */
  worktreeDir: z.string(),
});
export type ProjectGitInfo = z.infer<typeof ProjectGitInfoSchema>;

/** One row of Settings › Git & Worktrees' per-project card. */
export const WorktreeSchema = z.object({
  path: z.string(),
  branch: z.string().nullable(),
  /** Directory mtime: when someone last wrote in it. Null when it is gone. */
  lastUsedAt: z.number().nullable(),
  /** Sessions still pointing at it — never swept, and a warning before Delete. */
  openSessions: z.number().int().nonnegative(),
  /** Uncommitted work: `Delete` refuses rather than discarding it. */
  dirty: z.boolean(),
  locked: z.boolean(),
});
export type Worktree = z.infer<typeof WorktreeSchema>;

/* -------------------------------------------------------------------------- */
/* The contract                                                                */
/* -------------------------------------------------------------------------- */

const InProject = z.object({
  projectId: z.string().min(1),
  /**
   * Answer for this session's working directory instead of the project's, and
   * resolve the `turn` and `session` scopes against its recorded marks.
   */
  sessionId: z.string().optional(),
});
const AtPath = InProject.extend({ path: z.string() });

export const gitIpc = {
  git: {
    /** Repository, branch, upstream, worktrees — what the mode chip needs. */
    projectInfo: invoke(
      z.object({ projectId: z.string().min(1) }),
      ProjectGitInfoSchema,
    ),

    status: invoke(InProject.extend({ scope: DiffScopeSchema.optional() }), GitStatusSchema),
    /** Both sides of one file, for the inline diff editor. */
    fileDiff: invoke(AtPath.extend({ scope: DiffScopeSchema.optional() }), FileDiffSchema),
    /** The unified patch, for copying out of a review. */
    unifiedDiff: invoke(
      AtPath.extend({ scope: DiffScopeSchema.optional() }),
      z.object({ patch: z.string() }),
    ),
    commit: invoke(
      InProject.extend({ message: z.string().min(1), push: z.boolean().optional() }),
      z.object({ sha: z.string() }),
    ),
    /**
     * `gh pr create`, pushing first when the branch has no upstream. Answers
     * with the URL rather than opening it: whether a link opens in a browser
     * is the renderer's decision.
     */
    pullRequest: invoke(
      InProject.extend({ title: z.string().min(1), body: z.string().optional() }),
      z.object({ url: z.string() }),
    ),

    /** Hardcore's worktrees for a project, newest first. */
    worktrees: invoke(
      z.object({ projectId: z.string().min(1) }),
      z.array(WorktreeSchema),
    ),
    /** Refuses a dirty worktree unless `force`; never removes the checkout. */
    removeWorktree: invoke(
      z.object({
        projectId: z.string().min(1),
        path: z.string().min(1),
        force: z.boolean().optional(),
      }),
      z.void(),
    ),
  },
} as const;
