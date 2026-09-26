/**
 * Fill `resources/cadgen/` from a checkout: the cadgen wheel for this
 * version and the constraints file the managed runtime installs it with
 * (plan §8).
 *
 *   node scripts/cad-resources.mjs [--python <interpreter>] [--out <dir>]
 *
 * 1. The wheel. Built from the runtime produced by `scripts/bundle/bundle.sh`,
 *    the same prerequisite and build command as `release-publish.yml`, then copied in. The
 *    runtime bundling passes this exact wheel path to pip, so an index or pip
 *    cache can supply dependencies but cannot substitute another cadgen build.
 *    In CI this step does not run: the `desktop` job downloads the wheel the
 *    `publish` job just built and uploaded into the same directory, so the
 *    app bundles the very file that went to PyPI.
 * 2. `constraints.txt`. `pip freeze` from the development interpreter (the
 *    checkout's `.venv` by default), filtered to cadgen's dependency closure —
 *    the packages its metadata reaches, transitively, the runtime's extras
 *    (`RUNTIME_EXTRAS` in bundle-runtime.mjs) included — so the
 *    managed runtime resolves the same OCP, build123d and ezdxf the checkout
 *    was tested against, and nothing the venv happens to hold beyond them
 *    (pytest, playwright, the editable cadgen itself) pins anything.
 *
 * Both are build outputs: gitignored, recreated on demand, and required before
 * a packaged CAD runtime can be built.
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { appVersion } from "./app-version.mjs";
import { RUNTIME_EXTRAS } from "./bundle-runtime.mjs";

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

const REQUIRED_CADGEN_RUNTIME = [
  "node/mesh-export.mjs",
  "browser/render.html",
  "browser/snapshot-render.js",
  "viewer/index.html",
];

function requireBundledCadgenRuntime() {
  const runtime = path.join(repoRoot, "packages", "cadgen", "src", "cadgen", "_runtime");
  const missing = REQUIRED_CADGEN_RUNTIME.filter((name) => !fs.existsSync(path.join(runtime, name)));
  if (missing.length > 0) {
    throw new Error(
      `cadgen's package runtime is not bundled (${missing.join(", ")}); ` +
        "run `scripts/bundle/bundle.sh --clean` before `npm run cad:resources`",
    );
  }
}

/**
 * Distribution names reachable from `root`, transitively — the closure — with
 * the named extras of the root followed (and any extras a requirement names,
 * `a[b]`). `pip show` cannot do this: its `Requires:` line leaves every
 * extra's requirement out, so netgen and the rest of `cadgen[fea]` would go
 * unpinned and the runtime would resolve them from PyPI at build time.
 * Environment markers other than `extra` are not evaluated: a requirement for
 * another platform is a name `pip freeze` does not list here, so it pins
 * nothing, which is the same outcome as before.
 */
export function dependencyClosure(python, root, env, extras = []) {
  const script = `
import importlib.metadata as md, json, re, sys
root, extras = sys.argv[1], [e for e in sys.argv[2].split(",") if e]
REQ = re.compile(r"^\\s*([A-Za-z0-9][A-Za-z0-9._-]*)\\s*(?:\\[([^\\]]*)\\])?[^;]*(?:;(.*))?$")
EXTRA = re.compile(r"""extra\\s*==\\s*['"]([^'"]+)['"]""")
def norm(name): return name.lower().replace("_", "-").replace(".", "-")
seen, queue = {}, [(root, set(extras))]
while queue:
    name, wanted = queue.pop(0)
    key = norm(name)
    if key in seen and wanted <= seen[key]: continue
    try: dist = md.distribution(name)
    except md.PackageNotFoundError: continue
    seen[key] = seen.get(key, set()) | wanted
    for line in dist.requires or []:
        match = REQ.match(line)
        if not match: continue
        dep, dep_extras, marker = match.group(1), match.group(2) or "", match.group(3) or ""
        extra = EXTRA.search(marker)
        if extra and extra.group(1) not in wanted: continue
        queue.append((dep, {e.strip() for e in dep_extras.split(",") if e.strip()}))
print(json.dumps(sorted(k for k in seen if k != norm(root))))
`;
  const out = run(python, ["-c", script, root, extras.join(",")], { env });
  return new Set(JSON.parse(out));
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
    requireBundledCadgenRuntime();
    const dist = path.join(repoRoot, "packages", "cadgen", "dist");
    // setuptools' build/lib is incremental. Old hashed Viewer chunks otherwise survive
    // a fresh source bundle and are copied into the next wheel alongside current chunks.
    fs.rmSync(path.join(repoRoot, "packages", "cadgen", "build"), { recursive: true, force: true });
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

  // The closure's names are normalised the way freeze prints them (lower case,
  // dashes), so the two agree on membership.
  const closure = dependencyClosure(python, "cadgen", env, RUNTIME_EXTRAS);
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
