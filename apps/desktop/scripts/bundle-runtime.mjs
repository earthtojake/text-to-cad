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
 *      the cache — `~/.cache/hardcore/python` or `--cache`, which CI keys on
 *      the pin file — checked against the pinned sha256 and unpacked;
 *   2. `pip install --target <site-packages>` puts cadgen and every pin of
 *      `resources/cadgen/constraints.txt` into it, from the wheel in
 *      `resources/cadgen` (`npm run cad:resources`, or the wheel the release
 *      workflow just built) and PyPI, with `--only-binary=:all:` and the
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

/** Directories a runtime never reads, removed after the install. */
function prune(layout) {
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

/** `python -I -c`: what `src/main/cad/runtime.ts` asks an interpreter, so the bundle is checked the way it is used. */
const PROBE = [
  "import json, cadgen, cadgen.viewer",
  "print(json.dumps({'version': cadgen.__version__}))",
].join("; ");

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

export async function bundleRuntime({ target, out, cache, wheels, version, python: explicitPython, build = PYTHON_BUILD }) {
  const asset = build.targets[target];
  if (!asset) {
    throw new Error(`no pinned interpreter for ${target}`);
  }
  const wheel = fs.existsSync(wheels) ? fs.readdirSync(wheels).find((name) => name.startsWith(`cadgen-${version}-`) && name.endsWith(".whl")) : null;
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
  console.info(`\n== ${target}: Python ${build.version}, cadgen ${version} (${wheel}) -> ${path.relative(appRoot, root)}`);

  // 1. the interpreter
  const archive = path.join(cache, asset.file);
  await fetchPinned(pythonBuildUrl(target, build), archive, asset.sha256);
  fs.rmSync(root, { recursive: true, force: true });
  fs.mkdirSync(root, { recursive: true });
  run("tar", ["-xzf", archive, "-C", root]);
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
  run(pipPython, [
    "-m", "pip", "install",
    "--no-compile",
    "--no-warn-script-location",
    "--only-binary=:all:",
    "--python-version", pyMinor,
    "--implementation", "cp",
    "--abi", `cp${major}${minor}`,
    ...asset.pip.platforms.flatMap((platform) => ["--platform", platform]),
    "--target", layout.sitePackages,
    "--find-links", wheels,
    "-c", constraints,
    `cadgen==${version}`,
  ], { env: pipEnv });

  // 3. prune, then bytecode
  const removed = prune(layout);
  console.info(`pruned ${removed.length} paths (${removed.filter((entry) => !entry.endsWith("__pycache__")).slice(0, 6).join(", ")}${removed.length > 6 ? ", …" : ""})`);
  const compiler = native ? layout.python : hostPython(explicitPython, pyMinor);
  if (versionOf(compiler) === pyMinor) {
    run(compiler, ["-m", "compileall", "-q", "-j", "0", "--invalidation-mode", "unchecked-hash", layout.pythonDir], { quiet: true });
    console.info("compiled bytecode (unchecked-hash)");
  } else {
    console.warn(`no Python ${pyMinor} host to compile bytecode with (have ${versionOf(compiler) ?? "none"}); the bundle ships without pycs`);
  }

  // 4. check, then the marker
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
    native,
    host: `${process.platform}-${process.arch}`,
    builtAt: new Date().toISOString(),
  };
  fs.writeFileSync(layout.marker, `${JSON.stringify(marker, null, 2)}\n`);
  const bytes = directorySize(root);
  console.info(`${target}: ${(bytes / 1024 / 1024).toFixed(0)} MB on disk`);
  return { ...marker, root, bytes };
}

/** The marker a complete bundle carries, or null. `scripts/package.mjs` refuses to package without one. */
export function bundledRuntime(out, target, version) {
  const layout = runtimeLayout(path.join(out, target), target);
  if (!fs.existsSync(layout.marker) || !fs.existsSync(layout.python)) {
    return null;
  }
  try {
    const marker = JSON.parse(fs.readFileSync(layout.marker, "utf8"));
    return marker.cadgen === version && marker.target === target ? marker : null;
  } catch {
    return null;
  }
}

export function defaultCacheDir() {
  return process.env.HARDCORE_RUNTIME_CACHE || path.join(os.homedir(), ".cache", "hardcore", "python");
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
  // 1803+ ships bsdtar as tar.exe).
  execFileSync("tar", ["--version"], { stdio: "ignore" });
  for (const target of targets) {
    await bundleRuntime({ target, out, cache, wheels, version, python: options.python });
  }
}
