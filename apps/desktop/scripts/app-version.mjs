// The app's version is the repository's VERSION file — one canonical release
// version for cadgen, the skills and the desktop app (AGENTS.md: "Treat
// VERSION as the canonical release version. Do not hand-edit duplicate
// package ... versions"). package.json therefore stays at 0.0.0 and every
// build stamps the real number:
//
//   - electron.vite.config.ts defines __APP_VERSION__ from here,
//   - scripts/package.mjs passes it to electron-builder as
//     --config.extraMetadata.version, which is what the installer, the
//     updater feed and app.getVersion() read.
//
// Printed to stdout when run directly, so shell callers can use it too.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** Absolute path of the repository's canonical VERSION file. */
export const versionFile = path.resolve(appRoot, "..", "..", "VERSION");

/**
 * The canonical release version.
 *
 * Falls back to `0.0.0` outside a checkout (the packaged app never reads this;
 * it reads the version electron-builder stamped into its own package.json).
 */
export function appVersion() {
  try {
    const raw = fs.readFileSync(versionFile, "utf8").trim();
    if (/^\d+\.\d+\.\d+/.test(raw)) {
      return raw;
    }
    throw new Error(`not a semver version: ${JSON.stringify(raw)}`);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return "0.0.0";
    }
    throw error;
  }
}

/**
 * `version`, unless it is the `0.0.0` stand-in `appVersion()` answers without
 * a VERSION file. A build a person installs must carry the real number: the
 * updater compares it, the skills root is keyed by it, and a 0.0.0 installer
 * would never be offered an update. `scripts/package.mjs` refuses to run
 * without one.
 */
export function releaseVersion(version = appVersion()) {
  if (version === "0.0.0") {
    throw new Error(`no release version: ${versionFile} is missing (or says 0.0.0); packaging needs the real one`);
  }
  return version;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.stdout.write(`${appVersion()}\n`);
}
