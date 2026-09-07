/**
 * Every child process main starts, so that quitting can end them.
 *
 * The app quits by `app.quit()`; Electron then waits for the Node side to
 * come down, and the Node side waits for the children it has pipes to. A
 * child that is still running at that moment — a version probe importing
 * OCP, a `git fetch` against a slow remote, a `claude plugin install` — holds
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
 *               problem and gets a SIGKILL from `will-quit`.
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

const live = new Map<Trackable, ChildKind>();

/** Register a child until it exits. Returns it, so a spawn can be wrapped inline. */
export function trackChild<T extends Trackable>(child: T, kind: ChildKind): T {
  live.set(child, kind);
  const forget = () => {
    live.delete(child);
  };
  if (typeof child.once === "function") {
    child.once("exit", forget);
    child.once("error", forget);
  } else if (typeof child.then === "function") {
    child.then(forget, forget);
  }
  return child;
}

/** What is still running, for tests and for the log. */
export function trackedChildren(): Array<{ pid: number | undefined; kind: ChildKind; file: string | undefined }> {
  return [...live.entries()].map(([child, kind]) => ({ pid: child.pid, kind, file: child.spawnfile }));
}

/**
 * `before-quit`: kill every probe, and detach every child from this process
 * so nothing here waits for it. Services keep running until their owner's
 * signal lands; that owner has already sent it by the time this is called.
 */
export function endTrackedChildren(): void {
  for (const [child, kind] of live) {
    if (kind === "probe") {
      kill(child, "SIGKILL");
    }
    detach(child);
  }
}

/** `will-quit`: whatever is left is not going to stop on its own. */
export function killTrackedChildren(): void {
  for (const child of live.keys()) {
    kill(child, "SIGKILL");
    detach(child);
  }
  live.clear();
}

function kill(child: Trackable, signal: NodeJS.Signals): void {
  try {
    if ((child.exitCode ?? null) === null && (child.signalCode ?? null) === null) {
      child.kill(signal);
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
