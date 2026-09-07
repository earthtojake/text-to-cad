/**
 * The CAD runtime (plan §8, as revised): which Python runs cadgen.
 *
 * The runtime SHIPS INSIDE THE APP. `scripts/bundle-runtime.mjs` builds a
 * pinned python-build-standalone with cadgen and its whole closure installed,
 * electron-builder copies it beside the app (`Resources/runtime/<os>-<arch>/`),
 * and a packaged Hardcore has nothing to download, install or repair on first
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
import { execFile } from "node:child_process";

import { trackChild } from "../children";

import type { RuntimeStatus } from "../../shared/ipc/runtime";

/* -------------------------------------------------------------------------- */
/* The host                                                                    */
/* -------------------------------------------------------------------------- */

export type ExecResult = { stdout: string; stderr: string; code: number | null };

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
  /** The Node cadgen's builders run under: this Electron binary, as Node. */
  nodeBinary: string;
  env: Record<string, string | undefined>;
  /** The `cadPythonOverride` setting, read fresh on every resolution. */
  overrideSetting: () => string | null;
  exec: (
    file: string,
    args: string[],
    options: { env: Record<string, string>; cwd?: string; onLine?: (line: string) => void },
  ) => Promise<ExecResult>;
};

const PROBE_TIMEOUT_MS = 60_000;

/** Run a program to completion; the runtime's, the viewer's and the plugin manager's one exec. */
export function execCommand(
  file: string,
  args: string[],
  options: { env: Record<string, string>; cwd?: string; onLine?: (line: string) => void; timeoutMs?: number },
): Promise<ExecResult> {
  return new Promise((resolve) => {
    // A probe: the answer is not wanted once the app is quitting, and the
    // process must not wait sixty seconds for `import cadgen` to finish.
    const child = trackChild(execFile(
      file,
      args,
      {
        env: options.env,
        cwd: options.cwd,
        timeout: options.timeoutMs,
        maxBuffer: 64 * 1024 * 1024,
        windowsHide: true,
      },
      (error, stdout, stderr) => {
        const code = error && "code" in error && typeof error.code === "number" ? error.code : error ? null : 0;
        resolve({ stdout: String(stdout), stderr: String(stderr), code: error ? code : 0 });
      },
    ), "probe");
    if (options.onLine) {
      const onLine = options.onLine;
      let buffer = "";
      const feed = (chunk: Buffer | string) => {
        buffer += String(chunk);
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.trim()) {
            onLine(line);
          }
        }
      };
      child.stdout?.on("data", feed);
      child.stderr?.on("data", feed);
    }
  });
}

export function nodeHost(options: {
  userData: string;
  appVersion: string;
  resourcesDir: string;
  appRoot: string;
  overrideSetting: () => string | null;
}): RuntimeHost {
  return {
    platform: process.platform,
    arch: process.arch,
    env: process.env,
    nodeBinary: process.execPath,
    ...options,
    exec: (file, args, execOptions) => execCommand(file, args, { ...execOptions, timeoutMs: PROBE_TIMEOUT_MS }),
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

/** What `python -c` answers about an installed cadgen. */
type Probe = { version: string; viewer: boolean };

/**
 * `cadgen.viewer` is imported as well as `cadgen`: the desktop runs
 * `python -m cadgen.viewer --api-only` per project, so an interpreter that
 * imports cadgen but not its viewer is not a runtime for this app.
 */
const PROBE_SCRIPT = [
  "import json, cadgen",
  "viewer = True",
  "try:\n    import cadgen.viewer\nexcept Exception:\n    viewer = False",
  "print(json.dumps({'version': cadgen.__version__, 'viewer': viewer}))",
].join("\n");

/**
 * Environment variables a person's shell may carry that would redirect the
 * BUNDLED interpreter at a different Python: another site-packages through
 * PYTHONPATH, another prefix through PYTHONHOME, a startup file. The bundle
 * is a closed world; the checkout's PYTHONPATH is added back afterwards.
 */
const HOST_PYTHON_ENV = ["PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONEXECUTABLE"];

export class CadRuntime {
  private probeCache = new Map<string, Promise<Probe>>();
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
  }

  /** Append to the runtime log. Best effort: a log that cannot be written is not worth a second error. */
  log(line: string): Promise<void> {
    const file = runtimeLogPath(this.host.userData);
    this.logQueue = this.logQueue.then(async () => {
      try {
        await fsp.mkdir(path.dirname(file), { recursive: true });
        await fsp.appendFile(file, `${new Date().toISOString()} ${line}\n`);
      } catch {
        /* see above */
      }
    });
    return this.logQueue;
  }

  private probe(resolved: ResolvedPython): Promise<Probe> {
    const key = `${resolved.python}\0${resolved.env.PYTHONPATH ?? ""}`;
    let pending = this.probeCache.get(key);
    if (!pending) {
      pending = (async () => {
        if (!fs.existsSync(resolved.python)) {
          throw new Error(`no interpreter at ${resolved.python}`);
        }
        const result = await this.host.exec(resolved.python, ["-c", PROBE_SCRIPT], {
          env: this.processEnv(resolved),
        });
        if (result.code !== 0) {
          throw new Error(result.stderr.trim().split("\n").at(-1) || `python exited ${result.code}`);
        }
        const line = result.stdout.trim().split("\n").at(-1) ?? "";
        const parsed = JSON.parse(line) as Partial<Probe>;
        if (typeof parsed.version !== "string") {
          throw new Error("cadgen did not report a version");
        }
        return { version: parsed.version, viewer: Boolean(parsed.viewer) };
      })();
      // A failed probe is not cached: the person is likely fixing the path.
      pending.catch((error: unknown) => {
        this.probeCache.delete(key);
        void this.log(`[probe] ${resolved.source} ${resolved.python}: ${error instanceof Error ? error.message : String(error)}`);
      });
      this.probeCache.set(key, pending);
    }
    return pending;
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
      return {
        state: "ready",
        python: resolved.python,
        source: resolved.source,
        cadgenVersion: probe.version,
        viewerBuilt: probe.viewer,
        log,
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
        message: `${SOURCE_NAMES[resolved.source]} (${resolved.python}) cannot import cadgen: ${this.lastError}`,
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
