/**
 * The explorer's handlers: the file tab's filesystem and the terminal tabs'
 * ptys. The review tab's git reads are `./git.ts`, which borrows `rootOf` and
 * `fsCall` from here — the same two questions ("which project" and "what does
 * this failure look like to a person") have one answer for both.
 *
 * Every one of them starts by turning a `projectId` into a root, because a
 * path from the renderer means nothing on its own. `rootOf` throws when the
 * project is gone, which is the honest answer to "read this file in a project
 * I removed" and stops a stale tab from reading an arbitrary path.
 */
import { randomUUID } from "node:crypto";
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";

import { BrowserWindow, dialog, shell, type WebContents } from "electron";

import { explorerTabs, projects, sessions, settings } from "../db/repositories";
import {
  FileWatchers,
  FsError,
  FsConflictError,
  createDirectory,
  createFile,
  duplicateEntry,
  listDirectory,
  listPaths,
  pathKinds,
  readBinaryFile,
  readTextFile,
  renameEntry,
  resolveInRoot,
  statEntry,
  statFile,
  writeTextFile,
} from "../explorer/fs";
import { sessionRuntimePath } from "../cad";
import { Terminals } from "../explorer/terminal";
import * as git from "../projects/git";
import { projectWorktreeDir, realDirectory, resolveProjectRoot, rootBelongsToProject } from "../projects/workspace";
import type { ExplorerTab, IpcEventChannel, IpcEventPayload } from "../../shared";
import type { FileChange, FileMutationResult } from "../../shared/ipc/explorer";
import { fileExtension, track } from "../telemetry";
import { IpcError, type IpcContext } from "./register";

/* -------------------------------------------------------------------------- */
/* The services                                                                */
/* -------------------------------------------------------------------------- */

/** `broadcast` from `./index`, taken as an argument rather than imported. */
type Broadcast = <C extends IpcEventChannel>(channel: C, payload: IpcEventPayload<C>) => void;

let publish: Broadcast | null = null;
let watchers: FileWatchers | null = null;
let terminals: Terminals | null = null;

/**
 * Wire the two long-lived services to the broadcaster.
 *
 * They are created here rather than at module scope because both push events,
 * and a module-scope instance would have to reach back into `ipc/index.ts` for
 * the broadcaster — the cycle this argument avoids.
 */
export function initExplorerServices(broadcast: Broadcast) {
  publish = broadcast;
  watchers ??= new FileWatchers((root, changes) => {
    // A watched root is a project directory or one of a project's worktrees;
    // the event names both, because a tab knows its root and a strip knows
    // its project.
    const owner = projectOfRoot(root);
    if (owner) {
      broadcast("files.changed", { projectId: owner.project.id, root: owner.root, changes });
    }
  }, undefined, (root, reason) => {
    const owner = projectOfRoot(root);
    if (owner) {
      broadcast("files.watch-error", {
        projectId: owner.project.id,
        root: owner.root,
        message: `Live updates stopped: ${reason}. Reload the tab to re-arm them.`,
      });
    }
  });
  terminals ??= new Terminals((event) => {
    if (event.type === "data") {
      broadcast("terminal.data", { id: event.id, data: event.data, seq: event.seq });
    } else {
      broadcast("terminal.exit", { id: event.id, exitCode: event.exitCode });
    }
  });
}

/** On quit: no pty and no watcher outlives the window that opened it. */
export function disposeExplorerServices() {
  // The ptys: a shell that outlives the window is a shell nobody can see or
  // stop. The watchers are left alone on purpose — chokidar's `close()` over
  // a large tree blocks for most of a second before its first await, and an
  // fsevents handle dies with the process anyway.
  terminals?.killAll();
  terminals = null;
  watchers = null;
}

/**
 * The watches each page holds, by root, counted like the watchers' own refs.
 * A reload (Cmd+R) or a renderer that dies never sends its unwatches: the
 * new page watches again, and every root the old one watched kept a ref that
 * nothing would release, and a chokidar watcher over the tree that never
 * closed. A page's leases are returned for it when another page commits in
 * its place or it goes.
 *
 * On `did-navigate`, not `did-start-navigation`: a navigation starts before
 * `will-navigate` is asked, and the window cancels every one of those
 * (`src/main/index.ts` — a stray `<a href>`, a file dropped on the page), so
 * a page released at the start would keep living with its watches gone.
 */
const leases = new Map<number, Map<string, number>>();
/**
 * The root each of a page's watch requests resolved to when it took the
 * lease, by the request's own (project, root). An unwatch returns the lease
 * this names rather than resolving the request again: a project or session
 * deleted since the watch has no row for `rootOf` to read, and the unwatch
 * that follows a delete would throw before it gave anything back.
 *
 * A list per request, one entry per watch outstanding: the same request can
 * resolve to another root between two watches (a worktree switched under a
 * session), and a single slot would hand the second watch's root to the
 * first unwatch. The oldest is returned first; an emptied list is deleted.
 */
const leased = new Map<number, Map<string, string[]>>();
const requestKey = (projectId: string, root: string | undefined) => `${projectId}\0${root ?? ""}`;
/** Per page, how many documents it has shown; a watch is credited to the one that asked. */
const documents = new Map<number, number>();

/**
 * The document asking, taken before a watch's await: a navigation that
 * commits meanwhile makes the watch the old document's, already released.
 */
function documentOf(sender: WebContents | undefined): number | undefined {
  if (!sender) return undefined;
  const known = documents.get(sender.id);
  if (known !== undefined) return known;
  documents.set(sender.id, 0);
  const id = sender.id;
  const release = () => {
    const roots = leases.get(id);
    leases.delete(id);
    leased.delete(id);
    documents.set(id, (documents.get(id) ?? 0) + 1);
    for (const [directory, count] of roots ?? []) {
      for (let index = 0; index < count; index += 1) void watchers?.unwatch(directory).catch(() => {});
    }
  };
  // `did-navigate` is the main frame's, and a committed cross-document
  // navigation only (an in-page one is `did-navigate-in-page`).
  sender.on("did-navigate", release);
  sender.on("render-process-gone", release);
  sender.once("destroyed", () => {
    release();
    documents.delete(id);
  });
  return 0;
}

/** False when the document that asked is gone: the watch is its own to give back. */
function lease(sender: WebContents | undefined, root: string, document: number | undefined, request: string): boolean {
  if (!sender) return true;
  if (documents.get(sender.id) !== document) return false;
  let names = leased.get(sender.id);
  if (!names) {
    names = new Map();
    leased.set(sender.id, names);
  }
  names.set(request, [...names.get(request) ?? [], root]);
  let held = leases.get(sender.id);
  if (!held) {
    held = new Map();
    leases.set(sender.id, held);
  }
  held.set(root, (held.get(root) ?? 0) + 1);
  return true;
}

/**
 * Each page's watches still setting up, by root. An unwatch is sent after
 * its watch but can land first — the watch awaits the root before it takes
 * its lease — and would find nothing to give back: the watch then holds a
 * lease, and the watcher a ref, that nothing returns. An unwatch waits for
 * the page's watches of that root to land first.
 */
const settingUp = new Map<string, Set<Promise<unknown>>>();
const pageRoot = (sender: WebContents, root: string) => `${sender.id}\0${root}`;

async function watchLanded(sender: WebContents | undefined, root: string, watch: Promise<void>): Promise<void> {
  if (!sender) return watch;
  const key = pageRoot(sender, root);
  const pending = settingUp.get(key) ?? new Set();
  settingUp.set(key, pending);
  pending.add(watch);
  try {
    await watch;
  } finally {
    pending.delete(watch);
    if (pending.size === 0 && settingUp.get(key) === pending) settingUp.delete(key);
  }
}

/** One outstanding watch of `request` is being given back: forget the root it took. */
function forgetLeased(sender: WebContents, request: string, root: string) {
  const names = leased.get(sender.id);
  const roots = names?.get(request);
  if (!names || !roots) return;
  const at = roots.indexOf(root);
  if (at >= 0) roots.splice(at, 1);
  if (roots.length === 0) names.delete(request);
}

/** False when this page holds no watch on the root to give back. */
function returnLease(sender: WebContents, root: string): boolean {
  const held = leases.get(sender.id);
  const count = held?.get(root) ?? 0;
  if (count === 0) return false;
  if (count === 1) held!.delete(root);
  else held!.set(root, count - 1);
  return true;
}

function services() {
  if (!watchers || !terminals) {
    throw new IpcError("the explorer services are not running");
  }
  return { watchers, terminals };
}

/* -------------------------------------------------------------------------- */
/* Projects and paths                                                          */
/* -------------------------------------------------------------------------- */

/**
 * Session roots' real paths, keyed by the spelling main recorded. rootOf runs
 * for every stat, list, read and `exists` (the transcript asks one per path
 * token), and realpathSync blocks main's thread, so a spelling is resolved
 * once; the cache is dropped whenever the recorded spellings change.
 */
const recordedRealpaths = { signature: "", paths: new Map<string, string>() };

function recordedRealpath(spelling: string, signature: string): string {
  if (recordedRealpaths.signature !== signature) {
    recordedRealpaths.signature = signature;
    recordedRealpaths.paths.clear();
  }
  let real = recordedRealpaths.paths.get(spelling);
  if (real === undefined) {
    real = realDirectory(spelling);
    recordedRealpaths.paths.set(spelling, real);
  }
  return real;
}

/**
 * The directory a request reads from: the project's, or — when the request
 * names a `root` — one of that project's worktrees (plan §9). Anything else
 * is refused here, before a path is resolved against it.
 */
export function rootOf(projectId: string, root?: string | null): string {
  const project = projects.get(projectId);
  if (!project) {
    throw new IpcError("that project is no longer open");
  }
  try {
    // Persisted worktrees retain access even if an old project label changed.
    // Any spelling of the directory finds its session; what is handed on is
    // the RECORDED spelling — never the caller's (that let a request key
    // watchers and viewers by a string of its choosing), and not the realpath
    // either: watchers, `files.changed` and the CAD viewer are keyed by this
    // root, and the renderer and `forgetCadSession` know the session by the
    // path main recorded.
    if (root) {
      const all = sessions.list();
      const recorded = all
        .filter((session) => session.projectId === projectId)
        .flatMap((session) => [session.cwd, session.worktreePath].filter((candidate): candidate is string => Boolean(candidate)));
      // The usual caller sends the recorded spelling back: no disk access.
      const exact = recorded.find((candidate) => git.samePath(candidate, root));
      if (exact) return exact;
      if (recorded.length > 0) {
        const requested = realDirectory(root);
        const signature = all.map((session) => `${session.cwd}\0${session.worktreePath ?? ""}`).join("\0");
        const linked = recorded.find((candidate) => git.samePath(recordedRealpath(candidate, signature), requested));
        if (linked) return linked;
      }
    }
    return resolveProjectRoot(settings.get(), project, root);
  } catch (error) {
    throw new IpcError(error instanceof Error ? error.message : String(error));
  }
}

/**
 * `shell.showItemInFolder`: the project, one of its worktrees, or the folder
 * its worktrees live in — resolved here, never taken as a path.
 */
export function revealProjectDirectory(request: {
  projectId: string;
  root?: string | null | undefined;
  worktrees?: true | undefined;
}): void {
  const target = rootOf(request.projectId, request.root);
  const project = projects.get(request.projectId);
  shell.showItemInFolder(request.worktrees && project ? projectWorktreeDir(settings.get(), project) : target);
}

/**
 * The project a watched directory belongs to, and the root the renderer
 * knows it by (null for the project directory itself). Roots are compared
 * by real path: the watcher reports the directory it was given after
 * `realpath`, and a project under `/tmp` on macOS is really under
 * `/private/tmp`.
 */
export function projectOfRoot(root: string): { project: { id: string }; root: string | null } | null {
  const current = settings.get();
  for (const project of projects.list()) {
    if (git.samePath(project.path, root)) {
      return { project, root: null };
    }
  }
  for (const session of sessions.list()) {
    if (git.samePath(session.cwd, root) || (session.worktreePath && git.samePath(session.worktreePath, root))) {
      const project = projects.get(session.projectId);
      if (project) return { project, root: git.samePath(project.path, root) ? null : root };
    }
  }
  // Either worktree folder: the hashed one, or the pre-hash one when git
  // links the worktree to this project's repository (`rootBelongsToProject`).
  for (const project of projects.list()) {
    if (!git.samePath(project.path, root) && rootBelongsToProject(current, project, root)) {
      return { project, root };
    }
  }
  return null;
}

/**
 * Run something that touches the filesystem, translating its failures.
 *
 * An `FsError` is a message written to be read ("that file is not text"); an
 * `ENOENT` from Node carries an absolute path, which is exactly what must not
 * reach the UI. `registerIpc` already hides anything that is not an
 * `IpcError`, so the job here is only to promote the ones that are safe.
 */
export async function fsCall<T>(work: () => Promise<T>): Promise<T> {
  try {
    return await work();
  } catch (error) {
    if (error instanceof FsError || error instanceof git.GitError) {
      throw new IpcError(error.message);
    }
    if (isErrno(error, "ENOENT")) {
      throw new IpcError("that file is gone");
    }
    if (isErrno(error, "EACCES") || isErrno(error, "EPERM")) {
      throw new IpcError("no permission to read that file");
    }
    if (isErrno(error, "EISDIR")) {
      throw new IpcError("that is a directory");
    }
    throw error;
  }
}

function isErrno(error: unknown, code: string): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as NodeJS.ErrnoException).code === code
  );
}

/** Structured failures survive Electron's error serialization without parsing prose. */
function fileFailure(error: unknown): { code: "denied" | "not-found" | "already-exists" | "unsupported" | "conflict" | "error"; message: string } {
  if (error instanceof FsError) return { code: error.code, message: error.message };
  if (isErrno(error, "ENOENT")) return { code: "not-found", message: "that file is gone" };
  if (isErrno(error, "EEXIST")) return { code: "already-exists", message: "something with that name is already there" };
  if (isErrno(error, "EACCES") || isErrno(error, "EPERM")) return { code: "denied", message: "no permission to change that file" };
  if (error instanceof IpcError) return { code: "denied", message: error.message };
  return { code: "error", message: "could not change that file" };
}

function publishChange(at: { projectId: string; root?: string }, change: FileChange) {
  try { publish?.("files.changed", { projectId: at.projectId, root: at.root ?? null, changes: [change] }); }
  catch { /* A failed notification cannot turn an already committed mutation into a failed receipt. */ }
}

async function mutateFile(at: AtPath, operation: (base: string) => Promise<FileChange>): Promise<FileMutationResult> {
  try {
    const change = { ...await operation(rootOf(at.projectId, at.root)), mutationId: randomUUID() };
    publishChange(at, change);
    return { status: "committed", path: change.path, change };
  } catch (error) { return { status: "failed", ...fileFailure(error) }; }
}

/**
 * A terminal's working directory: a root, or a directory under one.
 *
 * `Open in terminal` on a folder in the tree asks for that folder, which is
 * neither the project nor a worktree. The check is still the root check —
 * the directory has to be inside the project or inside one of its worktrees
 * — and then `resolveInRoot` against whichever it is, so a symlink out of
 * the tree is caught the way it is for a read.
 */
async function terminalDirectory(projectId: string, cwd: string | undefined): Promise<string> {
  if (!cwd) {
    return rootOf(projectId, null);
  }
  const absolute = path.resolve(cwd);
  try {
    return rootOf(projectId, absolute);
  } catch (error) {
    const project = projects.get(projectId);
    if (!project) {
      throw error;
    }
    const worktreeDir = projectWorktreeDir(settings.get(), project);
    const root = git.isUnder(project.path, absolute)
      ? project.path
      : git.isUnder(worktreeDir, absolute)
        ? rootOf(projectId, path.join(worktreeDir, path.relative(worktreeDir, absolute).split(path.sep)[0] ?? ""))
        : null;
    if (!root) {
      throw error;
    }
    const resolved = await resolveInRoot(root, absolute);
    if (!(await fs.stat(resolved)).isDirectory()) {
      throw new FsError("that is not a directory");
    }
    return resolved;
  }
}

/**
 * The platform's "open with" for one file.
 *
 * macOS: a chooser over `/Applications`, then `open -a`. Windows: the
 * shell's own Open With dialog, which is the one a person knows. Linux: a
 * chooser for a program, run with the file — there is no portable picker.
 */
async function openWith(absolute: string, ctx: IpcContext): Promise<void> {
  const run = (command: string, args: string[]) =>
    new Promise<void>((resolve, reject) => {
      execFile(command, args, (error) => (error ? reject(error) : resolve()));
    });

  if (process.platform === "win32") {
    await run("rundll32.exe", ["shell32.dll,OpenAs_RunDLL", absolute]);
    return;
  }

  const window = BrowserWindow.fromWebContents(ctx.sender);
  const options: Electron.OpenDialogOptions =
    process.platform === "darwin"
      ? {
          title: "Open with",
          buttonLabel: "Open",
          defaultPath: "/Applications",
          filters: [{ name: "Applications", extensions: ["app"] }],
          properties: ["openFile"],
        }
      : {
          title: "Open with",
          buttonLabel: "Open",
          defaultPath: "/usr/bin",
          properties: ["openFile"],
        };
  const result = window ? await dialog.showOpenDialog(window, options) : await dialog.showOpenDialog(options);
  const chosen = result.canceled ? undefined : result.filePaths[0];
  if (!chosen) {
    return;
  }
  if (process.platform === "darwin") {
    await run("open", ["-a", chosen, absolute]);
  } else {
    await run(chosen, [absolute]);
  }
}

/* -------------------------------------------------------------------------- */
/* Handlers                                                                    */
/* -------------------------------------------------------------------------- */

type AtPath = { projectId: string; root?: string; path: string };

export const explorerHandlers = {
  explorer: {
    list: ({
      projectId,
      root: rootPath,
      path: directory,
    }: {
      projectId: string;
      root?: string;
      path: string;
    }) =>
      fsCall(async () => {
        const root = rootOf(projectId, rootPath);
        const entries = await listDirectory(root, directory);
        await watchers?.watchListedDirectory(root, directory);
        return entries;
      }),

    paths: ({
      projectId,
      root,
      path: directory,
      limit,
    }: {
      projectId: string;
      root?: string;
      path: string;
      limit?: number;
    }) =>
      fsCall(() =>
        listPaths(rootOf(projectId, root), directory, limit === undefined ? {} : { limit }),
      ),

    stat: ({ projectId, root: rootPath, path: target, intent }: AtPath & { intent?: "open" | undefined }) =>
      fsCall(async () => {
        const root = rootOf(projectId, rootPath);
        const entry = await statFile(root, target);
        // Only a file tab's stat says `intent: "open"` (`fileSource.ts`); the
        // composer's attachment check and the integrations' renderer lookup
        // stat files nobody opened, and must neither watch nor count them. An
        // agent's open_file needs no watch of its own: the tab it opens stats
        // again through `fileSource.ts`, and that stat watches.
        if (intent !== "open") return entry;
        await watchers?.watchEntry(root, entry);
        // `file_opened`: opening a file tab is renderer state, and its stat is
        // the call main sees for an open. A tab's reload after an on-disk
        // change stats again without the intent, so it is neither held nor
        // counted twice. Only the extension leaves:
        // never the path or the name (README, "Telemetry").
        if (entry.kind === "file") {
          track({ name: "file_opened", extension: fileExtension(entry.path) });
        }
        return entry;
      }),

    exists: ({ projectId, root, paths }: { projectId: string; root?: string; paths: string[] }) =>
      fsCall(() => pathKinds(rootOf(projectId, root), paths)),

    readText: ({ projectId, root, path: target }: AtPath) =>
      fsCall(() => readTextFile(rootOf(projectId, root), target)),

    writeText: ({
      projectId,
      root,
      path: target,
      content,
      expectedRevision,
    }: AtPath & {
      content: string;
      expectedRevision?: string;
    }) => (async () => {
      try {
        const base = rootOf(projectId, root);
        const document = await writeTextFile(base, target, content, expectedRevision);
        // The save renamed a new inode into place; a move right after it is
        // still this file's (`FileWatchers.refreshEntry`).
        await watchers?.refreshEntry(base, document.path).catch(() => {});
        publishChange({ projectId, root }, { kind: "changed", path: document.path, directory: false, revision: document.revision });
        return { status: "saved" as const, document };
      } catch (error) {
        if (error instanceof FsConflictError) return { status: "conflict" as const, message: error.message, actualRevision: error.actualRevision };
        return { status: "error" as const, ...fileFailure(error) };
      }
    })(),

    readBinary: ({ projectId, root, path: target }: AtPath) =>
      fsCall(() => readBinaryFile(rootOf(projectId, root), target)),

    absolutePath: ({ projectId, root, path: target }: AtPath) =>
      fsCall(async () => ({ path: await resolveInRoot(rootOf(projectId, root), target) })),

    openDefault: ({ projectId, root, path: target }: AtPath) =>
      fsCall(async () => {
        const absolute = await resolveInRoot(rootOf(projectId, root), target);
        // `openPath` answers with a message instead of throwing, and an
        // unhandled one leaves the user clicking a menu item that does nothing.
        const failure = await shell.openPath(absolute);
        if (failure) {
          throw new IpcError(failure);
        }
      }),

    openWith: ({ projectId, root, path: target }: AtPath, ctx: IpcContext) =>
      fsCall(async () => {
        const absolute = await resolveInRoot(rootOf(projectId, root), target);
        try {
          await openWith(absolute, ctx);
        } catch (error) {
          throw new IpcError(`could not open the file that way: ${error instanceof Error ? error.message : String(error)}`);
        }
      }),

    reveal: ({ projectId, root, path: target }: AtPath) =>
      fsCall(async () => {
        shell.showItemInFolder(await resolveInRoot(rootOf(projectId, root), target));
      }),

    createFile: (at: AtPath & { name: string }) => mutateFile(at, async base => {
      const result = await createFile(base, at.path, at.name);
      return { kind: "added", path: result.path, directory: false };
    }),

    createDirectory: (at: AtPath & { name: string }) => mutateFile(at, async base => {
      const result = await createDirectory(base, at.path, at.name);
      return { kind: "added", path: result.path, directory: true };
    }),

    // Rename, duplicate and trash act on the row: a symlink is the link, its
    // path is the link's, and its target is left alone (`statEntry`).
    rename: (at: AtPath & { name: string }) => mutateFile(at, async base => {
      const before = await statEntry(base, at.path);
      const result = await renameEntry(base, at.path, at.name);
      return { kind: "moved", previousPath: before.path, path: result.path, directory: before.directory };
    }),

    duplicate: (at: AtPath) => mutateFile(at, async base => {
      const before = await statEntry(base, at.path);
      const result = await duplicateEntry(base, at.path);
      return { kind: "added", path: result.path, directory: before.directory };
    }),

    trash: (at: AtPath) => mutateFile(at, async base => {
      const before = await statEntry(base, at.path);
      if (before.absolute === (await fs.realpath(base).catch(() => path.resolve(base)))) {
        throw new FsError("the project itself cannot be trashed here", "denied");
      }
      await shell.trashItem(before.absolute);
      return { kind: "removed", path: before.path, directory: before.directory };
    }),

    watch: ({ projectId, root, paths }: { projectId: string; root?: string; paths?: string[] }, ctx?: IpcContext) =>
      fsCall(async () => {
        const directory = rootOf(projectId, root);
        const document = documentOf(ctx?.sender);
        const { watchers: service } = services();
        await watchLanded(ctx?.sender, directory, (async () => {
          await service.watch(directory, paths);
          // The page moved on while the watch was set up: nothing will give it back.
          if (!lease(ctx?.sender, directory, document, requestKey(projectId, root))) await service.unwatch(directory, paths);
        })());
      }),

    unwatch: ({ projectId, root, paths }: { projectId: string; root?: string; paths?: string[] }, ctx?: IpcContext) =>
      fsCall(async () => {
        const request = requestKey(projectId, root);
        const directory = (ctx && leased.get(ctx.sender.id)?.get(request)?.[0]) || rootOf(projectId, root);
        // Behind the page's watches of this root still on their way (`settingUp`).
        if (ctx) await Promise.allSettled([...settingUp.get(pageRoot(ctx.sender, directory)) ?? []]);
        // After the wait: a watch that landed meanwhile has recorded its root by now.
        if (ctx) forgetLeased(ctx.sender, request, directory);
        // A page's unwatch after its leases went with a reload is already counted.
        if (ctx && !returnLease(ctx.sender, directory)) return;
        await services().watchers.unwatch(directory, paths);
      }),

    // A saved terminal tab names a pty of the run that saved it. Ptys die with
    // the app, so an id no live pty of this session answers to is released here
    // and the tab starts a fresh shell; left in, every restored terminal would
    // say "no longer running" until Try again.
    loadTabs: ({ sessionId }: { sessionId: string }) => {
      const { terminals: live } = services();
      return explorerTabs.list(sessionId).map(tab =>
        tab.kind === "terminal" && tab.ptyId && !live.owns(tab.ptyId, sessionId) ? { ...tab, ptyId: null } : tab);
    },

    saveTabs: ({ sessionId, tabs }: { sessionId: string; tabs: ExplorerTab[] }) => {
      explorerTabs.replace(sessionId, tabs);
    },
  },

  terminal: {
    create: ({
      sessionId,
      projectId,
      cwd,
      cols,
      rows,
      agent,
    }: {
      sessionId: string;
      projectId: string;
      cwd?: string;
      cols?: number;
      rows?: number;
      agent?: boolean;
    }) =>
      fsCall(async () => {
        // A worktree is outside the project directory by design (plan §9), so
        // this is not `resolveInRoot` alone; it is the root check first, which
        // admits the project and its own worktrees, and then a directory under
        // whichever of those it is (`Open in terminal` on a folder).
        const session = sessions.get(sessionId);
        if (!session || session.projectId !== projectId || session.archived) throw new IpcError("This session is no longer active.");
        const directory = await terminalDirectory(projectId, cwd ?? session.cwd);
        await resolveInRoot(session.cwd, directory);
        const service = services().terminals;
        const info = await service.create({
          sessionId,
          projectId,
          cwd: directory,
          ...(cols === undefined ? {} : { cols }),
          ...(rows === undefined ? {} : { rows }),
          // A respawned agent-opened tab gets what `create_terminal` gave it: `cadgen` on PATH.
          ...(agent ? { pathPrefix: sessionRuntimePath() } : {}),
        });
        const current = sessions.get(sessionId);
        if (!current || current.archived || current.cwd !== session.cwd || current.projectId !== projectId) {
          service.kill(info.id);
          throw new IpcError("This session changed before the terminal was ready.");
        }
        return info;
      }),

    write: ({ id, sessionId, data }: OwnedPty & { data: string }) => {
      ownedTerminals(id, sessionId).write(id, data);
    },

    resize: ({ id, sessionId, cols, rows }: OwnedPty & { cols: number; rows: number }) => {
      ownedTerminals(id, sessionId).resize(id, cols, rows);
    },

    attach: ({ id, sessionId }: OwnedPty) => ownedTerminals(id, sessionId).attach(id),

    kill: ({ id, sessionId }: OwnedPty) => {
      ownedTerminals(id, sessionId).kill(id);
    },
  },
};

type OwnedPty = { id: string; sessionId: string };

/**
 * The pty registry, once the pty is known to be the asking session's. A pty
 * id is not a capability: sharing a directory grants no access to another
 * session's shell. A pty that is already gone is left to the registry, whose
 * answer for one is a no-op (or `null` for `attach`).
 */
function ownedTerminals(id: string, sessionId: string): Terminals {
  const { terminals } = services();
  if (terminals.has(id) && !terminals.owns(id, sessionId)) {
    throw new IpcError("that terminal belongs to another session");
  }
  return terminals;
}

/** The app-owned PTY registry shared by UI and integration tools. */
export function explorerTerminals(): Terminals { return services().terminals; }
