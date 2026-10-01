/**
 * The warm build daemon, started before the first file needs it.
 *
 * Every compile the viewer submits runs in cadgen's pool: on a daemon spare
 * when one is warm, else in a transient process that pays the OCP import
 * (`import build123d`, several seconds) on the caller's clock. The first
 * daemon-served job of a machine's day also pays for the daemon's own start
 * — measured at 3.5 s on top of the job (scripts/perf-cad.mjs, "daemon first
 * job (spawn)" vs "daemon warm") — and its spares keep importing after that.
 *
 * `cadgen daemon` (`python -m cadgen.daemon`) is the registered command that
 * runs the daemon, and it is exactly what a cadgen client spawns on its own
 * when it finds none: it creates the shared secret itself, takes the
 * singleton lock, and stands down at once if one is already bound, so
 * starting it here when a project opens is the same daemon the CLI and the
 * viewer would have started later, only earlier and off the critical path.
 * Detached and never held as one of the app's children (only its pid is remembered, while it
 * runs, so a quit's deadline spares it): it is the person's daemon, shared with every
 * terminal, and it retires on its own idle timeout the way the CLI's does.
 * It starts in the app's data directory, not in the project that opened it:
 * a process's cwd locks that folder on Windows (the worktree could not be
 * removed while the daemon lives on) and pins a deleted inode elsewhere. It
 * needs no project cwd — every request carries its own, and its workers run
 * in a tempdir between jobs.
 *
 * Once per app run per interpreter. The daemon's stderr — its lifecycle
 * lines and the kernel's noise — goes to the runtime log beside the probe's
 * and the viewer's, so one file answers "what did the app start".
 */
import { spawn as nodeSpawn } from "node:child_process";
import fs from "node:fs";

import type { ResolvedPython } from "./runtime";

export const DAEMON_ARGS = ["-m", "cadgen.daemon"];

const spawnedPids = new Set<number>();

/**
 * Pids of the daemons this app run started AND that are still running; the quit watchdog spares
 * them (src/main/quit-deadline.ts). A daemon's pid leaves the set when it exits, so a pid the
 * kernel hands to a later direct child of the app is never spared by mistake.
 */
export function daemonPids(): number[] {
  return [...spawnedPids];
}

export type DaemonSpawn = (
  python: string,
  args: string[],
  options: { cwd: string; env: Record<string, string>; logFile: string },
) => {
  pid?: number | undefined;
  unref(): void;
  /** A real child process has it; the exit is what takes its pid back out of `daemonPids()`. */
  once?(event: "exit", listener: () => void): unknown;
} | null;

export type DaemonWarmerDeps = {
  /** The environment cadgen children get (PYTHONPATH in a checkout, CADGEN_NODE). */
  env: (resolved: ResolvedPython) => Record<string, string>;
  /** Where the daemon's stderr goes: the runtime log. */
  logFile: () => string;
  /** The directory it starts in: one that no project owns, so none is held open. */
  cwd: () => string;
  spawn?: DaemonSpawn;
  log?: (line: string) => void;
};

function defaultSpawn(python: string, args: string[], options: { cwd: string; env: Record<string, string>; logFile: string }) {
  let out: number | "ignore" = "ignore";
  try {
    out = fs.openSync(options.logFile, "a");
  } catch {
    /* no log: the daemon still runs */
  }
  const child = nodeSpawn(python, args, {
    cwd: options.cwd,
    env: options.env,
    detached: true,
    stdio: ["ignore", out, out],
    windowsHide: true,
  });
  child.on("error", () => {
    /* reported by the caller's log line; nothing else to do */
  });
  if (typeof out === "number") {
    child.on("spawn", () => fs.closeSync(out as number));
    child.on("error", () => {
      try {
        fs.closeSync(out as number);
      } catch {
        /* closed on spawn */
      }
    });
  }
  return child;
}

export class DaemonWarmer {
  private readonly warmed = new Set<string>();
  private readonly spawn: DaemonSpawn;
  private readonly log: (line: string) => void;

  constructor(private readonly deps: DaemonWarmerDeps) {
    this.spawn = deps.spawn ?? defaultSpawn;
    this.log = deps.log ?? ((line) => console.info(`[daemon] ${line}`));
  }

  /** Interpreters a daemon was started for, in order. */
  list(): string[] {
    return [...this.warmed];
  }

  /**
   * Start the daemon for `resolved` if this app run has not already. A person
   * who turned the daemon off (`CADGEN_DAEMON=0`, cadgen's own switch) gets
   * none: the viewer and the CLI would run every job cold in that
   * environment, and warming one they will never use is not a favour.
   */
  warm(resolved: ResolvedPython): boolean {
    const env = this.deps.env(resolved);
    if (env.CADGEN_DAEMON === "0" || this.warmed.has(resolved.python)) {
      return false;
    }
    this.warmed.add(resolved.python);
    try {
      const child = this.spawn(resolved.python, DAEMON_ARGS, { cwd: this.deps.cwd(), env, logFile: this.deps.logFile() });
      if (!child) {
        this.warmed.delete(resolved.python);
        return false;
      }
      child.unref();
      if (child.pid) {
        const pid = child.pid;
        spawnedPids.add(pid);
        child.once?.("exit", () => spawnedPids.delete(pid));
      }
      this.log(`warming ${resolved.source} ${resolved.python}${child.pid ? ` (pid ${child.pid})` : ""}`);
      return true;
    } catch (error) {
      this.warmed.delete(resolved.python);
      this.log(`could not start the daemon: ${error instanceof Error ? error.message : String(error)}`);
      return false;
    }
  }
}
