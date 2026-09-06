/**
 * The managed CAD runtime (plan §8): which Python runs cadgen, and how one is
 * provisioned when there is none.
 *
 * Resolution order, first hit wins:
 *
 *   1. an override — `CAD_DESKTOP_PYTHON` in the environment, then the
 *      `cadPythonOverride` setting;
 *   2. a development checkout's `.venv` — the app is running from inside the
 *      text-to-cad repository (a `VERSION` and `packages/cadgen/pyproject.toml`
 *      above it), so the checkout's interpreter runs the checkout's cadgen;
 *   3. the managed runtime under `userData/runtime/<appVersion>/` —
 *      python-build-standalone plus `cadgen==<appVersion>`;
 *   4. nothing: `status()` answers `missing` and `provision()` builds 3.
 *
 * Inside a checkout, whichever interpreter wins is run with
 * `PYTHONPATH=<checkout>/packages/cadgen/src`, so the cadgen it imports is the
 * checkout's own rather than whatever the venv installed last — the venv on a
 * developer's machine points at one checkout and the app may be running from a
 * worktree of another.
 *
 * Everything with a side effect goes through `RuntimeHost`, so the resolution
 * order and the provisioning sequence are testable with a fake machine
 * (tests/unit/main/cad-runtime.test.ts). Main wires the real one in
 * `src/main/cad/index.ts`.
 */
import { createHash } from "node:crypto";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import { execFile } from "node:child_process";

import type { RuntimeStatus } from "../../shared/ipc/runtime";

/* -------------------------------------------------------------------------- */
/* The pinned interpreter                                                      */
/* -------------------------------------------------------------------------- */

/**
 * One python-build-standalone release, `install_only` flavour, for the four
 * platforms the app packages for. The hashes are the release's `SHA256SUMS`
 * lines for these files, copied in when the release was pinned, and every
 * download is checked against them before it is extracted — a mirror, a proxy
 * or a truncated transfer cannot hand the app an interpreter it did not ask
 * for.
 *
 * 3.13 rather than 3.11: cadgen's `requires-python` is >=3.11 and its wheels
 * (cadquery-ocp, build123d) ship for 3.13, and the constraints file
 * `scripts/cad-resources.mjs` writes is frozen from a 3.13 venv, so the managed
 * runtime and the development runtime resolve the same dependency closure.
 */
export const PYTHON_BUILD = {
  release: "20260901",
  version: "3.13.15",
  assets: {
    "darwin-arm64": {
      file: "cpython-3.13.15+20260901-aarch64-apple-darwin-install_only.tar.gz",
      sha256: "b9054a9d3d54f4cb5573d44907fddb29874b08909bde73f29f2868cf872223ee",
    },
    "darwin-x64": {
      file: "cpython-3.13.15+20260901-x86_64-apple-darwin-install_only.tar.gz",
      sha256: "49f0d97f506b855eed60b74a8ac138595c5b39799a6aa5e0d7ca8abe1019a4d4",
    },
    "win32-x64": {
      file: "cpython-3.13.15+20260901-x86_64-pc-windows-msvc-install_only.tar.gz",
      sha256: "9bcc038a0bf180612ed56dec93d4977d035e80b8d9320ef51a38c287baf134b7",
    },
    "linux-x64": {
      file: "cpython-3.13.15+20260901-x86_64-unknown-linux-gnu-install_only.tar.gz",
      sha256: "0651dd7157d3debf769e15a52c1de9de7fbcdc36ba72faf79fde3c44f14d9461",
    },
  },
} as const;

export type PythonBuildTarget = keyof typeof PYTHON_BUILD.assets;

/** The shape of the pin, so a test can provision against bytes it made up. */
export type PythonBuild = {
  release: string;
  version: string;
  assets: Record<PythonBuildTarget, { file: string; sha256: string }>;
};

export function pythonBuildTarget(platform: NodeJS.Platform, arch: string): PythonBuildTarget | null {
  const key = `${platform}-${arch}`;
  return key in PYTHON_BUILD.assets ? (key as PythonBuildTarget) : null;
}

export function pythonBuildUrl(target: PythonBuildTarget, build: PythonBuild = PYTHON_BUILD): string {
  const { file } = build.assets[target];
  return `https://github.com/astral-sh/python-build-standalone/releases/download/${build.release}/${file}`;
}

/* -------------------------------------------------------------------------- */
/* The host                                                                    */
/* -------------------------------------------------------------------------- */

export type ExecResult = { stdout: string; stderr: string; code: number | null };

export type RuntimeHost = {
  platform: NodeJS.Platform;
  arch: string;
  /** `app.getPath("userData")`. */
  userData: string;
  /** The app's version, which is the cadgen version it installs. */
  appVersion: string;
  /** `process.resourcesPath` in a packaged app; `apps/desktop/resources` in a checkout. */
  resourcesDir: string;
  /** Where the app's code lives; the checkout search starts here. */
  appRoot: string;
  env: Record<string, string | undefined>;
  /** The `cadPythonOverride` setting, read fresh on every resolution. */
  overrideSetting: () => string | null;
  exec: (
    file: string,
    args: string[],
    options: { env: Record<string, string>; cwd?: string; onLine?: (line: string) => void },
  ) => Promise<ExecResult>;
  /** Fetch `url` into `dest`, reporting bytes as they arrive. */
  download: (url: string, dest: string, onProgress: (received: number, total: number | null) => void) => Promise<void>;
  /** Unpack a `.tar.gz` into `dest`. */
  extract: (archive: string, dest: string) => Promise<void>;
};

const PROBE_TIMEOUT_MS = 60_000;

/** Run a program to completion; the runtime's, the viewer's and the plugin manager's one exec. */
export function execCommand(
  file: string,
  args: string[],
  options: { env: Record<string, string>; cwd?: string; onLine?: (line: string) => void; timeoutMs?: number },
): Promise<ExecResult> {
  return new Promise((resolve) => {
    const child = execFile(
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
    );
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

async function downloadToFile(
  url: string,
  dest: string,
  onProgress: (received: number, total: number | null) => void,
): Promise<void> {
  const response = await fetch(url, { redirect: "follow" });
  if (!response.ok || !response.body) {
    throw new Error(`download failed: HTTP ${response.status} for ${url}`);
  }
  const length = response.headers.get("content-length");
  const total = length ? Number(length) : null;
  let received = 0;
  await fsp.mkdir(path.dirname(dest), { recursive: true });
  const reader = response.body.getReader();
  const out = fs.createWriteStream(dest);
  const source = (async function* () {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        return;
      }
      received += value.byteLength;
      onProgress(received, total);
      yield value;
    }
  })();
  await pipeline(source, out);
}

/**
 * `tar` rather than a JavaScript tar library: every platform the app packages
 * for ships one (macOS and Linux always have; Windows 10 1803+ carries bsdtar
 * as `tar.exe`), and a gzip tarball of 25–120 MB is exactly what it is for.
 */
async function extractTarGz(archive: string, dest: string): Promise<void> {
  await fsp.mkdir(dest, { recursive: true });
  const result = await execCommand("tar", ["-xzf", archive, "-C", dest], {
    env: { ...(process.env as Record<string, string>) },
    timeoutMs: 10 * 60_000,
  });
  if (result.code !== 0) {
    throw new Error(`tar failed (${result.code}): ${result.stderr.trim() || result.stdout.trim()}`);
  }
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
    ...options,
    exec: (file, args, execOptions) => execCommand(file, args, { ...execOptions, timeoutMs: PROBE_TIMEOUT_MS }),
    download: downloadToFile,
    extract: extractTarGz,
  };
}

/* -------------------------------------------------------------------------- */
/* Resolution                                                                  */
/* -------------------------------------------------------------------------- */

export type PythonSource = "override" | "checkout" | "managed";

export type ResolvedPython = {
  python: string;
  source: PythonSource;
  /** Extra environment every cadgen process gets (`PYTHONPATH` in a checkout). */
  env: Record<string, string>;
};

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

/** The managed layout under `userData/runtime/<version>/`. */
export function managedPaths(userData: string, appVersion: string, platform: NodeJS.Platform) {
  const root = path.join(userData, "runtime", appVersion);
  return {
    root,
    pythonDir: path.join(root, "python"),
    python:
      platform === "win32"
        ? path.join(root, "python", "python.exe")
        : path.join(root, "python", "bin", "python3"),
    marker: path.join(root, "installed.json"),
    log: path.join(root, "provision.log"),
    downloads: path.join(root, "downloads"),
  };
}

export type ProvisionPhase = "download" | "verify" | "extract" | "install" | "check";

export type Progress = {
  status: RuntimeStatus;
  message?: string;
  percent?: number;
};

/** What `python -c` answers about an installed cadgen. */
type Probe = { version: string; viewer: boolean };

const PROBE_SCRIPT = [
  "import json, cadgen",
  "from cadgen import assets",
  "d = assets.viewer_dist_dir()",
  "print(json.dumps({'version': cadgen.__version__, 'viewer': (d / 'index.html').is_file()}))",
].join("; ");

export class CadRuntime {
  private probeCache = new Map<string, Promise<Probe>>();
  private installing: Promise<RuntimeStatus> | null = null;
  private lastError: { message: string; log: string | null } | null = null;
  private readonly listeners = new Set<(progress: Progress) => void>();

  constructor(
    private readonly host: RuntimeHost,
    private readonly build: PythonBuild = PYTHON_BUILD,
  ) {}

  onProgress(listener: (progress: Progress) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

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
   * The interpreter to run cadgen with, without provisioning anything. Null
   * when there is none yet.
   */
  resolve(): ResolvedPython | null {
    const env = this.checkoutEnv();
    const override = this.host.env.CAD_DESKTOP_PYTHON?.trim() || this.host.overrideSetting()?.trim() || null;
    if (override) {
      return { python: override, source: "override", env };
    }
    const checkout = this.checkout();
    if (checkout) {
      const python = venvPython(checkout, this.host.platform);
      if (fs.existsSync(python)) {
        return { python, source: "checkout", env };
      }
    }
    const managed = managedPaths(this.host.userData, this.host.appVersion, this.host.platform);
    if (fs.existsSync(managed.marker) && fs.existsSync(managed.python)) {
      return { python: managed.python, source: "managed", env };
    }
    return null;
  }

  /** Environment for a cadgen child process: the host's plus the resolution's. */
  processEnv(resolved: ResolvedPython): Record<string, string> {
    const base: Record<string, string> = {};
    for (const [key, value] of Object.entries(this.host.env)) {
      if (value !== undefined) {
        base[key] = value;
      }
    }
    return { ...base, ...resolved.env, PYTHONUNBUFFERED: "1" };
  }

  /** Drop what is known about an interpreter; the next `status()` probes again. */
  invalidate(): void {
    this.probeCache.clear();
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
      pending.catch(() => this.probeCache.delete(key));
      this.probeCache.set(key, pending);
    }
    return pending;
  }

  /** The state, probing the interpreter once and remembering the answer. */
  async status(): Promise<RuntimeStatus> {
    if (this.installing) {
      return this.installingStatus();
    }
    return this.probedStatus();
  }

  /** `status()` without the installing short-circuit: what a provision ends by asking. */
  private async probedStatus(): Promise<RuntimeStatus> {
    const resolved = this.resolve();
    if (!resolved) {
      return {
        state: this.lastError ? "error" : "missing",
        python: null,
        cadgenVersion: null,
        viewerBuilt: false,
        overridden: false,
        log: this.lastError?.log ?? null,
        message: this.lastError?.message ?? (this.provisionable() ? undefined : this.unsupportedMessage()),
      };
    }
    try {
      const probe = await this.probe(resolved);
      return {
        state: "ready",
        python: resolved.python,
        cadgenVersion: probe.version,
        viewerBuilt: probe.viewer,
        overridden: resolved.source === "override",
        log: null,
      };
    } catch (error) {
      return {
        state: "error",
        python: resolved.python,
        cadgenVersion: null,
        viewerBuilt: false,
        overridden: resolved.source === "override",
        log: null,
        message: `${resolved.source === "override" ? "The override interpreter" : "The interpreter"} cannot import cadgen: ${
          error instanceof Error ? error.message : String(error)
        }`,
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

  private provisionable(): boolean {
    return pythonBuildTarget(this.host.platform, this.host.arch) !== null;
  }

  private unsupportedMessage(): string {
    return `No managed Python is published for ${this.host.platform}/${this.host.arch}. Point the override at an interpreter with cadgen ${this.host.appVersion} installed.`;
  }

  private installingStatus(message?: string): RuntimeStatus {
    const managed = managedPaths(this.host.userData, this.host.appVersion, this.host.platform);
    return {
      state: "installing",
      python: fs.existsSync(managed.python) ? managed.python : null,
      cadgenVersion: null,
      viewerBuilt: false,
      overridden: false,
      log: null,
      message,
    };
  }

  /**
   * Install or reinstall the managed runtime. With an override or a checkout
   * in force there is nothing to install — the answer is a fresh probe of
   * that interpreter, which is what "Repair" means for it.
   */
  async repair(): Promise<RuntimeStatus> {
    this.invalidate();
    const resolved = this.resolve();
    if (resolved && resolved.source !== "managed") {
      return this.status();
    }
    return this.provision();
  }

  /** Provision the managed runtime from scratch, streaming progress. */
  provision(): Promise<RuntimeStatus> {
    if (!this.installing) {
      this.installing = this.provisionUncached().finally(() => {
        this.installing = null;
      });
    }
    return this.installing;
  }

  private emit(progress: Progress) {
    for (const listener of this.listeners) {
      listener(progress);
    }
  }

  private async provisionUncached(): Promise<RuntimeStatus> {
    const target = pythonBuildTarget(this.host.platform, this.host.arch);
    const managed = managedPaths(this.host.userData, this.host.appVersion, this.host.platform);
    const logLines: string[] = [];
    const log = (line: string) => {
      logLines.push(line);
    };
    const report = (phase: ProvisionPhase, message: string, percent: number) => {
      log(`[${phase}] ${message}`);
      this.emit({ status: this.installingStatus(message), message, percent: Math.max(0, Math.min(100, percent)) });
    };
    this.lastError = null;
    this.invalidate();

    try {
      if (!target) {
        throw new Error(this.unsupportedMessage());
      }
      const asset = this.build.assets[target];

      await fsp.rm(managed.root, { recursive: true, force: true });
      await fsp.mkdir(managed.downloads, { recursive: true });

      // 1. download
      const archive = path.join(managed.downloads, asset.file);
      report("download", `Downloading Python ${this.build.version}…`, 0);
      let lastPercent = -1;
      await this.host.download(pythonBuildUrl(target, this.build), archive, (received, total) => {
        const fraction = total ? received / total : 0;
        const percent = Math.floor(fraction * 60);
        if (percent !== lastPercent) {
          lastPercent = percent;
          const mb = (received / 1024 / 1024).toFixed(0);
          report(
            "download",
            total
              ? `Downloading Python ${this.build.version} (${mb} of ${(total / 1024 / 1024).toFixed(0)} MB)`
              : `Downloading Python (${mb} MB)`,
            percent,
          );
        }
      });

      // 2. verify
      report("verify", "Verifying the download…", 60);
      const digest = await sha256File(archive);
      if (digest !== asset.sha256) {
        throw new Error(`checksum mismatch for ${asset.file}: expected ${asset.sha256}, got ${digest}`);
      }

      // 3. extract — the archive's top-level directory is `python/`.
      report("extract", "Unpacking Python…", 65);
      await this.host.extract(archive, managed.root);
      if (!fs.existsSync(managed.python)) {
        throw new Error(`the archive did not produce ${managed.python}`);
      }
      await fsp.rm(managed.downloads, { recursive: true, force: true });

      // 4. install cadgen
      report("install", `Installing cadgen ${this.host.appVersion}…`, 75);
      const { args, description } = this.pipArgs();
      log(`[install] ${description}`);
      let installPercent = 75;
      const pipEnv = { ...this.processEnv({ python: managed.python, source: "managed", env: {} }), PIP_DISABLE_PIP_VERSION_CHECK: "1" };
      const pip = await this.host.exec(managed.python, ["-m", "pip", "install", ...args], {
        env: pipEnv,
        onLine: (line) => {
          log(line);
          if (/^(Collecting|Downloading|Installing collected|Successfully)/.test(line) && installPercent < 94) {
            installPercent += 1;
          }
          this.emit({ status: this.installingStatus(line), message: line, percent: installPercent });
        },
      });
      if (pip.code !== 0) {
        throw new Error(`pip exited ${pip.code}: ${pip.stderr.trim().split("\n").at(-1) ?? ""}`);
      }

      // 5. check
      report("check", "Checking the installation…", 95);
      const probe = await this.probe({ python: managed.python, source: "managed", env: {} });
      if (probe.version !== this.host.appVersion) {
        throw new Error(`installed cadgen ${probe.version}, expected ${this.host.appVersion}`);
      }
      await fsp.writeFile(
        managed.marker,
        JSON.stringify({ cadgenVersion: probe.version, python: this.build.version, at: new Date().toISOString() }, null, 2),
      );
      await fsp.writeFile(managed.log, logLines.join("\n") + "\n");
      report("check", "Ready.", 100);
      const status = await this.probedStatus();
      this.emit({ status, message: "Ready.", percent: 100 });
      return status;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      log(`[error] ${message}`);
      await fsp.mkdir(managed.root, { recursive: true }).catch(() => {});
      await fsp.writeFile(managed.log, logLines.join("\n") + "\n").catch(() => {});
      // A half-provisioned runtime must never resolve as one: the marker is
      // what `resolve()` looks for, and it is only ever written last.
      await fsp.rm(managed.marker, { force: true }).catch(() => {});
      this.lastError = { message, log: logLines.slice(-40).join("\n") };
      const status = await this.probedStatus();
      this.emit({ status, message, percent: undefined });
      return status;
    }
  }

  /**
   * How cadgen is installed. The bundled wheel directory (`resources/cadgen`,
   * filled by the release workflow or `scripts/cad-resources.mjs`) is offered
   * with `--find-links`, so the exact-version requirement resolves to the
   * bundled file; its dependencies (OCP, build123d, the rest of the gigabyte)
   * still come from PyPI, pinned by the constraints file that was frozen
   * beside the wheel. Without a bundled wheel the same command, minus the
   * link, installs the release from PyPI.
   */
  pipArgs(): { args: string[]; description: string } {
    const wheelDir = path.join(this.host.resourcesDir, "cadgen");
    const wheels = fs.existsSync(wheelDir) ? fs.readdirSync(wheelDir).filter((name) => name.endsWith(".whl")) : [];
    const constraints = path.join(wheelDir, "constraints.txt");
    const args: string[] = [];
    if (wheels.length > 0) {
      args.push("--find-links", wheelDir);
    }
    args.push(`cadgen==${this.host.appVersion}`);
    if (fs.existsSync(constraints)) {
      args.push("-c", constraints);
    }
    return {
      args,
      description: `pip install ${args.join(" ")}${wheels.length ? ` (bundled: ${wheels.join(", ")})` : " (from PyPI)"}`,
    };
  }
}

async function sha256File(file: string): Promise<string> {
  const hash = createHash("sha256");
  await pipeline(fs.createReadStream(file), hash);
  return hash.digest("hex");
}
