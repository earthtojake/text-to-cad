/**
 * Every child process main starts, so that quitting can end them.
 *
 * The app quits by `app.quit()`; Electron then waits for the Node side to
 * come down, and the Node side waits for the children it has pipes to. A
 * child that is still running at that moment — a version probe importing
 * OCP, a `git fetch` against a slow remote, a `pip install` into a cold cache — holds
 * the whole exit until it finishes or its own timeout kills it, which is how
 * quitting took sixty seconds with a STEP file open: `execCommand`'s probe
 * has a sixty-second timeout, and the process left when it did.
 *
 * So every spawn registers here and `endTrackedChildren` is called from
 * `before-quit`. Two kinds:
 *
 *   - `probe`   stateless: a `--version`, a `git status`, a login-shell
 *               `env`. Killed outright; the answer is not wanted any more.
 *   - `service` the viewer, an adapter, an install: told to stop by its
 *               owner (SIGTERM, so the viewer unregisters itself) and left to
 *               go. Its pipes are dropped and it is unref'd here, so nothing
 *               waits on it; a service that ignores SIGTERM is its owner's
 *               problem and gets a SIGKILL from `will-quit`. An explicitly
 *               owned POSIX process group also ends every worker it started,
 *               even if the service leader exits before its workers.
 *
 * Two shapes of child are registered: Node's `ChildProcess` (an emitter with
 * `exit`), and execa's subprocess, which is a promise with `pid` and `kill`
 * mixed in and no events at all. `Trackable` is what the two have in common.
 */

export type ChildKind = "probe" | "service";

type Closable = { destroy?: () => void } | null | undefined;

/** What a child has to offer to be tracked: a way to kill it, and a way to know it ended. */
export type Trackable = {
  pid?: number | undefined;
  spawnfile?: string;
  kill(signal?: NodeJS.Signals): unknown;
  exitCode?: number | null;
  signalCode?: NodeJS.Signals | null;
  stdin?: Closable;
  stdout?: Closable;
  stderr?: Closable;
  unref?: () => void;
  once?: (event: "exit" | "error", listener: () => void) => unknown;
  then?: (onFulfilled: () => void, onRejected: () => void) => unknown;
};

type Tracked = { kind: ChildKind; processGroup: number | undefined };

const live = new Map<Trackable, Tracked>();

type TrackOptions = {
  /** Only for a child this app spawned with `detached: true` on POSIX. */
  ownedProcessGroup?: boolean;
};

/** Register a child until it exits. Returns it, so a spawn can be wrapped inline. */
export function trackChild<T extends Trackable>(child: T, kind: ChildKind, options: TrackOptions = {}): T {
  const record: Tracked = {
    kind,
    processGroup: options.ownedProcessGroup && process.platform !== "win32" && child.pid && child.pid > 0 ? child.pid : undefined,
  };
  live.set(child, record);
  const forget = () => {
    // The leader can exit on SIGTERM while a compiler still imports OCP.
    // Reap its owned group before forgetting it; waiting for will-quit loses
    // the handle after reparenting. A shared daemon starts its own session.
    killGroup(record);
    live.delete(child);
  };
  if (typeof child.once === "function") {
    child.once("exit", forget);
    child.once("error", () => {
      if (!child.pid) {
        forget();
      }
    });
  } else if (typeof child.then === "function") {
    child.then(forget, forget);
  }
  return child;
}

/** What is still running, for tests and for the log. */
export function trackedChildren(): Array<{ pid: number | undefined; kind: ChildKind; file: string | undefined }> {
  return [...live.entries()].map(([child, { kind }]) => ({ pid: child.pid, kind, file: child.spawnfile }));
}

/**
 * `before-quit`: kill every probe, and detach every child from this process
 * so nothing here waits for it. Services keep running until their owner's
 * signal lands; that owner has already sent it by the time this is called.
 */
export function endTrackedChildren(): void {
  for (const [child, record] of live) {
    const { kind } = record;
    if (kind === "probe") {
      kill(child, record);
    }
    detach(child);
  }
}

/** `will-quit`: whatever is left is not going to stop on its own. */
export function killTrackedChildren(): void {
  for (const [child, record] of live) {
    kill(child, record);
    detach(child);
  }
  live.clear();
}

function killGroup(record: Tracked): void {
  const pid = record.processGroup;
  if (pid === undefined) {
    return;
  }
  // One final signal while this group's ownership is known. Do not retain
  // its numeric id after cleanup, when the OS can eventually reuse it.
  record.processGroup = undefined;
  try {
    process.kill(-pid, "SIGKILL");
  } catch {
    // No remaining members. Never fall back to another process group.
  }
}

function kill(child: Trackable, record: Tracked): void {
  killGroup(record);
  try {
    if ((child.exitCode ?? null) === null && (child.signalCode ?? null) === null) {
      child.kill("SIGKILL");
    }
  } catch {
    // Gone between the check and the signal; that is the outcome wanted.
  }
}

/** Drop the pipes and the ref: the process will not be waited on. */
function detach(child: Trackable): void {
  for (const stream of [child.stdin, child.stdout, child.stderr]) {
    try {
      stream?.destroy?.();
    } catch {
      /* already closed */
    }
  }
  try {
    child.unref?.();
  } catch {
    /* a child with no handle */
  }
}
