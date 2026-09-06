/**
 * One `cadgen viewer --api-only` per project root (plan §7).
 *
 * The launcher's contract is the whole design here. Run from a directory, it
 * always ends with the URL of a live viewer for that directory and prints one
 * JSON line — `{"url","port","action":"started"|"reused"}` — when asked with
 * `--json`. `started` means this process is the server and its child is ours
 * to keep, restart and stop; `reused` means an instance somebody else started
 * (a terminal, another app) already serves that realpath, the launcher exited
 * after saying so, and there is nothing of ours to kill. The port is an output
 * of launch and nothing here reasons about it.
 *
 * `--api-only` because the client is not the wheel's built copy but the
 * viewer's source compiled into this app's renderer (`CadFileView`); the
 * process serves `/__cad` and `/__tess_cache` and nothing else.
 *
 * `spawn`, `probe` and `delay` are injectable so the crash/restart and
 * reuse-never-killed rules are unit-tested with a fake child
 * (tests/unit/main/viewer.test.ts).
 */
import { spawn as nodeSpawn } from "node:child_process";
import { EventEmitter } from "node:events";
import readline from "node:readline";
import type { Readable } from "node:stream";

import type { ViewerOrigin } from "../../shared/ipc/cad";
import { trackChild } from "../children";
import type { ResolvedPython } from "./runtime";

export interface ViewerChild {
  pid?: number | undefined;
  stdout: Readable;
  stderr: Readable;
  on(event: "exit", listener: (code: number | null, signal: NodeJS.Signals | null) => void): this;
  kill(signal?: NodeJS.Signals): boolean;
}

export type ViewerSpawn = (
  python: string,
  args: string[],
  options: { cwd: string; env: Record<string, string> },
) => ViewerChild;

export const VIEWER_ARGS = ["-m", "cadgen.viewer", "--api-only", "--host", "127.0.0.1", "--json"];

/** How long the launcher has to print its JSON line. */
const LAUNCH_TIMEOUT_MS = 90_000;
/** Crash restarts: 1s, 2s, 4s … capped, and given up after this many in a row. */
const RESTART_BASE_MS = 1_000;
const RESTART_MAX_MS = 30_000;
const RESTART_LIMIT = 5;

export type Launched = { url: string; port: number; action: "started" | "reused" };

/** The launcher's stdout contract: the last JSON line with a url. */
export function parseLaunchLine(line: string): Launched | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("{")) {
    return null;
  }
  try {
    const parsed = JSON.parse(trimmed) as Partial<Launched>;
    if (typeof parsed.url === "string" && (parsed.action === "started" || parsed.action === "reused")) {
      return { url: parsed.url, port: Number(parsed.port), action: parsed.action };
    }
  } catch {
    /* narration, not the contract line */
  }
  return null;
}

/** `http://127.0.0.1:3245/` → `http://127.0.0.1:3245`. */
export function originOf(url: string): string {
  return url.replace(/\/+$/, "");
}

type Entry = {
  root: string;
  origin: string;
  /** Somebody else's instance: probed before use, never killed. */
  reused: boolean;
  child: ViewerChild | null;
  restarts: number;
  stopped: boolean;
};

export type ViewerManagerDeps = {
  /** The interpreter to run, or null when the runtime is not ready. */
  runtime: () => Promise<ResolvedPython | null>;
  /** The environment for that interpreter (PYTHONPATH in a checkout). */
  env: (resolved: ResolvedPython) => Record<string, string>;
  spawn?: ViewerSpawn;
  /** Is an origin answering? Used for reused instances before handing them out. */
  probe?: (origin: string) => Promise<boolean>;
  delay?: (ms: number) => Promise<void>;
  log?: (line: string) => void;
};

function defaultSpawn(python: string, args: string[], options: { cwd: string; env: Record<string, string> }): ViewerChild {
  // A service: `stop` sends it SIGTERM and it unregisters itself on the way
  // out; quitting must not wait for that.
  return trackChild(
    nodeSpawn(python, args, { cwd: options.cwd, env: options.env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true }),
    "service",
  );
}

async function defaultProbe(origin: string): Promise<boolean> {
  try {
    const response = await fetch(`${origin}/__cad/server`, { signal: AbortSignal.timeout(2_000) });
    return response.ok;
  } catch {
    return false;
  }
}

const defaultDelay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export class ViewerManager extends EventEmitter {
  private readonly entries = new Map<string, Entry>();
  private readonly pending = new Map<string, Promise<ViewerOrigin>>();
  private readonly spawn: ViewerSpawn;
  private readonly probe: (origin: string) => Promise<boolean>;
  private readonly delay: (ms: number) => Promise<void>;
  private readonly log: (line: string) => void;

  constructor(private readonly deps: ViewerManagerDeps) {
    super();
    this.spawn = deps.spawn ?? defaultSpawn;
    this.probe = deps.probe ?? defaultProbe;
    this.delay = deps.delay ?? defaultDelay;
    this.log = deps.log ?? ((line) => console.info(`[viewer] ${line}`));
  }

  /** The instances this manager knows about. */
  list(): Array<{ root: string; origin: string; reused: boolean; pid: number | undefined }> {
    return [...this.entries.values()].map((entry) => ({
      root: entry.root,
      origin: entry.origin,
      reused: entry.reused,
      pid: entry.child?.pid,
    }));
  }

  /**
   * The origin serving `root`, launching if need be. Concurrent callers for
   * one root share a launch; a root whose instance is up answers at once.
   */
  originFor(root: string): Promise<ViewerOrigin> {
    const existing = this.entries.get(root);
    if (existing && !existing.stopped) {
      if (!existing.reused) {
        return Promise.resolve({ origin: existing.origin });
      }
      // A reused instance is not ours: check it is still there before
      // handing it out, and launch again (reuse-or-start) when it is not.
      return this.probe(existing.origin).then((alive) => {
        if (alive) {
          return { origin: existing.origin };
        }
        this.entries.delete(root);
        return this.originFor(root);
      });
    }
    let pending = this.pending.get(root);
    if (!pending) {
      pending = this.launch(root).finally(() => this.pending.delete(root));
      this.pending.set(root, pending);
    }
    return pending;
  }

  private async launch(root: string): Promise<ViewerOrigin> {
    const resolved = await this.deps.runtime();
    if (!resolved) {
      return { origin: null, reason: "runtime-not-ready" };
    }
    try {
      const entry = await this.start(root, resolved, 0);
      return { origin: entry.origin };
    } catch (error) {
      this.log(`launch failed for ${root}: ${error instanceof Error ? error.message : String(error)}`);
      return { origin: null, reason: "viewer-failed" };
    }
  }

  private start(root: string, resolved: ResolvedPython, restarts: number): Promise<Entry> {
    return new Promise<Entry>((resolve, reject) => {
      const child = this.spawn(resolved.python, VIEWER_ARGS, { cwd: root, env: this.deps.env(resolved) });
      const stderrTail: string[] = [];
      let settled = false;
      let launched: Launched | null = null;

      const timer = setTimeout(() => {
        if (!settled) {
          settled = true;
          child.kill();
          reject(new Error(`the viewer did not announce itself within ${LAUNCH_TIMEOUT_MS / 1000}s`));
        }
      }, LAUNCH_TIMEOUT_MS);

      readline.createInterface({ input: child.stdout }).on("line", (line) => {
        const parsed = parseLaunchLine(line);
        if (!parsed || settled) {
          return;
        }
        settled = true;
        clearTimeout(timer);
        launched = parsed;
        const entry: Entry = {
          root,
          origin: originOf(parsed.url),
          reused: parsed.action === "reused",
          child: parsed.action === "started" ? child : null,
          restarts,
          stopped: false,
        };
        this.entries.set(root, entry);
        this.log(`${parsed.action} ${entry.origin} for ${root}${child.pid ? ` (pid ${child.pid})` : ""}`);
        this.emit("change", this.list());
        resolve(entry);
      });

      readline.createInterface({ input: child.stderr }).on("line", (line) => {
        stderrTail.push(line);
        if (stderrTail.length > 20) {
          stderrTail.shift();
        }
        this.log(`${root}: ${line}`);
      });

      child.on("exit", (code, signal) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          reject(new Error(`the viewer exited (${code ?? signal}) before announcing itself: ${stderrTail.slice(-3).join(" | ")}`));
          return;
        }
        if (launched?.action !== "started") {
          // The launcher that reported a reuse exits right after: expected.
          return;
        }
        const entry = this.entries.get(root);
        if (!entry || entry.child !== child) {
          return;
        }
        entry.child = null;
        this.entries.delete(root);
        this.emit("change", this.list());
        if (entry.stopped) {
          return;
        }
        this.log(`viewer for ${root} exited (${code ?? signal})`);
        void this.restart(root, resolved, entry.restarts + 1);
      });
    });
  }

  private async restart(root: string, resolved: ResolvedPython, attempt: number): Promise<void> {
    if (attempt > RESTART_LIMIT) {
      this.log(`viewer for ${root} crashed ${RESTART_LIMIT} times in a row; giving up until it is asked for again`);
      return;
    }
    const wait = Math.min(RESTART_MAX_MS, RESTART_BASE_MS * 2 ** (attempt - 1));
    this.log(`restarting the viewer for ${root} in ${wait}ms (attempt ${attempt})`);
    await this.delay(wait);
    // Stopped, or asked for (and relaunched) by someone else, meanwhile.
    if (this.entries.has(root) || this.pending.has(root)) {
      return;
    }
    const pending = this.start(root, resolved, attempt)
      .then((): ViewerOrigin => ({ origin: this.entries.get(root)?.origin ?? null }))
      .catch((error: unknown): ViewerOrigin => {
        this.log(`restart failed for ${root}: ${error instanceof Error ? error.message : String(error)}`);
        void this.restart(root, resolved, attempt + 1);
        return { origin: null, reason: "viewer-failed" };
      })
      .finally(() => this.pending.delete(root));
    this.pending.set(root, pending);
    await pending;
  }

  /** Stop the instance for a root — ours only. A reused one is forgotten, not killed. */
  stop(root: string): void {
    const entry = this.entries.get(root);
    if (!entry) {
      return;
    }
    entry.stopped = true;
    this.entries.delete(root);
    if (entry.child) {
      this.log(`stopping the viewer for ${root} (pid ${entry.child.pid})`);
      entry.child.kill();
    }
    this.emit("change", this.list());
  }

  /** On quit. */
  stopAll(): void {
    for (const root of [...this.entries.keys()]) {
      this.stop(root);
    }
  }
}
