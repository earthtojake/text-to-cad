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
  /** Why there is no repository, when it is more than "a folder": git missing, the folder gone, dubious ownership. */
  problem: z.string().optional(),
  branch: z.string().nullable(),
  unborn: z.boolean(),
  ahead: z.number(),
  behind: z.number(),
  files: z.array(ChangedFileSchema),
  insertions: z.number(),
  deletions: z.number(),
  /**
   * Files in the working tree — what `Commit` takes — whatever the scope. It
   * rides on every answer so the review's commit button needs no second read.
   */
  workingFiles: z.number().int().nonnegative(),
  /**
   * Where the directory asked about sits in the repository, `/`-separated with
   * a trailing slash (`app/`), or empty at its top. `files` name paths from
   * the repository's top; the explorer's watcher names them from the project
   * (or worktree) the review reads in, and this is the difference.
   */
  prefix: z.string().optional(),
  /**
   * Set when the scope asked for was `Last turn` or `This session` and the
   * session has no recorded revision for it. `files` is then empty — not the
   * working tree — and the review says why rather than "No changes".
   */
  unmarked: z.enum(["turn", "session"]).optional(),
  /**
   * A session scope in a repository with no commits yet. No mark can exist
   * there, and every change is new since the repository began, so `files` is
   * the working tree and the review says it is measuring from the start.
   */
  fromStart: z.literal(true).optional(),
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
  /** Why there is no repository, when it is more than "a folder": git missing, the folder gone, dubious ownership. */
  problem: z.string().optional(),
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
  /** text-to-cad's worktrees for this project (never the checkout itself). */
  worktreeCount: z.number().int().nonnegative(),
  /** `<worktree root>/<project>`, expanded — what Settings prints. */
  worktreeDir: z.string(),
});
export type ProjectGitInfo = z.infer<typeof ProjectGitInfoSchema>;

/** One row of Settings › Git and worktrees' per-project card. */
export const WorktreeSchema = z.object({
  path: z.string(),
  branch: z.string().nullable(),
  /** The newest file mtime in it (`lastWrittenAt`): when someone last wrote in it. Null when it is gone. */
  lastUsedAt: z.number().nullable(),
  /** Sessions still pointing at it — never swept, and a warning before Delete. */
  openSessions: z.number().int().nonnegative(),
  /**
   * Uncommitted changes or ignored files: `Delete` refuses rather than
   * discarding them. Null when git could not check — shown as unknown, and
   * kept like dirty.
   */
  dirty: z.boolean().nullable(),
  /**
   * Work only this checkout holds although its files are clean: commits on a
   * detached HEAD no branch reaches, or a merge or rebase left half done.
   * Kept like dirty; null when git could not check.
   */
  stranded: z.boolean().nullable(),
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
/**
 * A repository-relative path: never absolute, never climbing out with `..`.
 * Main resolves it again against the repository after realpath; this is the
 * first lock on the same door.
 */
const RepositoryPath = z
  .string()
  .min(1)
  .refine(
    (value) => !value.includes("\0") && !/^(?:[\\/]|[A-Za-z]:)/.test(value) && !value.split(/[\\/]/).includes(".."),
    { message: "path must be relative to the repository" },
  );
const AtPath = InProject.extend({ path: RepositoryPath });

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
      // Empty only for a push of commits already made (main refuses an empty commit message).
      InProject.extend({ message: z.string(), push: z.boolean().optional() }),
      // `pushedOnly`: the tree was clean by the time the request arrived, so nothing was
      // committed and only the `pushed` commits already made were sent.
      z.object({ sha: z.string(), pushedOnly: z.boolean().optional(), pushed: z.number().optional() }),
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

    /** text-to-cad's worktrees for a project, newest first. */
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
