/**
 * Which build of the CAD Viewer or the CAD app a page is, for the version its app menu shows:
 * `viewerLinks({ version, build })` (`@text-to-cad/ui/links`) reads `0.7.15` for the release's own
 * build and `0.7.15-dev.<build>` for any other. Each app's Vite config hands it to its page as
 * `__TEXT_TO_CAD_BUILD__`.
 *
 * The release's own build is the one whose environment names the version it builds in
 * `TEXT_TO_CAD_RELEASE` (the release workflow's bundle step sets it), and it has no build id. Any
 * other build is custom, and its id says what it was built from: the commit of the checkout
 * (`b80844940`), with `-dirty` when a file git tracks there had changes no commit holds yet (a
 * file git does not track changes a build only through one it does), or, outside a checkout,
 * when it was built (UTC, `20261007153012`). A marker that is missing, or that names another
 * version, makes a custom build: a forgotten marker shows a release as `-dev`, and nothing
 * passes a custom build off as a release.
 */
import { execFileSync } from "node:child_process";

/** The variable a release's own build names its version in. */
export const RELEASE_ENV = "TEXT_TO_CAD_RELEASE";

/**
 * What git prints for `args` in `cwd`, or null where it cannot answer (no git, no checkout). It
 * takes no lock a git command running meanwhile in the checkout would trip over.
 */
function git(cwd, ...args) {
  try {
    return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], timeout: 10_000,
      maxBuffer: 64 * 1024 * 1024, env: { ...process.env, GIT_OPTIONAL_LOCKS: "0" } }).trim();
  } catch {
    return null;
  }
}

/**
 * This build's id: "" for the release's own build of `version`, else the checkout's commit (and
 * `-dirty`), else the time of the build.
 *
 * @param {{ version: string, env?: Record<string, string | undefined>, cwd?: string, now?: Date }} options
 *   `cwd`: a directory of the checkout the build is made from.
 */
export function buildId({ version, env = process.env, cwd = process.cwd(), now = new Date() }) {
  const release = String(env[RELEASE_ENV] ?? "").trim();
  if (release && release === String(version ?? "").trim()) return "";
  const commit = git(cwd, "rev-parse", "--short", "HEAD");
  if (!commit) return now.toISOString().replace(/\D/gu, "").slice(0, 14);
  return git(cwd, "status", "--porcelain", "--untracked-files=no") ? `${commit}-dirty` : commit;
}
