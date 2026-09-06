/**
 * `npm run package:mac | package:win | package:linux`, and the one entry point
 * the release workflow uses too. Any extra arguments are passed straight to
 * electron-builder, so CI's `--mac --arm64 --x64` needs nothing special here.
 *
 * Three things this does that a bare `electron-builder` invocation would not:
 *
 * 1. Builds first (`electron-vite build`), because electron-builder ships
 *    `out/` and has no opinion about how it got there.
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

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const targets = process.argv.slice(2);

if (targets.length === 0) {
  console.error("usage: node scripts/package.mjs --mac | --win | --linux [electron-builder args]");
  process.exit(2);
}

/**
 * What `extraResources` copies. Empty is a valid state (this build has no
 * bundled wheel); recreated rather than assumed so the config never depends on
 * electron-builder's tolerance of a source directory that is not there.
 */
const EXTRA_RESOURCE_DIRS = ["resources/cadgen", "resources/plugin"];

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

run(npx, ["electron-vite", "build"]);
run(npx, [
  "electron-builder",
  ...targets,
  `--config.extraMetadata.version=${version}`,
  ...(notarize ? ["--config.mac.notarize=true"] : []),
  // Publishing is the release workflow's job, never a local build's: it uploads
  // the artifacts to the GitHub Release it already tags.
  "--publish",
  "never",
]);
