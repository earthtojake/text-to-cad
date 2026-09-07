/**
 * `npm run package:mac | package:win | package:linux`, and the one entry point
 * the release workflow uses too. Any extra arguments are passed straight to
 * electron-builder, so CI's `--mac --arm64 --x64` needs nothing special here.
 *
 * Three things this does that a bare `electron-builder` invocation would not:
 *
 * 1. Builds first (`scripts/build.mjs`: the composed plugin, `electron-vite
 *    build`, the bundled MCP server), because electron-builder ships `out/`
 *    and has no opinion about how it got there.
 * 2. Stamps the repository's VERSION as `extraMetadata.version`. package.json
 *    stays at 0.0.0 (see scripts/app-version.mjs): the release version has
 *    exactly one home, and this is how it reaches the installer name,
 *    `app.getVersion()` and the updater feed without anything being
 *    hand-edited.
 * 3. Decides whether the build is signed FROM THE ENVIRONMENT ALONE. There is
 *    no `--sign` flag and no signed/unsigned config pair to keep in step:
 *    the secrets are present or they are not, and the same command produces an
 *    unsigned build on a laptop and a signed, notarised one in CI the day the
 *    secrets are added. See `signingEnv` below.
 *
 * A Node script rather than shell in package.json because
 * `--config.extraMetadata.version=$(cat ../../VERSION)` does not work on
 * Windows, and Windows is one of the three targets.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { appVersion } from "./app-version.mjs";
import { bundledRuntime } from "./bundle-runtime.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const argv = process.argv.slice(2);
// `--no-runtime` is this script's, not electron-builder's: package without
// the CAD runtime, for a build whose purpose is not CAD (a layout check, a
// signing rehearsal). A release never passes it.
const withoutRuntime = argv.includes("--no-runtime");
const targets = argv.filter((arg) => arg !== "--no-runtime");

if (targets.length === 0) {
  console.error("usage: node scripts/package.mjs --mac | --win | --linux [--no-runtime] [electron-builder args]");
  process.exit(2);
}

/**
 * What `extraResources` copies. Recreated rather than assumed so the config
 * never depends on electron-builder's tolerance of a source directory that is
 * not there. `resources/runtime/<target>` is checked, not created: an empty
 * one would package an app that cannot render CAD.
 */
const EXTRA_RESOURCE_DIRS = ["resources/cadgen", "resources/plugin", "resources/runtime"];

/**
 * The `<os>-<arch>` runtimes this invocation needs: one per app electron-builder
 * will produce, which is the arch flags on the command line or, without any,
 * the arch list in electron-builder.yml for that os.
 */
const DEFAULT_ARCHES = { "--mac": ["arm64", "x64"], "--win": ["x64"], "--linux": ["x64"] };
const OS_NAMES = { "--mac": "mac", "--win": "win", "--linux": "linux" };
// The target names electron-builder.yml lists per os. An arch flag on the
// command line only narrows the build when target NAMES are on it too
// (app-builder-lib's computeArchToTargetNamesMap: with no names, every arch
// the config lists is built regardless of --arm64), so `--mac --arm64` is
// passed on as `--mac dmg zip --arm64`. Measured, not assumed: `--arm64`
// alone packaged an x64 app as well — one with no runtime in it.
const TARGET_NAMES = { "--mac": ["dmg", "zip"], "--win": ["nsis"], "--linux": ["AppImage", "deb"] };
const ARCH_FLAGS = ["arm64", "x64", "ia32", "armv7l", "universal"];

export function runtimeTargetsFor(args) {
  const arches = ARCH_FLAGS.filter((arch) => args.includes(`--${arch}`));
  return Object.keys(OS_NAMES)
    .filter((flag) => args.includes(flag))
    .flatMap((flag) => (arches.length > 0 ? arches : DEFAULT_ARCHES[flag]).map((arch) => `${OS_NAMES[flag]}-${arch}`));
}

/** The electron-builder arguments: the os flags followed by their target names when an arch flag narrows the build. */
export function builderArgsFor(args) {
  if (!ARCH_FLAGS.some((arch) => args.includes(`--${arch}`))) {
    return args;
  }
  return args.flatMap((arg) => (arg in TARGET_NAMES && !args.some((other) => TARGET_NAMES[arg].includes(other)) ? [arg, ...TARGET_NAMES[arg]] : [arg]));
}

/**
 * Code-signing is on when, and only when, the credentials exist.
 *
 * `CSC_LINK` (+ `CSC_KEY_PASSWORD`) is the certificate; without it
 * `CSC_IDENTITY_AUTO_DISCOVERY=false` is set explicitly, because
 * electron-builder's default is to go looking in the keychain — which makes a
 * developer's machine produce a differently-signed artifact from CI's, silently.
 *
 * Notarisation needs all three Apple variables. It is requested through
 * `--config.mac.notarize=true` rather than being left on in
 * electron-builder.yml, because a notarize attempt without credentials fails
 * the whole run, and an unsigned build is the normal case today.
 */
function signingEnv() {
  const has = (name) => Boolean(process.env[name]);
  const signed = has("CSC_LINK");
  const notarize =
    signed && has("APPLE_ID") && has("APPLE_APP_SPECIFIC_PASSWORD") && has("APPLE_TEAM_ID");

  const env = { ...process.env };
  if (!signed) {
    env.CSC_IDENTITY_AUTO_DISCOVERY = "false";
  }
  return { env, signed, notarize };
}

const version = appVersion();
const { env, signed, notarize } = signingEnv();

console.info(`packaging Hardcore ${version} for ${targets.join(" ")}`);
console.info(
  signed
    ? `signing: on (CSC_LINK), notarisation: ${notarize ? "on" : "off (no APPLE_* credentials)"}`
    : "signing: off (no CSC_LINK) — CSC_IDENTITY_AUTO_DISCOVERY=false",
);

for (const directory of EXTRA_RESOURCE_DIRS) {
  fs.mkdirSync(path.join(appRoot, directory), { recursive: true });
}

// The runtime is the product. A package without one is refused, not warned
// about, because the app it makes says "the CAD runtime did not start" on the
// first STEP file — which is the report this check exists to make impossible.
const runtimeOut = path.join(appRoot, "resources", "runtime");
for (const target of runtimeTargetsFor(targets)) {
  const bundle = bundledRuntime(runtimeOut, target, version);
  if (bundle) {
    console.info(`runtime: ${target} (Python ${bundle.python}, cadgen ${bundle.cadgen}, built ${bundle.builtAt ?? "?"})`);
  } else if (withoutRuntime) {
    console.warn(`runtime: ${target} NOT BUNDLED (--no-runtime): this app will not render CAD`);
  } else {
    console.error(
      `no bundled CAD runtime for ${target} under resources/runtime/ (or not cadgen ${version}).\n` +
        `Run \`npm run bundle:runtime -- --target ${target}\` first (see resources/README.md), or pass --no-runtime to package without one.`,
    );
    process.exit(2);
  }
}

const run = (command, args) => {
  const result = spawnSync(command, args, { cwd: appRoot, stdio: "inherit", shell: false, env });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
};

const npx = process.platform === "win32" ? "npx.cmd" : "npx";

// The same build `npm run build` does: the composed plugin, electron-vite,
// the bundled MCP server (scripts/build.mjs).
run(process.execPath, [path.join(appRoot, "scripts", "build.mjs")]);
run(npx, [
  "electron-builder",
  ...builderArgsFor(targets),
  `--config.extraMetadata.version=${version}`,
  ...(notarize ? ["--config.mac.notarize=true"] : []),
  // Publishing is the release workflow's job, never a local build's: it uploads
  // the artifacts to the GitHub Release it already tags.
  "--publish",
  "never",
]);
