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
 * A crash restarts the child with backoff and gives up after
 * `RESTART_LIMIT` in a row; an instance that stays up `HEALTHY_UPTIME_MS`
 * starts the count again. `launch`, `restart` and `stop` share a per-root
 * generation: every stop bumps it (`stopAll` bumps all roots, and stops the
 * ones still launching), and each launch or restart checks it after every
 * await, so a stop during a backoff or a launch stays a stop. At most
 * `MAX_LIVE_VIEWERS` children run; going over stops the least recently asked
 * for root that `inUse` (a CAD tab is open on it) does not name, and when
 * every other root is named the bound is exceeded.
 *
 * `spawn`, `probe`, `delay`, `now`, `inUse` and `maxLive` are injectable so
 * the crash/restart, eviction and reuse-never-killed rules are unit-tested
 * with a fake child (tests/unit/main/viewer.test.ts).
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
/**
 * Crash restarts: 1s, 2s, 4s … capped, and given up after this many in a row.
 * "In a row" ends when an instance stays up `HEALTHY_UPTIME_MS`: its next
 * crash starts the count again, so a viewer that dies once a day is never
 * given up on.
 */
const RESTART_BASE_MS = 1_000;
const RESTART_MAX_MS = 30_000;
const RESTART_LIMIT = 5;
const HEALTHY_UPTIME_MS = 5 * 60_000;
/** Live viewers this manager started; opening one more stops the least recently asked for. */
const MAX_LIVE_VIEWERS = 3;

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
  /** Crashes in a row that led to this instance. */
  restarts: number;
  /** When it announced, on the manager's clock. */
  startedAt: number;
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
  /** The clock uptime is measured on; `Date.now` when omitted. */
  now?: () => number;
  /**
   * Roots that must keep their viewer (a CAD tab is open on them). Asked when
   * a launch would put the manager over its bound; never evicted.
   */
  inUse?: () => Iterable<string>;
  /** The bound on live viewers; `MAX_LIVE_VIEWERS` when omitted. */
  maxLive?: number;
  log?: (line: string) => void;
};

function defaultSpawn(python: string, args: string[], options: { cwd: string; env: Record<string, string> }): ViewerChild {
  // A service: `stop` sends it SIGTERM and it unregisters itself on the way
  // out; quitting must not wait for that. The POSIX group belongs only to
  // this launcher and its transient compile workers. A reused viewer lives
  // in another group; the shared warm daemon starts a separate session.
  const ownedProcessGroup = process.platform !== "win32";
  return trackChild(
    nodeSpawn(python, args, { cwd: options.cwd, env: options.env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true, detached: ownedProcessGroup }),
    "service",
    { ownedProcessGroup },
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

class StoppedWhileLaunching extends Error {
  constructor(root: string) {
    super(`the viewer for ${root} was stopped while launching`);
  }
}

export class ViewerManager extends EventEmitter {
  private readonly entries = new Map<string, Entry>();
  private readonly pending = new Map<string, Promise<ViewerOrigin>>();
  /** The child of each launch still waiting to announce, so a stop can kill it now. */
  private readonly launching = new Map<string, ViewerChild>();
  /**
   * Bumped by every `stop` (entry or not) and, for all roots at once, by
   * `stopAll`. A crash's restart remembers the generation it was scheduled
   * under and gives up if it moved: a stop during the backoff or the
   * relaunch — on quit, or a deleted worktree session — must stay a stop.
   */
  private readonly stops = new Map<string, number>();
  /** When each root was last asked for, as a counter: the order eviction goes in. */
  private readonly lastAsked = new Map<string, number>();
  private askedCount = 0;
  private stopsAll = 0;
  private readonly spawn: ViewerSpawn;
  private readonly probe: (origin: string) => Promise<boolean>;
  private readonly delay: (ms: number) => Promise<void>;
  private readonly now: () => number;
  private readonly log: (line: string) => void;

  constructor(private readonly deps: ViewerManagerDeps) {
    super();
    this.spawn = deps.spawn ?? defaultSpawn;
    this.probe = deps.probe ?? defaultProbe;
    this.delay = deps.delay ?? defaultDelay;
    this.now = deps.now ?? Date.now;
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
    this.lastAsked.set(root, ++this.askedCount);
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
      const launch = this.launch(root).finally(() => this.forgetPending(root, launch));
      pending = launch;
      this.pending.set(root, pending);
    }
    return pending;
  }

  /** Drop `promise` from the pending launches — unless a stop has since let a newer one take its place. */
  private forgetPending(root: string, promise: Promise<ViewerOrigin>): void {
    if (this.pending.get(root) === promise) {
      this.pending.delete(root);
    }
  }

  private async launch(root: string): Promise<ViewerOrigin> {
    // Taken before the first await: a session deleted while its viewer is
    // still coming up (the runtime resolving, then up to a minute and a half
    // of launch) stops a root that has no entry yet. The launch that
    // announces afterwards is killed, not kept serving a removed worktree.
    const generation = this.stopGeneration(root);
    const resolved = await this.deps.runtime();
    if (!resolved) {
      return { origin: null, reason: "runtime-not-ready" };
    }
    // A stop while the runtime resolved (a probe can take seconds) already
    // let the next ask start its own launch; spawning here too would race it
    // and overwrite its `launching` child.
    if (generation !== this.stopGeneration(root)) {
      return { origin: null, reason: "viewer-failed", message: new StoppedWhileLaunching(root).message };
    }
    try {
      const entry = await this.start(root, resolved, 0, generation);
      return { origin: entry.origin };
    } catch (error) {
      if (error instanceof StoppedWhileLaunching) {
        return { origin: null, reason: "viewer-failed", message: error.message };
      }
      const message = error instanceof Error ? error.message : String(error);
      this.log(`launch failed for ${root}: ${message}`);
      return { origin: null, reason: "viewer-failed", message };
    }
  }

  private stopGeneration(root: string): number {
    return this.stopsAll + (this.stops.get(root) ?? 0);
  }

  /** `generation`: the root's stop generation when the launch was asked for; a launch that announces after a stop is dropped. */
  private start(root: string, resolved: ResolvedPython, restarts: number, generation?: number): Promise<Entry> {
    return new Promise<Entry>((resolve, reject) => {
      const child = this.spawn(resolved.python, VIEWER_ARGS, { cwd: root, env: this.deps.env(resolved) });
      const stderrTail: string[] = [];
      let settled = false;
      this.launching.set(root, child);
      const announced = () => {
        if (this.launching.get(root) === child) this.launching.delete(root);
      };
      let launched: Launched | null = null;

      const timer = setTimeout(() => {
        if (!settled) {
          settled = true;
          announced();
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
        announced();
        clearTimeout(timer);
        launched = parsed;
        if (generation !== undefined && generation !== this.stopGeneration(root)) {
          if (parsed.action === "started") {
            this.log(`the viewer for ${root} was stopped while launching; stopping it (pid ${child.pid})`);
            child.kill();
          }
          reject(new StoppedWhileLaunching(root));
          return;
        }
        const entry: Entry = {
          root,
          origin: originOf(parsed.url),
          reused: parsed.action === "reused",
          child: parsed.action === "started" ? child : null,
          restarts,
          startedAt: this.now(),
          stopped: false,
        };
        this.entries.set(root, entry);
        this.evictBeyondBound(root);
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
          announced();
          clearTimeout(timer);
          if (generation !== undefined && generation !== this.stopGeneration(root)) {
            reject(new StoppedWhileLaunching(root));
            return;
          }
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
        // One that stayed up was healthy: this is a first crash, not another in a row.
        const healthy = this.now() - entry.startedAt >= HEALTHY_UPTIME_MS;
        void this.restart(root, resolved, healthy ? 1 : entry.restarts + 1);
      });
    });
  }

  private async restart(root: string, resolved: ResolvedPython, attempt: number): Promise<void> {
    if (attempt > RESTART_LIMIT) {
      this.log(`viewer for ${root} crashed ${RESTART_LIMIT} times in a row (none staying up ${HEALTHY_UPTIME_MS / 60_000} minutes); giving up until it is asked for again`);
      return;
    }
    const generation = this.stopGeneration(root);
    const wait = Math.min(RESTART_MAX_MS, RESTART_BASE_MS * 2 ** (attempt - 1));
    this.log(`restarting the viewer for ${root} in ${wait}ms (attempt ${attempt})`);
    await this.delay(wait);
    // Stopped, or asked for (and relaunched) by someone else, meanwhile.
    if (generation !== this.stopGeneration(root) || this.entries.has(root) || this.pending.has(root)) {
      return;
    }
    const pending = this.start(root, resolved, attempt, generation)
      .then((): ViewerOrigin => ({ origin: this.entries.get(root)?.origin ?? null }))
      .catch((error: unknown): ViewerOrigin => {
        if (error instanceof StoppedWhileLaunching) {
          return { origin: null, reason: "viewer-failed", message: error.message };
        }
        const message = error instanceof Error ? error.message : String(error);
        this.log(`restart failed for ${root}: ${message}`);
        void this.restart(root, resolved, attempt + 1);
        return { origin: null, reason: "viewer-failed", message };
      })
      .finally(() => this.forgetPending(root, pending));
    this.pending.set(root, pending);
    await pending;
  }

  /**
   * Keep the viewers this manager started within the bound: past it, stop the
   * least recently asked-for one whose root has no CAD tab open. `keep` (the
   * one that just came up) is never the victim. A project root that idles for
   * the rest of the session is otherwise a Python process until quit.
   */
  private evictBeyondBound(keep: string): void {
    const bound = this.deps.maxLive ?? MAX_LIVE_VIEWERS;
    const owned = () => [...this.entries.values()].filter((entry) => entry.child && entry.root !== keep);
    const busy = new Set(this.deps.inUse?.() ?? []);
    while ([...this.entries.values()].filter((entry) => entry.child).length > bound) {
      const victim = owned()
        .filter((entry) => !busy.has(entry.root))
        .sort((a, b) => (this.lastAsked.get(a.root) ?? 0) - (this.lastAsked.get(b.root) ?? 0))[0];
      if (!victim) {
        return;
      }
      this.log(`more than ${bound} viewers are running; stopping the least recently used, for ${victim.root}`);
      this.stop(victim.root);
    }
  }

  /** Stop the instance for a root — ours only. A reused one is forgotten, not killed. */
  stop(root: string): void {
    this.stops.set(root, (this.stops.get(root) ?? 0) + 1);
    this.lastAsked.delete(root);
    // A launch still coming up is stopped now, not when it announces, and the
    // next `originFor` starts its own: joining this one would hand its caller
    // "stopped while launching" for a viewer it just asked for. (Whoever
    // already joined sees that failure once.)
    this.pending.delete(root);
    const starting = this.launching.get(root);
    if (starting) {
      this.launching.delete(root);
      this.log(`stopping the viewer for ${root} while it launches (pid ${starting.pid})`);
      starting.kill();
    }
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
    this.stopsAll += 1;
    // A root still launching has no entry: its pending launch and its child
    // are found by their own maps, or the next ask would join a stopped launch.
    const roots = new Set([...this.entries.keys(), ...this.pending.keys(), ...this.launching.keys()]);
    for (const root of roots) {
      this.stop(root);
    }
  }
}
