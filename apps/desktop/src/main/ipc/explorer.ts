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
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";

import { BrowserWindow, dialog, shell } from "electron";

import { explorerTabs, projects, settings } from "../db/repositories";
import {
  FileWatchers,
  FsError,
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
  statFile,
  writeTextFile,
  IgnoreRules,
} from "../explorer/fs";
import { addProjectFile } from "../explorer/add-files";
import { Terminals } from "../explorer/terminal";
import * as git from "../projects/git";
import { projectWorktreeDir, resolveProjectRoot } from "../projects/workspace";
import type { ExplorerTab, IpcEventChannel, IpcEventPayload } from "../../shared";
import { IpcError, type IpcContext } from "./register";

/* -------------------------------------------------------------------------- */
/* The services                                                                */
/* -------------------------------------------------------------------------- */

/** `broadcast` from `./index`, taken as an argument rather than imported. */
type Broadcast = <C extends IpcEventChannel>(channel: C, payload: IpcEventPayload<C>) => void;

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
  watchers ??= new FileWatchers((root, changes) => {
    // A watched root is a project directory or one of a project's worktrees;
    // the event names both, because a tab knows its root and a strip knows
    // its project.
    const owner = projectOfRoot(root);
    if (owner) {
      broadcast("files.changed", { projectId: owner.project.id, root: owner.root, changes });
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
 * The directory a request reads from: the project's, or — when the request
 * names a `root` — one of that project's worktrees (plan §9). Anything else
 * is refused here, before a path is resolved against it.
 */
export function rootOf(projectId: string, root?: string | null): string {
  const project = projects.list().find((candidate) => candidate.id === projectId);
  if (!project) {
    throw new IpcError("that project is no longer open");
  }
  try {
    return resolveProjectRoot(settings.get(), project, root);
  } catch (error) {
    throw new IpcError(error instanceof Error ? error.message : String(error));
  }
}

/**
 * The project a watched directory belongs to, and the root the renderer
 * knows it by (null for the project directory itself). Roots are compared
 * by real path: the watcher reports the directory it was given after
 * `realpath`, and a project under `/tmp` on macOS is really under
 * `/private/tmp`.
 */
function projectOfRoot(root: string): { project: { id: string }; root: string | null } | null {
  const current = settings.get();
  for (const project of projects.list()) {
    if (git.samePath(project.path, root)) {
      return { project, root: null };
    }
  }
  for (const project of projects.list()) {
    if (git.isUnder(projectWorktreeDir(current, project), root)) {
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
    const project = projects.list().find((candidate) => candidate.id === projectId);
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
      includeIgnored,
    }: {
      projectId: string;
      root?: string;
      path: string;
      includeIgnored?: boolean;
    }) =>
      fsCall(async () => {
        const root = rootOf(projectId, rootPath);
        return listDirectory(root, directory, {
          rules: await IgnoreRules.read(root),
          ...(includeIgnored === undefined ? {} : { includeIgnored }),
        });
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

    stat: ({ projectId, root, path: target }: AtPath) =>
      fsCall(() => statFile(rootOf(projectId, root), target)),

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
    }) => fsCall(() => writeTextFile(rootOf(projectId, root), target, content, expectedRevision)),

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

    addFiles: ({ projectId, root }: { projectId: string; root?: string }, ctx: IpcContext) =>
      fsCall(async () => {
        const base = rootOf(projectId, root);
        const window = BrowserWindow.fromWebContents(ctx.sender);
        const options: Electron.OpenDialogOptions = {
          title: "Add files to this project",
          message: "Copy files into this project. STEP, images, PDFs, code and other files are welcome.",
          buttonLabel: "Add files",
          properties: ["openFile", "multiSelections"],
        };
        const result = window ? await dialog.showOpenDialog(window, options) : await dialog.showOpenDialog(options);
        if (result.canceled || !result.filePaths.length) return null;
        if (rootOf(projectId, root) !== base) throw new IpcError("The project changed. Try adding files again.");
        const paths: string[] = [];
        const errors: string[] = [];
        for (const source of result.filePaths) {
          try { paths.push((await addProjectFile(base, source)).path); }
          catch (error) { errors.push(`${path.basename(source)}: ${error instanceof Error ? error.message : String(error)}`); }
        }
        return { paths, errors };
      }),

    reveal: ({ projectId, root, path: target }: AtPath) =>
      fsCall(async () => {
        shell.showItemInFolder(await resolveInRoot(rootOf(projectId, root), target));
      }),

    createFile: ({ projectId, root, path: directory, name }: AtPath & { name: string }) =>
      fsCall(() => createFile(rootOf(projectId, root), directory, name)),

    createDirectory: ({ projectId, root, path: directory, name }: AtPath & { name: string }) =>
      fsCall(() => createDirectory(rootOf(projectId, root), directory, name)),

    rename: ({ projectId, root, path: target, name }: AtPath & { name: string }) =>
      fsCall(() => renameEntry(rootOf(projectId, root), target, name)),

    duplicate: ({ projectId, root, path: target }: AtPath) =>
      fsCall(() => duplicateEntry(rootOf(projectId, root), target)),

    trash: ({ projectId, root, path: target }: AtPath) =>
      fsCall(async () => {
        const base = rootOf(projectId, root);
        const absolute = await resolveInRoot(base, target);
        // The root is the project: trashing it from its own tree is never
        // what a click on a menu item meant.
        if (absolute === (await fs.realpath(base).catch(() => path.resolve(base)))) {
          throw new IpcError("the project itself cannot be trashed here");
        }
        await shell.trashItem(absolute);
      }),

    watch: ({ projectId, root }: { projectId: string; root?: string }) =>
      fsCall(() => services().watchers.watch(rootOf(projectId, root))),

    unwatch: ({ projectId, root }: { projectId: string; root?: string }) =>
      fsCall(() => services().watchers.unwatch(rootOf(projectId, root))),

    loadTabs: ({ projectId }: { projectId: string }) => explorerTabs.list(projectId),

    saveTabs: ({ projectId, tabs }: { projectId: string; tabs: ExplorerTab[] }) => {
      explorerTabs.replace(projectId, tabs);
    },
  },

  terminal: {
    create: ({
      projectId,
      cwd,
      cols,
      rows,
      shell: shellPath,
      args,
    }: {
      projectId: string;
      cwd?: string;
      cols?: number;
      rows?: number;
      shell?: string;
      args?: string[];
    }) =>
      fsCall(async () => {
        // A worktree is outside the project directory by design (plan §9), so
        // this is not `resolveInRoot` alone; it is the root check first, which
        // admits the project and its own worktrees, and then a directory under
        // whichever of those it is (`Open in terminal` on a folder).
        const directory = await terminalDirectory(projectId, cwd);
        return services().terminals.create({
          cwd: directory,
          ...(cols === undefined ? {} : { cols }),
          ...(rows === undefined ? {} : { rows }),
          ...(shellPath === undefined ? {} : { shell: shellPath }),
          ...(args === undefined ? {} : { args }),
        });
      }),

    write: ({ id, data }: { id: string; data: string }) => {
      services().terminals.write(id, data);
    },

    resize: ({ id, cols, rows }: { id: string; cols: number; rows: number }) => {
      services().terminals.resize(id, cols, rows);
    },

    attach: ({ id }: { id: string }) => services().terminals.attach(id),

    kill: ({ id }: { id: string }) => {
      services().terminals.kill(id);
    },
  },
};
