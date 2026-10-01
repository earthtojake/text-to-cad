/**
 * The CAD runtime (plan §8, as revised): which Python runs cadgen.
 *
 * The runtime SHIPS INSIDE THE APP. `scripts/bundle-runtime.mjs` builds a
 * pinned python-build-standalone with cadgen and its whole closure installed,
 * electron-builder copies it beside the app (`Resources/runtime/<os>-<arch>/`),
 * and a packaged text-to-cad has nothing to download, install or repair on first
 * launch. Resolution order, first hit wins:
 *
 *   1. an override — `CAD_DESKTOP_PYTHON` in the environment, then the
 *      `cadPythonOverride` setting (a developer's knob; the e2e suite's too);
 *   2. the bundled runtime beside the app — `resources/runtime/<os>-<arch>/`,
 *      recognised by the `runtime.json` the bundler writes last;
 *   3. a development checkout's `.venv` — the app is running from inside the
 *      text-to-cad repository (a `VERSION` and `packages/cadgen/pyproject.toml`
 *      above it), which is what `npm run dev` has;
 *   4. nothing: `status()` answers `missing`, and says where it looked.
 *
 * Inside a checkout, whichever interpreter wins is run with
 * `PYTHONPATH=<checkout>/packages/cadgen/src`, so the cadgen it imports is the
 * checkout's own rather than whatever was installed last — the venv on a
 * developer's machine points at one checkout and the app may be running from
 * a worktree of another.
 *
 * Every cadgen process also gets `CADGEN_NODE`: cadgen's DXF and mesh-export
 * builders run in Node, and an app launched from the Finder has no `node` on
 * its PATH. The one Node a packaged app is sure to have is its own Electron
 * binary told to be Node (`ELECTRON_RUN_AS_NODE`), the same way the MCP server
 * and the quit watchdog run.
 *
 * Everything with a side effect goes through `RuntimeHost`, so the resolution
 * order and the probe are testable with a fake machine
 * (tests/unit/main/cad-runtime.test.ts). Main wires the real one in
 * `src/main/cad/index.ts`.
 */
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";

import { trackChild } from "../children";

import type { RuntimeStatus } from "../../shared/ipc/runtime";

/* -------------------------------------------------------------------------- */
/* The host                                                                    */
/* -------------------------------------------------------------------------- */

/** `timedOut`: the timeout killed it, so `code` is null and the output partial. */
export type ExecResult = { stdout: string; stderr: string; code: number | null; timedOut?: boolean };

export type ExecOptions = {
  env: Record<string, string>;
  cwd?: string;
  onLine?: (line: string) => void;
  timeoutMs?: number;
  /**
   * Run it as the leader of its own POSIX process group, ended whole when it
   * exits — so a timeout that kills it takes the children it started too.
   */
  processGroup?: boolean;
};

export type RuntimeHost = {
  platform: NodeJS.Platform;
  arch: string;
  /** `app.getPath("userData")`: where the runtime log goes. */
  userData: string;
  /** The app's version, which is the cadgen version it bundles. */
  appVersion: string;
  /** `process.resourcesPath` in a packaged app; `apps/desktop/resources` in a checkout. */
  resourcesDir: string;
  /** Where the app's code lives; the checkout search starts here. */
  appRoot: string;
  /** `app.isPackaged`: a copy a person installed, as opposed to a build run from a checkout. */
  packaged: boolean;
  /** The Node cadgen's builders run under: this Electron binary, as Node. */
  nodeBinary: string;
  env: Record<string, string | undefined>;
  /** The `cadPythonOverride` setting, read fresh on every resolution. */
  overrideSetting: () => string | null;
  /** The clock the failed-probe window is measured on; `Date.now` when omitted. */
  now?: () => number;
  /** `timeoutMs` defaults to the probe's sixty seconds. */
  exec: (file: string, args: string[], options: ExecOptions) => Promise<ExecResult>;
};

const PROBE_TIMEOUT_MS = 60_000;

/**
 * How long a failed probe is remembered. `cad.warm` asks on every session
 * bind and a probe can take up to `DOCTOR_TIMEOUT_MS`, so a broken interpreter
 * re-probed each time floods the log and spawns a doctor per bind. Short
 * enough that fixing it and reopening is not a wait; `repair()` and an
 * override change clear it at once.
 */
const FAILED_PROBE_MS = 60_000;

const MAX_OUTPUT = 64 * 1024 * 1024;

/**
 * Run a program to completion; the runtime's and the viewer's one exec.
 *
 * `spawn`, not `execFile`: `execFile` does not pass `detached` through, so a
 * process-group run would share this process's group and a timeout could not
 * reach the children it started. On a timeout the leader gets SIGTERM — and,
 * for a process-group run, the whole group SIGKILL, so nothing it started is
 * left to run out its own clock.
 */
export function execCommand(file: string, args: string[], options: ExecOptions): Promise<ExecResult> {
  const group = Boolean(options.processGroup) && process.platform !== "win32";
  return new Promise((resolve) => {
    let child: ReturnType<typeof spawn>;
    try {
      child = spawn(file, args, { env: options.env, cwd: options.cwd, windowsHide: true, detached: group });
    } catch (error) {
      resolve({ stdout: "", stderr: error instanceof Error ? error.message : String(error), code: null });
      return;
    }
    // A probe: the answer is not wanted once the app is quitting, and the
    // process must not wait sixty seconds for `import cadgen` to finish.
    trackChild(child, "probe", { ownedProcessGroup: group });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let settled = false;
    const append = (current: string, chunk: string) => (current.length >= MAX_OUTPUT ? current : current + chunk);
    // Decoded by the stream, not per chunk: a UTF-8 character split across
    // two chunks would otherwise become two U+FFFDs in the interpreter's words.
    child.stdout?.setEncoding("utf8");
    child.stderr?.setEncoding("utf8");
    const onLine = options.onLine;
    let buffer = "";
    const feed = (chunk: string) => {
      if (!onLine) {
        return;
      }
      buffer += chunk;
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.trim()) {
          onLine(line);
        }
      }
    };
    child.stdout?.on("data", (chunk: string) => {
      stdout = append(stdout, chunk);
      feed(chunk);
    });
    child.stderr?.on("data", (chunk: string) => {
      stderr = append(stderr, chunk);
      feed(chunk);
    });
    const timer = options.timeoutMs
      ? setTimeout(() => {
          timedOut = true;
          if (group && child.pid) {
            try {
              process.kill(-child.pid, "SIGKILL");
            } catch {
              /* the group is already gone */
            }
          }
          child.kill("SIGTERM");
        }, options.timeoutMs)
      : null;
    const finish = (result: ExecResult) => {
      if (settled) {
        return;
      }
      settled = true;
      if (timer) {
        clearTimeout(timer);
      }
      resolve(result);
    };
    child.once("error", (error) => {
      finish({ stdout, stderr: stderr || error.message, code: null });
    });
    child.once("close", (code) => {
      finish({ stdout, stderr, code: timedOut ? null : code, ...(timedOut ? { timedOut } : {}) });
    });
  });
}

export function nodeHost(options: {
  userData: string;
  appVersion: string;
  resourcesDir: string;
  appRoot: string;
  packaged: boolean;
  overrideSetting: () => string | null;
}): RuntimeHost {
  return {
    platform: process.platform,
    arch: process.arch,
    env: process.env,
    nodeBinary: process.execPath,
    ...options,
    exec: (file, args, execOptions) =>
      execCommand(file, args, { ...execOptions, timeoutMs: execOptions.timeoutMs ?? PROBE_TIMEOUT_MS }),
  };
}

/* -------------------------------------------------------------------------- */
/* Layout                                                                      */
/* -------------------------------------------------------------------------- */

/** electron-builder's names, which the bundler's directories use: `mac-arm64`, `win-x64`, `linux-x64`. */
export function runtimeTarget(platform: NodeJS.Platform, arch: string): string {
  const os = platform === "darwin" ? "mac" : platform === "win32" ? "win" : platform;
  return `${os}-${arch}`;
}

/**
 * Where a bundled runtime lives and what it is made of. The same layout in a
 * checkout (`apps/desktop/resources/runtime/<target>/`) and in a packaged app
 * (`Contents/Resources/runtime/<target>/`), because `resourcesDir` is the one
 * thing that differs between them. `scripts/bundle-runtime.mjs` writes it;
 * `runtime.json` is written last and is the marker of a complete bundle.
 */
export function bundledPaths(resourcesDir: string, platform: NodeJS.Platform, arch: string) {
  const root = path.join(resourcesDir, "runtime", runtimeTarget(platform, arch));
  return {
    root,
    python:
      platform === "win32"
        ? path.join(root, "python", "python.exe")
        : path.join(root, "python", "bin", "python3"),
    marker: path.join(root, "runtime.json"),
  };
}

/**
 * Where an interpreter's console scripts live — the directory that holds
 * `cadgen` beside `python`. On posix that is the interpreter's own directory
 * (`<bundle>/python/bin/`, `.venv/bin/`); on Windows pip writes them to
 * `Scripts/` beside the interpreter, except in a venv where the interpreter
 * is already in `Scripts/`. Prepended to a session's `PATH`
 * (`src/main/acp/sessions.ts`).
 */
export function runtimeBinDir(python: string, platform: NodeJS.Platform): string {
  // The platform's own flavour, so a Windows path is read as one wherever
  // this runs (the unit test checks all four cases from one machine).
  const flavour = platform === "win32" ? path.win32 : path.posix;
  const dir = flavour.dirname(python);
  if (platform !== "win32") {
    return dir;
  }
  return flavour.basename(dir).toLowerCase() === "scripts" ? dir : flavour.join(dir, "Scripts");
}

/** What `scripts/bundle-runtime.mjs` records about a bundle. */
export type BundleMarker = {
  target: string;
  python: string;
  cadgen: string;
  builtAt?: string;
};

export function readBundleMarker(marker: string): BundleMarker | null {
  try {
    const parsed = JSON.parse(fs.readFileSync(marker, "utf8")) as Partial<BundleMarker>;
    return typeof parsed.cadgen === "string" && typeof parsed.target === "string" && typeof parsed.python === "string"
      ? { target: parsed.target, python: parsed.python, cadgen: parsed.cadgen, ...(parsed.builtAt ? { builtAt: parsed.builtAt } : {}) }
      : null;
  } catch {
    return null;
  }
}

/**
 * The repository root above `start`, or null. A checkout is recognised by the
 * two files that only the repository has: `VERSION` (the canonical release
 * version) and `packages/cadgen/pyproject.toml` (the distribution). The
 * search is the same shape as cadgen's own `assets.py` walk, anchored on
 * different files because this app is not inside `packages/`.
 */
export function findCheckout(start: string): string | null {
  let current = path.resolve(start);
  for (;;) {
    if (
      fs.existsSync(path.join(current, "VERSION")) &&
      fs.existsSync(path.join(current, "packages", "cadgen", "pyproject.toml"))
    ) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      return null;
    }
    current = parent;
  }
}

function venvPython(root: string, platform: NodeJS.Platform): string {
  return platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");
}

/**
 * The main checkout behind a git worktree, or null. A worktree's `.git` is a
 * file reading `gitdir: <main>/.git/worktrees/<name>`; worktrees are kept
 * light on purpose (CONTRIBUTING.md: no `.venv` copied in), so the venv to
 * run is the main checkout's while `PYTHONPATH` stays the worktree's own
 * `packages/cadgen/src`.
 */
export function mainCheckoutOfWorktree(root: string): string | null {
  const dotGit = path.join(root, ".git");
  let text: string;
  try {
    if (!fs.statSync(dotGit).isFile()) {
      return null;
    }
    text = fs.readFileSync(dotGit, "utf8");
  } catch {
    return null;
  }
  const match = /^gitdir:\s*(.+?)\s*$/m.exec(text);
  if (!match?.[1]) {
    return null;
  }
  const gitdir = path.resolve(root, match[1]);
  const marker = `${path.sep}.git${path.sep}worktrees${path.sep}`;
  const at = gitdir.indexOf(marker);
  return at === -1 ? null : gitdir.slice(0, at);
}

/**
 * The log is cut back to its last `RUNTIME_LOG_KEEP_BYTES` when it passes
 * `RUNTIME_LOG_MAX_BYTES`. The daemon holds an append fd on this file, so it
 * is rewritten in place (write the tail at the start, then `ftruncate`);
 * renaming it away would leave the daemon writing to an unlinked inode.
 */
export const RUNTIME_LOG_MAX_BYTES = 4 * 1024 * 1024;
export const RUNTIME_LOG_KEEP_BYTES = 1024 * 1024;

async function trimRuntimeLog(file: string): Promise<void> {
  const size = (await fsp.stat(file).catch(() => null))?.size ?? 0;
  if (size <= RUNTIME_LOG_MAX_BYTES) return;
  const handle = await fsp.open(file, "r+");
  try {
    const tail = Buffer.alloc(RUNTIME_LOG_KEEP_BYTES);
    const { bytesRead } = await handle.read(tail, 0, tail.length, size - tail.length);
    // Begin at a line, not in the middle of one. Lines the daemon appends between this read and the truncate are lost.
    const from = tail.subarray(0, bytesRead).indexOf(0x0a) + 1;
    const kept = tail.subarray(from, bytesRead);
    await handle.write(kept, 0, kept.length, 0);
    await handle.truncate(kept.length);
  } finally {
    await handle.close();
  }
}

/** The runtime log: every failed probe and every viewer launch that did not come up. */
export function runtimeLogPath(userData: string): string {
  return path.join(userData, "cad-runtime.log");
}

/* -------------------------------------------------------------------------- */
/* Resolution                                                                  */
/* -------------------------------------------------------------------------- */

export type PythonSource = "override" | "bundled" | "checkout";

export type ResolvedPython = {
  python: string;
  source: PythonSource;
  /** Extra environment every cadgen process gets (`PYTHONPATH` in a checkout). */
  env: Record<string, string>;
};

/**
 * The kernel as the probe found it, when it is not simply fine: `missing` (no
 * OCP), `unsupported` (OCP loads but cadgen's kernel check refuses it) or
 * `failed` (OCP will not load). `message` is the interpreter's words.
 */
export type KernelFinding = { state: string; message: string };

/**
 * What the probe learns about an installed cadgen. `kernel` is null when the
 * CAD kernel the build path needs is fine.
 */
type Probe = { version: string; viewer: boolean; kernel: KernelFinding | null };

/**
 * The probe is cadgen's own report: `python -m cadgen.cli doctor --json`.
 * Its `viewer` says whether `cadgen.viewer` imports (the desktop runs
 * `python -m cadgen.viewer --api-only` per project), and its `kernel` is
 * cadgen's kernel check — the one the STEP path runs, which also refuses an
 * OCP from a distribution cadgen does not build against. What "the kernel"
 * means stays in cadgen; the app reads the verdict. The report's exit code
 * and `pin` are not ours: the pin is a skill's concern.
 *
 * Only a kernel that FAILS to load stops the runtime: it would take every
 * build down with it. A `missing` or `unsupported` kernel is a warning on a
 * ready runtime — `cadgen.viewer` never imports the kernel, so GLB, STL and
 * DXF still open, and an OCP cadgen's check does not recognise may still
 * build — which About shows and a failed STEP build quotes.
 *
 * OCP's import (~2.5 s, far more on a cold disk) is the slow part, paid once
 * per interpreter and usually at project open. The doctor gets its own
 * timeout, and tells its kernel child a shorter one, so the child is ended
 * by the doctor before the doctor is ended by us; the doctor runs as its own
 * process group, so if it is killed anyway, the child goes with it.
 */
const DOCTOR_ARGS = ["-m", "cadgen.cli", "doctor", "--json"];
const DOCTOR_TIMEOUT_MS = 120_000;
/** Seconds; what `cadgen doctor` allows its fresh kernel interpreter. */
const DOCTOR_KERNEL_TIMEOUT_S = 90;

/**
 * A cadgen older than `doctor --json` — or one so old it has no
 * `cadgen.cli` module entry — is asked the old way, kernel imported by name.
 */
const FALLBACK_PROBE_SCRIPT = [
  "import json, cadgen",
  "viewer = True",
  "try:\n    import cadgen.viewer\nexcept Exception:\n    viewer = False",
  "kernel = None",
  "try:\n    import OCP, build123d\nexcept Exception as error:\n    kernel = f'{type(error).__name__}: {error}'",
  "print(json.dumps({'version': cadgen.__version__, 'viewer': viewer, 'kernel': kernel}))",
].join("\n");

/**
 * The report: the LAST stdout line that is a JSON object with a `version`.
 * Not simply the last line — an atexit hook or a sitecustomize can print
 * after it, and that is not a reason to call the runtime broken.
 */
function lastJsonObject(stdout: string): Record<string, unknown> | null {
  const lines = stdout.split("\n");
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index]?.trim();
    if (!line?.startsWith("{")) {
      continue;
    }
    try {
      const parsed: unknown = JSON.parse(line);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && "version" in parsed) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      /* not the report */
    }
  }
  return null;
}

function lastLine(result: ExecResult): string {
  return result.stderr.trim().split("\n").at(-1) || (result.code === null ? "python was killed" : `python exited ${result.code}`);
}

function timedOut(what: string): Error {
  return new Error(`${what} did not answer within ${DOCTOR_TIMEOUT_MS / 1000} s`);
}

/** Kernel states the build daemon cannot start on: it imports OCP to start. */
const DAEMON_BLOCKING_KERNEL = new Set(["missing", "unsupported"]);

/** One probe per interpreter and the cadgen source it runs. */
function probeKey(resolved: ResolvedPython): string {
  return `${resolved.python}\0${resolved.env.PYTHONPATH ?? ""}`;
}

/** A probe that ran: cadgen imported, but the CAD kernel failed to load. */
class KernelError extends Error {}

/**
 * Environment variables a person's shell may carry that would redirect the
 * BUNDLED interpreter at a different Python: another site-packages through
 * PYTHONPATH, another prefix through PYTHONHOME, a startup file. The bundle
 * is a closed world; the checkout's PYTHONPATH is added back afterwards.
 */
const HOST_PYTHON_ENV = ["PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONEXECUTABLE"];

export class CadRuntime {
  private probeCache = new Map<string, Promise<Probe>>();
  /** Probes that failed, by key, until the window closes or `invalidate()`. */
  private failedProbes = new Map<string, { error: unknown; until: number }>();
  /** Interpreters the daemon was not warmed on for their kernel, already logged. */
  private daemonSkipped = new Set<string>();
  private lastError: string | null = null;
  /** Log writes, in order; `status()` waits for them so `log` names a file that exists. */
  private logQueue: Promise<void> = Promise.resolve();

  constructor(private readonly host: RuntimeHost) {}

  /** The checkout this app runs from, when it does. */
  checkout(): string | null {
    return findCheckout(this.host.appRoot);
  }

  private checkoutEnv(): Record<string, string> {
    const root = this.checkout();
    if (!root) {
      return {};
    }
    const src = path.join(root, "packages", "cadgen", "src");
    const existing = this.host.env.PYTHONPATH;
    return { PYTHONPATH: existing ? `${src}${path.delimiter}${existing}` : src };
  }

  /**
   * What goes in front of a session's `PATH` (`src/main/acp/sessions.ts`), so
   * that `cadgen` and `python` inside an agent's session are the app's own.
   *
   * A checkout's `.venv/bin` has the console script pip installed, and is the
   * developer's own environment: that directory goes on the PATH as it is.
   *
   * The bundled runtime does not: it is a `pip install --target` and
   * `scripts/bundle-runtime.mjs` prunes the scripts pip wrote there, because
   * their shebang names the machine that built the bundle. So launchers are
   * written instead, into `<userData>/bin` — `cadgen` (one line that runs the
   * resolved interpreter's `python -m cadgen.cli`, the same dispatcher the
   * console script runs), `python3` and `python` — and that directory is the
   * ONLY one added. The bundle's own `bin/` is never on a session's PATH:
   * whatever else is there is not an agent's to run, and the bundle is signed
   * and read-only (`pip` is refused by its EXTERNALLY-MANAGED marker anyway;
   * resources/README.md). The skills invoke `cadgen`, `python` and `python3`.
   *
   * An override interpreter (`CAD_DESKTOP_PYTHON`, the setting) is the user's
   * own: its bin follows the `cadgen` launcher, and no python launchers are
   * written that would shadow it.
   *
   * Resolution only, never a probe: this is asked for on every session
   * connect, and a session that starts is not the place to wait sixty seconds
   * for `import cadgen`.
   */
  sessionPath(): string[] {
    const resolved = this.resolve();
    if (!resolved) {
      return [];
    }
    const bin = runtimeBinDir(resolved.python, this.host.platform);
    const executable = this.host.platform === "win32" ? "cadgen.exe" : "cadgen";
    if (fs.existsSync(path.join(bin, executable))) {
      return [bin];
    }
    const bundled = resolved.source === "bundled";
    const launchers = this.writeLaunchers(resolved.python, bundled);
    if (!launchers) {
      return [bin];
    }
    return bundled ? [launchers] : [launchers, bin];
  }

  /**
   * `<userData>/bin/cadgen` — and, for the bundled runtime, `python3` and
   * `python` — pointed at `python`. Each is rewritten only when its contents
   * would change (the interpreter moved, or the app was updated), so a launch
   * that changes nothing writes nothing. Without `interpreter`, python
   * launchers left by an earlier bundled resolution are removed.
   */
  private writeLaunchers(python: string, interpreter: boolean): string | null {
    const dir = path.join(this.host.userData, "bin");
    const windows = this.host.platform === "win32";
    const launcher = (args: string) =>
      windows ? `@echo off\r\n"${python}"${args} %*\r\n` : `#!/bin/sh\nexec "${python}"${args} "$@"\n`;
    const name = (base: string) => (windows ? `${base}.cmd` : base);
    const scripts: Array<[string, string]> = [[name("cadgen"), launcher(" -m cadgen.cli")]];
    for (const base of ["python3", "python"]) {
      if (interpreter) {
        scripts.push([name(base), launcher("")]);
      } else {
        try {
          fs.rmSync(path.join(dir, name(base)), { force: true });
        } catch (error) {
          void this.log(`[launcher] ${name(base)}: ${error instanceof Error ? error.message : String(error)}`);
        }
      }
    }
    for (const [fileName, script] of scripts) {
      const file = path.join(dir, fileName);
      try {
        if (fs.readFileSync(file, "utf8") === script) {
          continue;
        }
      } catch {
        /* not written yet, or unreadable: write it below */
      }
      try {
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(file, script, { mode: 0o755 });
        // An existing file keeps its old mode through writeFileSync.
        if (!windows) {
          fs.chmodSync(file, 0o755);
        }
      } catch (error) {
        void this.log(`[launcher] ${file}: ${error instanceof Error ? error.message : String(error)}`);
        return null;
      }
    }
    return dir;
  }

  /** The bundled runtime's layout on this machine. */
  bundled() {
    return bundledPaths(this.host.resourcesDir, this.host.platform, this.host.arch);
  }

  /** The interpreter to run cadgen with. Null when there is none. */
  resolve(): ResolvedPython | null {
    const env = this.checkoutEnv();
    const override = this.host.env.CAD_DESKTOP_PYTHON?.trim() || this.host.overrideSetting()?.trim() || null;
    if (override) {
      return { python: override, source: "override", env };
    }
    const bundled = this.bundled();
    if (fs.existsSync(bundled.marker) && fs.existsSync(bundled.python)) {
      // The bundle's PYTHONPATH, if any, is the checkout's: a checkout that
      // has run the bundler still runs the checkout's cadgen source.
      return { python: bundled.python, source: "bundled", env };
    }
    const checkout = this.checkout();
    if (checkout) {
      const python = venvPython(checkout, this.host.platform);
      if (fs.existsSync(python)) {
        return { python, source: "checkout", env };
      }
      // A worktree carries no venv of its own; the main checkout's runs the
      // worktree's cadgen through the PYTHONPATH already in `env`.
      const main = mainCheckoutOfWorktree(checkout);
      if (main) {
        const mainPython = venvPython(main, this.host.platform);
        if (fs.existsSync(mainPython)) {
          return { python: mainPython, source: "checkout", env };
        }
      }
    }
    return null;
  }

  /**
   * Environment for a cadgen child process: the host's, minus what would
   * redirect a bundled interpreter, plus the resolution's, plus the Node the
   * builders run under. `CADGEN_NODE` set by the person wins.
   */
  processEnv(resolved: ResolvedPython): Record<string, string> {
    const base: Record<string, string> = {};
    for (const [key, value] of Object.entries(this.host.env)) {
      if (value !== undefined && !(resolved.source === "bundled" && HOST_PYTHON_ENV.includes(key))) {
        base[key] = value;
      }
    }
    const node: Record<string, string> = this.host.env.CADGEN_NODE?.trim()
      ? {}
      : { CADGEN_NODE: this.host.nodeBinary, ELECTRON_RUN_AS_NODE: "1" };
    const bundled: Record<string, string> =
      resolved.source === "bundled" ? { PYTHONNOUSERSITE: "1", PYTHONDONTWRITEBYTECODE: "1" } : {};
    return { ...base, ...bundled, ...resolved.env, ...node, PYTHONUNBUFFERED: "1" };
  }

  /** Drop what is known about an interpreter; the next `status()` probes again. */
  invalidate(): void {
    this.probeCache.clear();
    this.failedProbes.clear();
    this.daemonSkipped.clear();
  }

  /** Append to the runtime log. Best effort: a log that cannot be written is not worth a second error. */
  log(line: string): Promise<void> {
    const file = runtimeLogPath(this.host.userData);
    this.logQueue = this.logQueue.then(async () => {
      try {
        await fsp.mkdir(path.dirname(file), { recursive: true });
        await trimRuntimeLog(file);
        await fsp.appendFile(file, `${new Date().toISOString()} ${line}\n`);
      } catch {
        /* see above */
      }
    });
    return this.logQueue;
  }

  private probe(resolved: ResolvedPython): Promise<Probe> {
    const key = probeKey(resolved);
    const failed = this.failedProbes.get(key);
    if (failed && (this.host.now?.() ?? Date.now()) < failed.until) {
      return Promise.reject(failed.error);
    }
    this.failedProbes.delete(key);
    let pending = this.probeCache.get(key);
    if (!pending) {
      pending = (async () => {
        if (!fs.existsSync(resolved.python)) {
          throw new Error(`no interpreter at ${resolved.python}`);
        }
        const env = this.processEnv(resolved);
        const probe = await this.askDoctor(resolved.python, env);
        if (probe.kernel?.state === "failed") {
          throw new KernelError(probe.kernel.message);
        }
        if (probe.kernel) {
          void this.log(`[probe] ${resolved.source} ${resolved.python}: CAD kernel ${probe.kernel.state}: ${probe.kernel.message}`);
        }
        return probe;
      })();
      const probing = pending;
      // Forget this probe — and only this one: an `invalidate()` since may
      // have put a newer probe under the same key.
      const forget = () => {
        if (this.probeCache.get(key) === probing) {
          this.probeCache.delete(key);
        }
      };
      // A failed probe is remembered for `FAILED_PROBE_MS`, not for the
      // session: the person is likely fixing the path, and `repair()` asks
      // again at once. Not remembered at all: a kernel check that timed out,
      // which said nothing about the kernel; the next status asks again
      // rather than quoting it all session.
      probing.then(
        (probe) => {
          if (probe.kernel?.state === "timeout") {
            forget();
          }
        },
        (error: unknown) => {
          // Only if this probe is still the current one: an `invalidate()`
          // since means the answer is about an interpreter setup that is gone.
          if (this.probeCache.get(key) === probing) {
            this.failedProbes.set(key, { error, until: (this.host.now?.() ?? Date.now()) + FAILED_PROBE_MS });
          }
          forget();
          void this.log(`[probe] ${resolved.source} ${resolved.python}: ${error instanceof Error ? error.message : String(error)}`);
        },
      );
      this.probeCache.set(key, probing);
    }
    return pending;
  }

  /** `cadgen doctor --json`, or the old question when no report comes back. */
  private async askDoctor(python: string, env: Record<string, string>): Promise<Probe> {
    const options = { timeoutMs: DOCTOR_TIMEOUT_MS, processGroup: true };
    const result = await this.host.exec(python, DOCTOR_ARGS, {
      env: { ...env, CADGEN_DOCTOR_KERNEL_TIMEOUT: String(DOCTOR_KERNEL_TIMEOUT_S) },
      ...options,
    });
    if (result.timedOut) {
      throw timedOut("cadgen doctor");
    }
    const report = lastJsonObject(result.stdout);
    const kernel = report?.kernel;
    if (report && typeof report.version === "string" && kernel && typeof kernel === "object") {
      const { ok, error, state } = kernel as { ok?: unknown; error?: unknown; state?: unknown };
      const viewer = report.viewer as { ok?: unknown } | undefined;
      const named = typeof state === "string" && state ? state : "failed";
      return {
        version: report.version,
        viewer: Boolean(viewer?.ok),
        kernel: ok === true ? null : { state: named, message: typeof error === "string" && error ? error : `kernel ${named}` },
      };
    }
    // No usable report. Its words go to the log first, whatever happens next.
    const words = lastLine(result);
    void this.log(`[probe] ${python}: cadgen doctor --json gave no report: ${words}`);
    // Only an OLDER cadgen is asked the old way: a doctor without `--json`
    // (argparse refuses it), one whose report has no `kernel`, or a cadgen
    // with no `cadgen.cli` entry at all. A doctor that crashed is not older —
    // the old way would skip cadgen's kernel check and hide the crash — so
    // that is the failure, in the doctor's words.
    const older =
      (report !== null && !kernel) ||
      /unrecognized arguments: --json/.test(result.stderr) ||
      /No module named '?cadgen\.cli(\.__main__)?(?![\w.])/.test(result.stderr);
    if (!older) {
      // cadgen itself absent is not an older cadgen: say that plainly.
      if (/No module named '?cadgen'?(?![\w.])/.test(result.stderr)) {
        throw new Error(`cadgen is not installed in ${python} (No module named 'cadgen')`);
      }
      throw new Error(words);
    }
    const fallback = await this.host.exec(python, ["-c", FALLBACK_PROBE_SCRIPT], { env, ...options });
    if (fallback.timedOut) {
      throw timedOut("python");
    }
    if (fallback.code !== 0) {
      throw new Error(lastLine(fallback));
    }
    const parsed = lastJsonObject(fallback.stdout);
    if (!parsed || typeof parsed.version !== "string") {
      throw new Error("cadgen did not report a version");
    }
    const kernelWords = typeof parsed.kernel === "string" && parsed.kernel ? parsed.kernel : null;
    return {
      version: parsed.version,
      viewer: Boolean(parsed.viewer),
      kernel: kernelWords
        ? { state: kernelWords.startsWith("ModuleNotFoundError") ? "missing" : "failed", message: kernelWords }
        : null,
    };
  }

  /** The state, probing the interpreter once and remembering the answer. */
  async status(): Promise<RuntimeStatus> {
    const logFile = runtimeLogPath(this.host.userData);
    await this.logQueue;
    const log = fs.existsSync(logFile) ? logFile : null;
    const resolved = this.resolve();
    if (!resolved) {
      return {
        state: "missing",
        python: null,
        source: null,
        cadgenVersion: null,
        viewerBuilt: false,
        log,
        message: this.missingMessage(),
      };
    }
    try {
      const probe = await this.probe(resolved);
      this.lastError = null;
      // A kernel warning is written to the log as the probe answers.
      await this.logQueue;
      return {
        state: "ready",
        python: resolved.python,
        source: resolved.source,
        cadgenVersion: probe.version,
        viewerBuilt: probe.viewer,
        log: fs.existsSync(logFile) ? logFile : log,
        ...(probe.kernel ? { kernel: probe.kernel } : {}),
      };
    } catch (error) {
      this.lastError = error instanceof Error ? error.message : String(error);
      await this.logQueue;
      return {
        state: "error",
        python: resolved.python,
        source: resolved.source,
        cadgenVersion: null,
        viewerBuilt: false,
        log: fs.existsSync(logFile) ? logFile : null,
        message:
          error instanceof KernelError
            ? `${SOURCE_NAMES[resolved.source]} (${resolved.python}) imports cadgen, but its CAD kernel fails to load: ${this.lastError}`
            : `${SOURCE_NAMES[resolved.source]} (${resolved.python}) cannot import cadgen: ${this.lastError}`,
      };
    }
  }

  /** A usable interpreter, or null — what the viewer asks before spawning. */
  async ready(): Promise<ResolvedPython | null> {
    const resolved = this.resolve();
    if (!resolved) {
      return null;
    }
    try {
      await this.probe(resolved);
      return resolved;
    } catch {
      return null;
    }
  }

  /**
   * The interpreter to warm the build daemon on: `ready()`'s, unless its CAD
   * kernel is `missing` or `unsupported`. The daemon imports OCP to start, so on such a
   * runtime it would only fail — noisily, on every project open. The viewer
   * is still warmed, but only for a root that holds a model (`warmCad`);
   * this is said once per interpreter in the log.
   */
  async daemonReady(): Promise<ResolvedPython | null> {
    const resolved = this.resolve();
    if (!resolved) {
      return null;
    }
    let probe: Probe;
    try {
      probe = await this.probe(resolved);
    } catch {
      return null;
    }
    // A `timeout` says nothing about the kernel: the daemon may start fine.
    if (!probe.kernel || !DAEMON_BLOCKING_KERNEL.has(probe.kernel.state)) {
      return resolved;
    }
    const key = probeKey(resolved);
    if (!this.daemonSkipped.has(key)) {
      this.daemonSkipped.add(key);
      void this.log(`[daemon] not warmed on ${resolved.python}: CAD kernel ${probe.kernel.state}: ${probe.kernel.message}`);
    }
    return null;
  }

  /**
   * Repair is a fresh look: forget the probe and ask again. There is nothing
   * to install — the runtime shipped with the app — so what this fixes is a
   * probe that failed while the machine was busy, an override that has since
   * been corrected, or a bundle that was missing until the app was updated.
   */
  async repair(): Promise<RuntimeStatus> {
    this.invalidate();
    return this.status();
  }

  private missingMessage(): string {
    const bundled = this.bundled();
    // The card shows this as written. Someone who installed the app cannot act
    // on a build script; the developer running from a checkout can.
    if (this.host.packaged) {
      return `This copy of text-to-cad has no CAD runtime, so models cannot be shown. Reinstall the app to restore it. (Looked for it at ${bundled.root}.)`;
    }
    const checkout = this.checkout();
    const looked = [
      `no bundled runtime at ${bundled.root}`,
      checkout ? `no .venv in the checkout at ${checkout}` : "not running from a checkout",
      "no CAD_DESKTOP_PYTHON or override interpreter",
    ];
    return `No CAD runtime: ${looked.join("; ")}. This build was packaged without its runtime (scripts/bundle-runtime.mjs).`;
  }
}

const SOURCE_NAMES: Record<PythonSource, string> = {
  override: "The override interpreter",
  bundled: "The bundled runtime",
  checkout: "The checkout's .venv",
};
