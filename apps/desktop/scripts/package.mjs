/**
 * `npm run package:mac | package:win | package:linux`.
 *
 * Builds first, then hands electron-builder the repository's VERSION as
 * `extraMetadata.version`. package.json stays at 0.0.0 (see
 * scripts/app-version.mjs): the release version has exactly one home, and this
 * is how it reaches the installer name, `app.getVersion()` and the updater
 * feed without anything being hand-edited.
 *
 * A Node script rather than shell in package.json because
 * `--config.extraMetadata.version=$(cat ../../VERSION)` does not work on
 * Windows, and Windows is one of the three targets.
 */
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { appVersion } from "./app-version.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const targets = process.argv.slice(2);

if (targets.length === 0) {
  console.error("usage: node scripts/package.mjs --mac | --win | --linux [electron-builder args]");
  process.exit(2);
}

const version = appVersion();
console.info(`packaging Hardcore ${version} for ${targets.join(" ")}`);

const run = (command, args) => {
  const result = spawnSync(command, args, { cwd: appRoot, stdio: "inherit", shell: false });
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
  // Publishing is the release workflow's job, never a local build's.
  "--publish",
  "never",
]);
