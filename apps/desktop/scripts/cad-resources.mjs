/**
 * Fill `resources/cadgen/` from a checkout: the cadgen wheel for this
 * version and the constraints file the managed runtime installs it with
 * (plan §8).
 *
 *   node scripts/cad-resources.mjs [--python <interpreter>] [--out <dir>]
 *
 * 1. The wheel. Built the way `release-publish.yml` builds the one it
 *    publishes — `python -m build packages/cadgen` — and copied in. The
 *    wheel is what `pip install --find-links resources/cadgen cadgen==<v>`
 *    resolves the exact-version requirement to (src/main/cad/runtime.ts).
 *    In CI this step does not run: the `desktop` job downloads the wheel the
 *    `publish` job just built and uploaded into the same directory, so the
 *    app bundles the very file that went to PyPI.
 * 2. `constraints.txt`. `pip freeze` from the development interpreter (the
 *    checkout's `.venv` by default), filtered to cadgen's dependency closure —
 *    the packages `pip show` reaches from `cadgen`, transitively — so the
 *    managed runtime resolves the same OCP, build123d and ezdxf the checkout
 *    was tested against, and nothing the venv happens to hold beyond them
 *    (pytest, playwright, the editable cadgen itself) pins anything.
 *
 * Both are build outputs: gitignored, recreated on demand, and absent from a
 * checkout that never ran this — which the app handles (it installs from
 * PyPI with no constraints, and Settings says so).
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { appVersion } from "./app-version.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..", "..");

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--python" || arg === "--out") {
      options[arg.slice(2)] = argv[index + 1];
      index += 1;
    } else if (arg === "--no-wheel") {
      options.noWheel = true;
    } else {
      throw new Error(`unknown argument ${arg}`);
    }
  }
  return options;
}

function run(file, args, options = {}) {
  return execFileSync(file, args, { encoding: "utf8", stdio: ["ignore", "pipe", "inherit"], ...options });
}

/** Distribution names `pip show` reaches from `root`, transitively — the closure. */
export function dependencyClosure(python, root, env) {
  const seen = new Set();
  const queue = [root];
  while (queue.length > 0) {
    const name = queue.shift();
    const key = name.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    let info;
    try {
      info = run(python, ["-m", "pip", "show", name], { env });
    } catch {
      continue; // an extra that is not installed, or a name pip does not know
    }
    seen.add(key);
    const requires = info
      .split("\n")
      .find((line) => line.startsWith("Requires:"))
      ?.slice("Requires:".length)
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean) ?? [];
    queue.push(...requires);
  }
  seen.delete(root.toLowerCase());
  return seen;
}

/** `pip freeze` lines for the closure — `name==version` only, editable installs dropped. */
export function constraintsFrom(freeze, closure) {
  return freeze
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => /^[A-Za-z0-9_.-]+==/.test(line))
    .filter((line) => closure.has(line.split("==")[0].toLowerCase().replace(/_/g, "-")))
    .sort((a, b) => a.localeCompare(b));
}

export function writeCadResources({ python, out, version, noWheel = false }) {
  fs.mkdirSync(out, { recursive: true });
  const env = { ...process.env, PYTHONPATH: path.join(repoRoot, "packages", "cadgen", "src") };

  if (!noWheel) {
    const dist = path.join(repoRoot, "packages", "cadgen", "dist");
    fs.rmSync(dist, { recursive: true, force: true });
    run(python, ["-m", "build", "--wheel", "--outdir", dist, path.join(repoRoot, "packages", "cadgen")], { env, stdio: "inherit" });
    const wheel = fs.readdirSync(dist).find((name) => name.endsWith(".whl"));
    if (!wheel) {
      throw new Error(`python -m build produced no wheel under ${dist}`);
    }
    if (!wheel.startsWith(`cadgen-${version}-`)) {
      throw new Error(`built ${wheel}, but the app version is ${version}; VERSION and packages/cadgen/pyproject.toml disagree`);
    }
    for (const stale of fs.readdirSync(out).filter((name) => name.endsWith(".whl"))) {
      fs.rmSync(path.join(out, stale));
    }
    fs.copyFileSync(path.join(dist, wheel), path.join(out, wheel));
    console.info(`wheel: ${wheel}`);
  }

  // The closure is computed with `pip show`, which normalises names the way
  // freeze prints them (dashes), so the two agree on membership.
  const closure = new Set([...dependencyClosure(python, "cadgen", env)].map((name) => name.replace(/_/g, "-")));
  const constraints = constraintsFrom(run(python, ["-m", "pip", "freeze"], { env }), closure);
  if (constraints.length === 0) {
    throw new Error("pip freeze found none of cadgen's dependencies; is cadgen installed in that interpreter?");
  }
  const header = `# cadgen ${version}'s dependency closure, frozen from ${python}\n# by scripts/cad-resources.mjs. Read by the managed runtime's pip install (-c).\n`;
  fs.writeFileSync(path.join(out, "constraints.txt"), `${header}${constraints.join("\n")}\n`);
  console.info(`constraints.txt: ${constraints.length} pins`);
  return { out, constraints };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const options = parseArgs(process.argv.slice(2));
  const python =
    options.python ??
    process.env.CAD_DESKTOP_PYTHON ??
    path.join(repoRoot, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  writeCadResources({
    python,
    out: options.out ? path.resolve(options.out) : path.join(appRoot, "resources", "cadgen"),
    version: appVersion(),
    noWheel: Boolean(options.noWheel),
  });
}
