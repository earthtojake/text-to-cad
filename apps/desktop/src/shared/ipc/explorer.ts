/**
 * The explorer's half of the IPC contract: the filesystem behind the file tab,
 * the ptys behind the terminal tabs. The review tab's git reads are their own
 * branch (`./git.ts`).
 *
 * It lives in its own file rather than in `index.ts` because it is the largest
 * branch in the contract and it belongs to one phase (P3). `index.ts` spreads
 * it in; nothing else there knows what is inside.
 *
 * Every request that names a path also names the project it is relative to.
 * Main resolves the pair and refuses anything outside that project's root —
 * a path on its own would be a request to read any file on the machine.
 */
import { z } from "zod";

import { ExplorerTabSchema } from "../types";
import { invoke } from "./define";

/* -------------------------------------------------------------------------- */
/* Shapes                                                                      */
/* -------------------------------------------------------------------------- */

/** Which renderer a file selects (`src/main/explorer/fs.ts` decides). */
export const FileKindSchema = z.enum(["text", "image", "pdf", "cad", "binary"]);
export type FileKind = z.infer<typeof FileKindSchema>;

export const DirEntrySchema = z.object({
  /** Project-root-relative, POSIX separators. */
  path: z.string(),
  name: z.string(),
  kind: z.enum(["file", "directory"]),
  size: z.number(),
  modifiedAt: z.number(),
  symlink: z.boolean(),
});
export type DirEntry = z.infer<typeof DirEntrySchema>;

export const FileStatSchema = z.object({
  path: z.string(),
  name: z.string(),
  kind: z.enum(["file", "directory"]),
  size: z.number(),
  modifiedAt: z.number(),
  fileKind: FileKindSchema,
  mime: z.string(),
  extension: z.string(),
});
export type FileStat = z.infer<typeof FileStatSchema>;

export const TextFileSchema = z.object({
  path: z.string(),
  content: z.string(),
  /** Content hash. A save sends it back so a stale write can be refused. */
  revision: z.string(),
  modifiedAt: z.number(),
  size: z.number(),
  truncated: z.boolean(),
});

export const BinaryFileSchema = z.object({
  path: z.string(),
  mime: z.string(),
  size: z.number(),
  dataUrl: z.string(),
});

export const FileChangeSchema = z.object({
  path: z.string(),
  kind: z.enum(["added", "changed", "removed"]),
  directory: z.boolean(),
});
export type FileChange = z.infer<typeof FileChangeSchema>;

export const TerminalInfoSchema = z.object({
  id: z.string(),
  cwd: z.string(),
  shell: z.string(),
  cols: z.number(),
  rows: z.number(),
  exitCode: z.number().nullable(),
});
export type TerminalInfo = z.infer<typeof TerminalInfoSchema>;

/* -------------------------------------------------------------------------- */
/* The contract                                                                */
/* -------------------------------------------------------------------------- */

const InProject = z.object({ projectId: z.string().min(1) });
/**
 * A project and, optionally, one of its worktrees as the root (plan §9). Main
 * resolves the pair: no `root` is the project directory; a `root` has to be
 * the project itself or a directory under its worktree folder, and anything
 * else is refused before a path is read.
 */
const InRoot = InProject.extend({ root: z.string().optional() });
const AtPath = InRoot.extend({ path: z.string() });

/** What `explorer.exists` answers per path: what is there, or nothing. */
export const PathKindSchema = z.enum(["file", "directory"]).nullable();
export type PathKind = z.infer<typeof PathKindSchema>;

export const explorerIpc = {
  explorer: {
    /** One directory's children. `path` is `""` for the project root. */
    list: invoke(
      AtPath.extend({ includeIgnored: z.boolean().optional() }),
      z.array(DirEntrySchema),
    ),
    /** Every file path under a directory, for the tree's fuzzy filter. */
    paths: invoke(
      AtPath.extend({ limit: z.number().int().positive().max(100_000).optional() }),
      z.object({ paths: z.array(z.string()), truncated: z.boolean() }),
    ),
    stat: invoke(AtPath, FileStatSchema),
    /**
     * Which of `paths` exist under the root, in one round trip. The
     * transcript asks this for every path-shaped token in a message before
     * drawing it as a link (`features/session/links`); one call per message
     * rather than one per token.
     */
    exists: invoke(
      InRoot.extend({ paths: z.array(z.string()).max(500) }),
      z.record(z.string(), PathKindSchema),
    ),
    readText: invoke(AtPath, TextFileSchema),
    writeText: invoke(
      AtPath.extend({
        content: z.string(),
        /** The revision the editor loaded; a mismatch is refused. */
        expectedRevision: z.string().optional(),
      }),
      TextFileSchema,
    ),
    /** Images and PDFs, as a `data:` URL the renderer can put in a `src`. */
    readBinary: invoke(AtPath, BinaryFileSchema),
    /** The absolute path, for the breadcrumb's copy action and `Open ▾`. */
    absolutePath: invoke(AtPath, z.object({ path: z.string() })),
    /** Open a file in the OS's default application for its type. */
    openDefault: invoke(AtPath, z.void()),

    /** Start (or join) the root's watcher. Refcounted in main. */
    watch: invoke(InRoot, z.void()),
    unwatch: invoke(InRoot, z.void()),

    /** The persisted tab strip for a project (the `explorer_tabs` table). */
    loadTabs: invoke(InProject, z.array(ExplorerTabSchema)),
    saveTabs: invoke(InProject.extend({ tabs: z.array(ExplorerTabSchema) }), z.void()),
  },

  terminal: {
    create: invoke(
      InProject.extend({
        /**
         * Defaults to the project root; a tab opened while a worktree
         * session is active passes that worktree. Checked like a root: the
         * project or one of its worktrees, nothing else.
         */
        cwd: z.string().optional(),
        cols: z.number().int().positive().optional(),
        rows: z.number().int().positive().optional(),
        /** Tests run one command instead of an interactive shell. */
        shell: z.string().optional(),
        args: z.array(z.string()).optional(),
      }),
      TerminalInfoSchema,
    ),
    write: invoke(z.object({ id: z.string().min(1), data: z.string() }), z.void()),
    resize: invoke(
      z.object({
        id: z.string().min(1),
        cols: z.number().int().positive(),
        rows: z.number().int().positive(),
      }),
      z.void(),
    ),
    /**
     * Everything a reattaching tab missed, plus whether the shell is alive and
     * the output sequence the snapshot ends at — see `terminal.data`.
     */
    attach: invoke(
      z.object({ id: z.string().min(1) }),
      z
        .object({ info: TerminalInfoSchema, scrollback: z.string(), seq: z.number() })
        .nullable(),
    ),
    kill: invoke(z.object({ id: z.string().min(1) }), z.void()),
  },

  // `git.*` used to live here. It is its own branch now (./git.ts): the
  // review's reads and P7's worktrees are one subject, and this branch was
  // already the biggest in the contract.
} as const;

/* -------------------------------------------------------------------------- */
/* Events                                                                      */
/* -------------------------------------------------------------------------- */

export const explorerEvents = {
  /**
   * A batch of filesystem changes under a project root. Batched in main: a
   * `git checkout` fires hundreds of events in a few milliseconds and a tree
   * that re-renders per event janks.
   */
  "files.changed": z.object({
    projectId: z.string(),
    /** The watched root the paths are relative to; null is the project directory. */
    root: z.string().nullable(),
    changes: z.array(FileChangeSchema),
  }),
  /**
   * One pty's output, with its index in that pty's stream.
   *
   * A tab attaching to a running shell reads the same bytes twice — once in
   * the scrollback `terminal.attach` returns, once from this stream, which it
   * subscribed to before the snapshot was taken. `seq` is how it tells the
   * overlap apart; without it the shell's startup is written twice.
   */
  "terminal.data": z.object({ id: z.string(), data: z.string(), seq: z.number() }),
  /** The shell exited; the tab shows the code instead of a live cursor. */
  "terminal.exit": z.object({ id: z.string(), exitCode: z.number() }),
} as const;
