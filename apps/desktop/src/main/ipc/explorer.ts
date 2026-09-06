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
import path from "node:path";

import { shell } from "electron";

import { explorerTabs, projects } from "../db/repositories";
import {
  FileWatchers,
  FsError,
  listDirectory,
  listPaths,
  readBinaryFile,
  readTextFile,
  resolveInRoot,
  statFile,
  writeTextFile,
  IgnoreRules,
} from "../explorer/fs";
import { Terminals } from "../explorer/terminal";
import * as git from "../projects/git";
import type { ExplorerTab, IpcEventChannel, IpcEventPayload } from "../../shared";
import { IpcError } from "./register";

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
    const project = projects.list().find((candidate) => candidate.path === root);
    if (project) {
      broadcast("files.changed", { projectId: project.id, changes });
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
export async function disposeExplorerServices() {
  terminals?.killAll();
  await watchers?.closeAll();
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

export function rootOf(projectId: string): string {
  const project = projects.list().find((candidate) => candidate.id === projectId);
  if (!project) {
    throw new IpcError("that project is no longer open");
  }
  return project.path;
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

/* -------------------------------------------------------------------------- */
/* Handlers                                                                    */
/* -------------------------------------------------------------------------- */

export const explorerHandlers = {
  explorer: {
    list: ({
      projectId,
      path: directory,
      includeIgnored,
    }: {
      projectId: string;
      path: string;
      includeIgnored?: boolean;
    }) =>
      fsCall(async () => {
        const root = rootOf(projectId);
        return listDirectory(root, directory, {
          rules: await IgnoreRules.read(root),
          ...(includeIgnored === undefined ? {} : { includeIgnored }),
        });
      }),

    paths: ({
      projectId,
      path: directory,
      limit,
    }: {
      projectId: string;
      path: string;
      limit?: number;
    }) =>
      fsCall(() =>
        listPaths(rootOf(projectId), directory, limit === undefined ? {} : { limit }),
      ),

    stat: ({ projectId, path: target }: { projectId: string; path: string }) =>
      fsCall(() => statFile(rootOf(projectId), target)),

    readText: ({ projectId, path: target }: { projectId: string; path: string }) =>
      fsCall(() => readTextFile(rootOf(projectId), target)),

    writeText: ({
      projectId,
      path: target,
      content,
      expectedRevision,
    }: {
      projectId: string;
      path: string;
      content: string;
      expectedRevision?: string;
    }) => fsCall(() => writeTextFile(rootOf(projectId), target, content, expectedRevision)),

    readBinary: ({ projectId, path: target }: { projectId: string; path: string }) =>
      fsCall(() => readBinaryFile(rootOf(projectId), target)),

    absolutePath: ({ projectId, path: target }: { projectId: string; path: string }) =>
      fsCall(async () => ({ path: await resolveInRoot(rootOf(projectId), target) })),

    openDefault: ({ projectId, path: target }: { projectId: string; path: string }) =>
      fsCall(async () => {
        const absolute = await resolveInRoot(rootOf(projectId), target);
        // `openPath` answers with a message instead of throwing, and an
        // unhandled one leaves the user clicking a menu item that does nothing.
        const failure = await shell.openPath(absolute);
        if (failure) {
          throw new IpcError(failure);
        }
      }),

    watch: ({ projectId }: { projectId: string }) =>
      fsCall(() => services().watchers.watch(rootOf(projectId))),

    unwatch: ({ projectId }: { projectId: string }) =>
      fsCall(() => services().watchers.unwatch(rootOf(projectId))),

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
        const root = rootOf(projectId);
        // A worktree is outside the project root by design (plan §9), so this
        // is not `resolveInRoot`: the check that matters is that main chose
        // the directory, which it does by falling back to the root.
        const directory = cwd ? path.resolve(cwd) : root;
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
