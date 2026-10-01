/**
 * `npm run package:mac | package:win | package:linux`, and the one entry point
 * the release workflow uses too. Any extra arguments are passed straight to
 * electron-builder, so CI's `--mac --arm64 --x64` needs nothing special here.
 *
 * Three things this does that a bare `electron-builder` invocation would not:
 *
 * 1. Builds first (`scripts/build.mjs`: the composed skills, `electron-vite
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

import { releaseVersion } from "./app-version.mjs";
import { PYTHON_BUILD, bundledRuntime } from "./bundle-runtime.mjs";
import { nodeTool } from "./node-bin.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/**
 * What `extraResources` copies. Recreated rather than assumed so the config
 * never depends on electron-builder's tolerance of a source directory that is
 * not there. `resources/runtime/<target>` is checked, not created: an empty
 * one would package an app that cannot render CAD.
 */
const EXTRA_RESOURCE_DIRS = ["resources/cadgen", "resources/skills", "resources/runtime"];

/**
 * The extraResources electron-builder copies straight from the checkout (the
 * runtime is built, never committed, so it is not here). The release workflow
 * checks out without git-lfs, so an LFS-tracked file among these ships as its
 * 130-byte pointer — the onboarding sample's STEP did. `lfsPointers` finds one
 * before electron-builder copies it.
 */
export const CHECKED_OUT_RESOURCES = ["src/main/browser/vendor/LICENSE", "resources/cadgen", "resources/skills", "resources/sample"];
const LFS_POINTER = "version https://git-lfs";

/** The files under `entries` (relative to `root`) that are Git LFS pointers rather than content. */
export function lfsPointers(root, entries = CHECKED_OUT_RESOURCES) {
  const found = [];
  const visit = (full) => {
    const stat = fs.lstatSync(full, { throwIfNoEntry: false });
    if (stat?.isDirectory()) {
      for (const name of fs.readdirSync(full).sort()) {
        visit(path.join(full, name));
      }
    } else if (stat?.isFile() && stat.size < 1024 && fs.readFileSync(full, "latin1").startsWith(LFS_POINTER)) {
      found.push(path.relative(root, full));
    }
  };
  for (const entry of entries) {
    visit(path.join(root, entry));
  }
  return found;
}

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

/** The macOS signing and notarisation variables, which no other os's build is handed. */
const MAC_SIGNING = ["CSC_LINK", "CSC_KEY_PASSWORD", "APPLE_ID", "APPLE_APP_SPECIFIC_PASSWORD", "APPLE_TEAM_ID"];

/**
 * The secrets each os's signing reads, which the release workflow has to map
 * onto that os's leg for `signingEnv` to see them at all.
 */
export const SIGNING_SECRETS = { mac: MAC_SIGNING, win: ["WIN_CSC_LINK", "WIN_CSC_KEY_PASSWORD"] };

/**
 * Code-signing is on when, and only when, the credentials exist.
 *
 * `CSC_LINK` (+ `CSC_KEY_PASSWORD`) is the macOS certificate and
 * `WIN_CSC_LINK` (+ `WIN_CSC_KEY_PASSWORD`) the Windows one; without it
 * `CSC_IDENTITY_AUTO_DISCOVERY=false` is set explicitly, because
 * electron-builder's default is to go looking in the keychain — which makes a
 * developer's machine produce a differently-signed artifact from CI's, silently.
 *
 * Notarisation needs all three Apple variables. It is requested through
 * `--config.mac.notarize=true` rather than being left on in
 * electron-builder.yml, because a notarize attempt without credentials fails
 * the whole run, and an unsigned build is the normal case today. On CI a
 * signed build that would not be notarised is refused.
 */
export function signingEnv(targets, source = process.env) {
  const oses = Object.keys(OS_NAMES)
    .filter((flag) => targets.includes(flag))
    .map((flag) => OS_NAMES[flag]);
  const has = (name) => Boolean(source[name]);
  const mac = oses.includes("mac");
  // CSC_LINK is the Apple certificate. electron-builder falls back to it for
  // Windows when WIN_CSC_LINK is unset, which would Authenticode-sign the
  // installer with the Apple cert and bake its subject into app-update.yml as
  // the publisher every later update is checked against. So off the Mac it is
  // not passed on at all, and one invocation never mixes the Mac with another os.
  if (mac && oses.length > 1 && has("CSC_LINK")) {
    throw new Error("CSC_LINK is the macOS certificate: package --mac on its own when signing, not together with --win or --linux");
  }
  const env = { ...source };
  if (!mac) {
    for (const name of MAC_SIGNING) {
      delete env[name];
    }
  }
  const signed = mac ? has("CSC_LINK") : oses.includes("win") && has("WIN_CSC_LINK");
  const apple = ["APPLE_ID", "APPLE_APP_SPECIFIC_PASSWORD", "APPLE_TEAM_ID"];
  const notarize = mac && signed && apple.every(has);
  // A signed app that is not notarised is one Gatekeeper refuses on first
  // launch ("cannot be opened because Apple cannot check it"), which is worse
  // than an unsigned one people know to right-click. On a laptop that is a
  // rehearsal; on CI it is a release, so it stops here rather than in a log line.
  if (mac && signed && !notarize && (has("CI") || has("GITHUB_ACTIONS"))) {
    throw new Error(
      `CSC_LINK is set but notarisation is off (missing ${apple.filter((name) => !has(name)).join(", ")}): ` +
        "a CI build signs and notarises, or does neither",
    );
  }

  // Notarisation credentials without a certificate to notarise are a build
  // that was meant to be signed and is not, so on CI it stops here too.
  if (mac && !signed && apple.some(has) && (has("CI") || has("GITHUB_ACTIONS"))) {
    throw new Error(`${apple.filter(has).join(", ")} set but CSC_LINK is not: a CI build signs and notarises, or does neither`);
  }

  if (!signed) {
    env.CSC_IDENTITY_AUTO_DISCOVERY = "false";
  }
  return { env, signed, notarize };
}

/** What `signingEnv` decided, for the build log. */
export function signingLine(targets, { signed, notarize }) {
  // Linux has no certificate to be missing: naming WIN_CSC_LINK there sends
  // someone to set a variable that would change nothing.
  if (!targets.includes("--mac") && !targets.includes("--win")) {
    return "signing: off (Linux builds are not signed) — CSC_IDENTITY_AUTO_DISCOVERY=false";
  }
  const certificate = targets.includes("--mac") ? "CSC_LINK" : "WIN_CSC_LINK";
  return signed
    ? `signing: on (${certificate}), notarisation: ${targets.includes("--mac") ? (notarize ? "on" : "off (no APPLE_* credentials)") : "n/a"}`
    : `signing: off (no ${certificate}) — CSC_IDENTITY_AUTO_DISCOVERY=false`;
}

/**
 * electron-builder, run by this Node from the package's own `cli.js` — not
 * `npx`, whose Windows shim Node refuses to spawn (scripts/node-bin.mjs).
 */
export function electronBuilder(targets, { version, notarize }) {
  return nodeTool("electron-builder", [
    ...builderArgsFor(targets),
    `--config.extraMetadata.version=${version}`,
    ...(notarize ? ["--config.mac.notarize=true"] : []),
    // Publishing is the release workflow's job, never a local build's: it uploads
    // the artifacts to the GitHub Release it already tags.
    "--publish",
    "never",
  ]);
}

function main(argv) {
  // `--no-runtime` is this script's, not electron-builder's: package without
  // the CAD runtime, for a build whose purpose is not CAD (a layout check, a
  // signing rehearsal). A release never passes it.
  const withoutRuntime = argv.includes("--no-runtime");
  const targets = argv.filter((arg) => arg !== "--no-runtime");

  if (targets.length === 0) {
    console.error("usage: node scripts/package.mjs --mac | --win | --linux [--no-runtime] [electron-builder args]");
    process.exit(2);
  }

  let version;
  try {
    version = releaseVersion();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(2);
  }
  let signing;
  try {
    signing = signingEnv(targets);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(2);
  }
  const { env, notarize } = signing;

  console.info(`packaging text-to-cad ${version} for ${targets.join(" ")}`);
  console.info(signingLine(targets, signing));

  for (const directory of EXTRA_RESOURCE_DIRS) {
    fs.mkdirSync(path.join(appRoot, directory), { recursive: true });
  }

  // The runtime is the product. A package without one is refused, not warned
  // about, because the app it makes says "the CAD runtime did not start" on the
  // first STEP file — which is the report this check exists to make impossible.
  const runtimeOut = path.join(appRoot, "resources", "runtime");
  for (const target of runtimeTargetsFor(targets)) {
    const bundle = bundledRuntime(runtimeOut, target, version, path.join(appRoot, "resources", "cadgen"));
    if (bundle) {
      console.info(`runtime: ${target} (Python ${bundle.python}, cadgen ${bundle.cadgen}, built ${bundle.builtAt ?? "?"})`);
    } else if (withoutRuntime) {
      console.warn(`runtime: ${target} NOT BUNDLED (--no-runtime): this app will not render CAD`);
    } else {
      console.error(
        `no bundled CAD runtime for ${target} under resources/runtime/ (or not cadgen ${version} on Python ${PYTHON_BUILD.version}+${PYTHON_BUILD.release}, from the wheel now in resources/cadgen).\n` +
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

  // The same build `npm run build` does: the composed skills, electron-vite,
  // the bundled MCP server (scripts/build.mjs).
  run(process.execPath, [path.join(appRoot, "scripts", "build.mjs")]);
  // After the build, which recomposes resources/skills.
  const pointers = lfsPointers(appRoot);
  if (pointers.length > 0) {
    console.error(
      `these resources are Git LFS pointers, not content, and would ship as such:\n${pointers.map((file) => `  ${file}`).join("\n")}\n` +
        "Take them out of LFS (a .gitattributes beside them, as resources/sample has) or run `git lfs pull`.",
    );
    process.exit(2);
  }
  run(...electronBuilder(targets, { version, notarize }));
}

// Run only as a script: the tests import the functions above, and an import
// must not start a build (or exit on the test runner's own argv).
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2));
}
