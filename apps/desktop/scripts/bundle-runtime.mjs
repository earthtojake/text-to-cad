/**
 * Build the CAD runtime the app ships (plan §8, as revised): a pinned
 * python-build-standalone interpreter with cadgen and its whole dependency
 * closure installed into it, laid out under `resources/runtime/<target>/`
 * for electron-builder to copy beside the app as an extraResource.
 *
 *   node scripts/bundle-runtime.mjs [--target mac-arm64|mac-x64|win-x64|linux-x64]...
 *                                   [--wheels <dir>] [--out <dir>] [--cache <dir>]
 *                                   [--python <host interpreter>]
 *
 * Nothing is downloaded at first launch and nothing is "installing": the
 * runtime is complete when the installer is. Per target, in order:
 *
 *   1. the pinned interpreter (`scripts/python-build.json`) is fetched into
 *      the cache — `~/.cache/text-to-cad/python` or `--cache`, which CI keys on
 *      the pin file — checked against the pinned sha256 and unpacked;
 *   2. `pip install --target <site-packages> <cadgen-wheel>` puts that exact
 *      release wheel and every pin of `resources/cadgen/constraints.txt` into
 *      it; PyPI supplies only the wheel's dependencies. The command uses
 *      `--only-binary=:all:` and the
 *      target's platform tags — so this works for a FOREIGN target too: pip
 *      never runs the target's interpreter, it only picks wheels for it;
 *   3. what a runtime never needs is pruned (the stdlib's test suite, every
 *      package's `tests`, static libraries, the console scripts pip wrote
 *      with a build-machine shebang), and then every module is compiled to
 *      `__pycache__` with `unchecked-hash` pycs, because the bundle is
 *      read-only once installed — a signed .app must not be written into —
 *      and the app runs the interpreter with PYTHONDONTWRITEBYTECODE;
 *   4. a runtime this machine can execute is probed (`import cadgen`,
 *      `import cadgen.viewer`, the version equals the app's); one it cannot
 *      is checked on disk; and `runtime.json` is written LAST, because it is
 *      what `src/main/cad/runtime.ts` looks for — a half-built directory is
 *      not a runtime.
 *
 * The native target uses the runtime's own pip and python for 2–4. A foreign
 * target uses a host interpreter for pip (any Python 3 with pip) and for the
 * bytecode (which has to be a 3.13, the pin's minor: pyc magic is per minor
 * version) — `--python`, else the first 3.13 on PATH, else the checkout's
 * `.venv`; without a 3.13 host the foreign bundle ships without pycs, and
 * says so, which costs a compile at first import and nothing else.
 *
 * Every artifact is a build output: `resources/runtime/` is gitignored.
 */
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";

import { appVersion } from "./app-version.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..", "..");

export const PYTHON_BUILD = JSON.parse(fs.readFileSync(path.join(appRoot, "scripts", "python-build.json"), "utf8"));
export const TARGETS = Object.keys(PYTHON_BUILD.targets);

const OS_NAMES = { darwin: "mac", win32: "win", linux: "linux" };

/** electron-builder's `${os}-${arch}` for this machine, or null off the table. */
export function hostTarget(platform = process.platform, arch = process.arch) {
  const target = `${OS_NAMES[platform] ?? platform}-${arch}`;
  return TARGETS.includes(target) ? target : null;
}

export function pythonBuildUrl(target, build = PYTHON_BUILD) {
  return `https://github.com/astral-sh/python-build-standalone/releases/download/${build.release}/${build.targets[target].file}`;
}

/** The layout under one target's directory. The tarball's top level is `python/`. */
export function runtimeLayout(root, target, pythonVersion = PYTHON_BUILD.version) {
  const [major, minor] = pythonVersion.split(".");
  const windows = target.startsWith("win-");
  const pythonDir = path.join(root, "python");
  return {
    root,
    pythonDir,
    python: windows ? path.join(pythonDir, "python.exe") : path.join(pythonDir, "bin", "python3"),
    stdlib: windows ? path.join(pythonDir, "Lib") : path.join(pythonDir, "lib", `python${major}.${minor}`),
    sitePackages: windows
      ? path.join(pythonDir, "Lib", "site-packages")
      : path.join(pythonDir, "lib", `python${major}.${minor}`, "site-packages"),
    marker: path.join(root, "runtime.json"),
  };
}

function parseArgs(argv) {
  const options = { targets: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = () => {
      index += 1;
      if (argv[index] === undefined) {
        throw new Error(`${arg} needs a value`);
      }
      return argv[index];
    };
    if (arg === "--target") {
      const target = value();
      if (!TARGETS.includes(target)) {
        throw new Error(`unknown target ${target}; one of ${TARGETS.join(", ")}`);
      }
      options.targets.push(target);
    } else if (arg === "--out" || arg === "--cache" || arg === "--wheels" || arg === "--python") {
      options[arg.slice(2)] = value();
    } else {
      throw new Error(`unknown argument ${arg}`);
    }
  }
  return options;
}

function run(file, args, { env, cwd, quiet = false } = {}) {
  const result = spawnSync(file, args, {
    cwd,
    env: { ...process.env, ...env },
    stdio: quiet ? ["ignore", "pipe", "pipe"] : "inherit",
    encoding: "utf8",
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    const tail = quiet ? `\n${(result.stderr || result.stdout || "").trim().split("\n").slice(-15).join("\n")}` : "";
    throw new Error(`${path.basename(file)} ${args.slice(0, 3).join(" ")}… exited ${result.status}${tail}`);
  }
  return result.stdout ?? "";
}

async function sha256File(file) {
  const hash = createHash("sha256");
  await pipeline(fs.createReadStream(file), hash);
  return hash.digest("hex");
}

/** Fetch `url` into `dest` unless a file with the pinned hash is already there. */
async function fetchPinned(url, dest, sha256) {
  if (fs.existsSync(dest) && (await sha256File(dest)) === sha256) {
    console.info(`cached: ${path.basename(dest)}`);
    return;
  }
  console.info(`downloading ${url}`);
  const response = await fetch(url, { redirect: "follow" });
  if (!response.ok || !response.body) {
    throw new Error(`download failed: HTTP ${response.status} for ${url}`);
  }
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const partial = `${dest}.part`;
  await pipeline(response.body, fs.createWriteStream(partial));
  const digest = await sha256File(partial);
  if (digest !== sha256) {
    fs.rmSync(partial, { force: true });
    throw new Error(`checksum mismatch for ${path.basename(dest)}: expected ${sha256}, got ${digest}`);
  }
  fs.renameSync(partial, dest);
}

/** Can this machine execute the interpreter at `python`? (Rosetta makes mac-x64 runnable on arm64.) */
function runnable(python) {
  if (!fs.existsSync(python)) {
    return false;
  }
  const result = spawnSync(python, ["-c", "import sys; print(sys.version_info[:2])"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
  return result.status === 0;
}

function versionOf(python) {
  const result = spawnSync(python, ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
  return result.status === 0 ? result.stdout.trim() : null;
}

function hasPip(python) {
  return spawnSync(python, ["-m", "pip", "--version"], { stdio: "ignore" }).status === 0;
}

/**
 * A host interpreter for a foreign target: `--python`, else the pin's minor on
 * PATH, else the checkout's venv, else any python3 with pip. The minor
 * matters for bytecode only; pip does not care.
 */
function hostPython(explicit, minor) {
  const candidates = [
    explicit,
    `python${minor}`,
    path.join(os.homedir(), ".local", "bin", `python${minor}`),
    path.join(repoRoot, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python"),
    "python3",
    "python",
  ].filter(Boolean);
  for (const candidate of candidates) {
    const found = path.isAbsolute(candidate) ? candidate : which(candidate);
    if (found && hasPip(found)) {
      return found;
    }
  }
  throw new Error(`no host Python with pip found for a foreign target; pass --python <interpreter> (${minor} preferred)`);
}

function which(name) {
  const result = spawnSync(process.platform === "win32" ? "where" : "which", [name], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
  const first = result.status === 0 ? result.stdout.trim().split(/\r?\n/)[0] : "";
  return first || null;
}

/**
 * Launchers in the interpreter's own `bin/` (posix) or `Scripts/` (Windows)
 * that an app runtime never runs and an agent must not: pip (which would
 * write into the signed, read-only bundle), IDLE, `python3-config` (build
 * flags for this build machine's paths) and wheel. `python`, `python3` and
 * `python3.X` stay. `python -m pip` stays too — the build uses it — and the
 * EXTERNALLY-MANAGED marker decides what it may do afterwards.
 */
const LAUNCHERS_TO_PRUNE = /^(pip|idle|wheel)[\d.]*(\.exe)?$|-config$/i;

/** Directories and files a runtime never reads, removed after the install. */
export function prune(layout) {
  const removed = [];
  const rm = (target) => {
    if (fs.existsSync(target)) {
      fs.rmSync(target, { recursive: true, force: true });
      removed.push(path.relative(layout.root, target));
    }
  };
  // The stdlib's own test suite (tens of megabytes of tests for the interpreter).
  rm(path.join(layout.stdlib, "test"));
  // Console scripts pip wrote for --target, with the build machine's shebang.
  rm(path.join(layout.sitePackages, "bin"));
  rm(path.join(layout.sitePackages, "Scripts"));
  // pip, idle, *-config and wheel launchers (LAUNCHERS_TO_PRUNE).
  for (const dir of [path.dirname(layout.python), path.join(layout.pythonDir, "bin"), path.join(layout.pythonDir, "Scripts")]) {
    if (!fs.existsSync(dir)) {
      continue;
    }
    for (const name of fs.readdirSync(dir)) {
      if (LAUNCHERS_TO_PRUNE.test(name)) {
        rm(path.join(dir, name));
      }
    }
  }
  // Documentation and static libraries.
  rm(path.join(layout.pythonDir, "share"));
  // Every package's tests, and every bytecode cache (recompiled below).
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory() || entry.isSymbolicLink()) {
        if (entry.isFile() && entry.name.endsWith(".a") && dir.startsWith(path.join(layout.pythonDir, "lib"))) {
          fs.rmSync(path.join(dir, entry.name));
          removed.push(path.relative(layout.root, path.join(dir, entry.name)));
        }
        continue;
      }
      const full = path.join(dir, entry.name);
      if (entry.name === "__pycache__" || entry.name === "tests") {
        fs.rmSync(full, { recursive: true, force: true });
        removed.push(path.relative(layout.root, full));
        continue;
      }
      walk(full);
    }
  };
  walk(layout.pythonDir);
  return removed;
}

/**
 * PEP 668's marker, in the stdlib directory (`sysconfig.get_path("stdlib")`):
 * pip then refuses to install into this interpreter — its own site-packages,
 * `--user` — with this message. The bundle is inside a signed, read-only app,
 * and its packages are the pinned closure cadgen was validated with; an
 * agent's `pip install -U numpy` must fail with an explanation, not break the
 * signature or the pins, nor die with EACCES. `pip install --target <dir>`
 * and a venv still work.
 */
export const EXTERNALLY_MANAGED = [
  "[externally-managed]",
  "Error=This Python is the CAD runtime bundled inside the text-to-cad app. Its",
  " packages are the pinned set cadgen was validated with, and the app bundle is",
  " signed and read-only, so nothing can be installed into it.",
  "",
  " To use other packages, create a virtual environment that can still import",
  " the bundled CAD packages:",
  "",
  "     python3 -m venv --system-site-packages .venv",
  "     .venv/bin/python -m pip install <package>",
  "",
  " (On Windows: .venv\\Scripts\\python -m pip install <package>.) The runtime",
  " updates with the app; see the text-to-cad README, \"CAD runtime\".",
  "",
].join("\n");

export function markExternallyManaged(layout) {
  fs.writeFileSync(path.join(layout.stdlib, "EXTERNALLY-MANAGED"), EXTERNALLY_MANAGED);
}

/** `python -I -c`: what `src/main/cad/runtime.ts` asks an interpreter, so the bundle is checked the way it is used. */
const PROBE = [
  "import json, cadgen, cadgen.viewer",
  "print(json.dumps({'version': cadgen.__version__}))",
].join("; ");

export const CADGEN_RUNTIME_FILES = [
  "_runtime/node/mesh-export.mjs",
  "_runtime/browser/render.html",
  "_runtime/browser/snapshot-render.js",
  "_runtime/viewer/index.html",
];

function missingCadgenRuntimeFiles(layout) {
  const cadgen = path.join(layout.sitePackages, "cadgen");
  return CADGEN_RUNTIME_FILES.filter((name) => !fs.existsSync(path.join(cadgen, name)));
}

function directorySize(dir) {
  let total = 0;
  const walk = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isSymbolicLink()) {
        continue;
      }
      if (entry.isDirectory()) {
        walk(full);
      } else {
        total += fs.statSync(full).size;
      }
    }
  };
  walk(dir);
  return total;
}

/**
 * The `tar` that unpacks the interpreter. On Windows it is the system's own
 * bsdtar, by full path: the release workflow runs this from Git Bash, whose
 * PATH puts GNU tar first, and GNU tar reads the `C:` of `C:\…\python.tar.gz`
 * as a remote host ("Cannot connect to C: resolve failed").
 */
export function tarCommand(platform = process.platform, env = process.env) {
  return platform === "win32" ? path.win32.join(env.SystemRoot ?? env.windir ?? "C:\\Windows", "System32", "tar.exe") : "tar";
}

/** Pip arguments that install the selected release wheel and its pinned closure. */
export function runtimePipInstallArgs({ layout, asset, pyMinor, wheel, constraints }) {
  const [major, minor] = pyMinor.split(".");
  return [
    "-m", "pip", "install",
    "--no-compile",
    "--no-warn-script-location",
    "--only-binary=:all:",
    "--python-version", pyMinor,
    "--implementation", "cp",
    "--abi", `cp${major}${minor}`,
    ...asset.pip.platforms.flatMap((platform) => ["--platform", platform]),
    "--target", layout.sitePackages,
    "-c", constraints,
    wheel,
  ];
}

export async function bundleRuntime({ target, out, cache, wheels, version, python: explicitPython, build = PYTHON_BUILD }) {
  const asset = build.targets[target];
  if (!asset) {
    throw new Error(`no pinned interpreter for ${target}`);
  }
  const wheel = releaseWheel(wheels, version)?.name;
  const constraints = path.join(wheels, "constraints.txt");
  if (!wheel) {
    throw new Error(`no cadgen-${version} wheel under ${wheels}; run \`npm run cad:resources\` (the release workflow downloads the published wheel there)`);
  }
  if (!fs.existsSync(constraints)) {
    throw new Error(`no constraints.txt under ${wheels}; run \`npm run cad:resources\``);
  }

  const root = path.join(out, target);
  const layout = runtimeLayout(root, target, build.version);
  const [major, minor] = build.version.split(".");
  const pyMinor = `${major}.${minor}`;
  const wheelPath = path.resolve(wheels, wheel);
  console.info(`\n== ${target}: Python ${build.version}, cadgen ${version} (${wheel}) -> ${path.relative(appRoot, root)}`);

  // 1. the interpreter
  const archive = path.join(cache, asset.file);
  await fetchPinned(pythonBuildUrl(target, build), archive, asset.sha256);
  fs.rmSync(root, { recursive: true, force: true });
  fs.mkdirSync(root, { recursive: true });
  run(tarCommand(), ["-xzf", archive, "-C", root]);
  if (!fs.existsSync(layout.python)) {
    throw new Error(`the archive did not produce ${layout.python}`);
  }

  // 2. cadgen and its closure, as wheels for the target
  const native = runnable(layout.python);
  const pipPython = native ? layout.python : hostPython(explicitPython, pyMinor);
  console.info(native ? "native target: the runtime's own pip" : `foreign target: pip from ${pipPython}`);
  const pipEnv = {
    PIP_DISABLE_PIP_VERSION_CHECK: "1",
    PIP_CACHE_DIR: path.join(cache, "pip"),
    PIP_REQUIRE_VIRTUALENV: "",
    PYTHONDONTWRITEBYTECODE: "1",
  };
  run(pipPython, runtimePipInstallArgs({ layout, asset, pyMinor, wheel: wheelPath, constraints }), { env: pipEnv });

  // 3. prune, then bytecode
  const removed = prune(layout);
  markExternallyManaged(layout);
  console.info(`pruned ${removed.length} paths (${removed.filter((entry) => !entry.endsWith("__pycache__")).slice(0, 6).join(", ")}${removed.length > 6 ? ", …" : ""})`);
  const compiler = native ? layout.python : hostPython(explicitPython, pyMinor);
  if (versionOf(compiler) === pyMinor) {
    run(compiler, ["-m", "compileall", "-q", "-j", "0", "--invalidation-mode", "unchecked-hash", layout.pythonDir], { quiet: true });
    console.info("compiled bytecode (unchecked-hash)");
  } else {
    console.warn(`no Python ${pyMinor} host to compile bytecode with (have ${versionOf(compiler) ?? "none"}); the bundle ships without pycs`);
  }

  // 4. check, then the marker
  const missingRuntime = missingCadgenRuntimeFiles(layout);
  if (missingRuntime.length > 0) {
    throw new Error(`the bundled cadgen wheel is missing package runtime assets: ${missingRuntime.join(", ")}`);
  }
  if (native) {
    const probe = run(layout.python, ["-I", "-c", PROBE], {
      quiet: true,
      env: { PYTHONDONTWRITEBYTECODE: "1" },
    }).trim().split("\n").at(-1);
    const parsed = JSON.parse(probe);
    if (parsed.version !== version) {
      throw new Error(`the bundled cadgen reports ${parsed.version}, expected ${version}`);
    }
    console.info(`probe: cadgen ${parsed.version} imports, viewer imports`);
  } else {
    const distInfo = path.join(layout.sitePackages, `cadgen-${version}.dist-info`);
    for (const required of [distInfo, path.join(layout.sitePackages, "cadgen", "__init__.py"), path.join(layout.sitePackages, "cadgen", "viewer")]) {
      if (!fs.existsSync(required)) {
        throw new Error(`the foreign bundle is missing ${path.relative(root, required)}`);
      }
    }
    console.info("checked on disk (a foreign target cannot be executed here)");
  }
  const marker = {
    target,
    python: build.version,
    release: build.release,
    cadgen: version,
    wheel,
    wheelSha256: releaseWheel(wheels, version).sha256,
    native,
    host: `${process.platform}-${process.arch}`,
    builtAt: new Date().toISOString(),
  };
  fs.writeFileSync(layout.marker, `${JSON.stringify(marker, null, 2)}\n`);
  const bytes = directorySize(root);
  console.info(`${target}: ${(bytes / 1024 / 1024).toFixed(0)} MB on disk`);
  return { ...marker, root, bytes };
}

/** The `cadgen-<version>-*.whl` under `wheels` and its sha256, or null when there is none. */
export function releaseWheel(wheels, version) {
  const name = fs.existsSync(wheels)
    ? fs.readdirSync(wheels).find((entry) => entry.startsWith(`cadgen-${version}-`) && entry.endsWith(".whl"))
    : undefined;
  if (!name) {
    return null;
  }
  return { name, sha256: createHash("sha256").update(fs.readFileSync(path.join(wheels, name))).digest("hex") };
}

/**
 * The marker a complete bundle for this cadgen, this interpreter pin and the
 * wheel now in `wheels` carries, or null. `scripts/package.mjs` refuses to
 * package without one.
 */
export function bundledRuntime(out, target, version, wheels, build = PYTHON_BUILD) {
  const layout = runtimeLayout(path.join(out, target), target, build.version);
  if (!fs.existsSync(layout.marker) || !fs.existsSync(layout.python) || missingCadgenRuntimeFiles(layout).length > 0) {
    return null;
  }
  try {
    const marker = JSON.parse(fs.readFileSync(layout.marker, "utf8"));
    // A bundle built from an older interpreter pin (python-build.json moved
    // on) is stale however current its cadgen is. So is one installed from a
    // different wheel of the same version — a rebuilt `cadgen-<v>` from
    // `npm run cad:resources` after a source change — which only the hash
    // tells apart: the file name is the same.
    const wheel = releaseWheel(wheels, version);
    return marker.cadgen === version &&
      marker.target === target &&
      marker.python === build.version &&
      marker.release === build.release &&
      wheel !== null &&
      marker.wheel === wheel.name &&
      marker.wheelSha256 === wheel.sha256
      ? marker
      : null;
  } catch {
    return null;
  }
}

export function defaultCacheDir() {
  return process.env.TEXT_TO_CAD_RUNTIME_CACHE || path.join(os.homedir(), ".cache", "text-to-cad", "python");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const options = parseArgs(process.argv.slice(2));
  const version = appVersion();
  const targets = options.targets.length > 0 ? options.targets : [hostTarget()].filter(Boolean);
  if (targets.length === 0) {
    throw new Error(`no --target given and this machine (${process.platform}-${process.arch}) is not a packaged target`);
  }
  const out = path.resolve(options.out ?? path.join(appRoot, "resources", "runtime"));
  const cache = path.resolve(options.cache ?? defaultCacheDir());
  const wheels = path.resolve(options.wheels ?? path.join(appRoot, "resources", "cadgen"));
  // `tar` is the extractor on every host (macOS and Linux always; Windows 10
  // 1803+ ships bsdtar as System32\tar.exe — `tarCommand`).
  execFileSync(tarCommand(), ["--version"], { stdio: "ignore" });
  for (const target of targets) {
    await bundleRuntime({ target, out, cache, wheels, version, python: options.python });
  }
}
