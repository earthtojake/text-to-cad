/**
 * Shared logic for the boundary-allowlist ratchet.
 *
 * The allowlists in tooling/oxlint/allowlists/*.json are shrink-only: entries
 * may be removed when a file stops violating a boundary rule, but never added.
 * `check-allowlists.mjs` fails when stale entries remain; the prune script
 * removes them. Both compare the allowlists against the full violation set,
 * produced by running oxlint with EMDASH_DISABLE_BOUNDARY_ALLOWLISTS=1 so the
 * boundary rules report allowlisted violations too.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const currentDir = path.dirname(fileURLToPath(import.meta.url));

export const REPO_ROOT = path.resolve(currentDir, '../../..');
export const ALLOWLISTS_DIR = path.resolve(currentDir, '../allowlists');

export const BOUNDARY_CATEGORIES = ['coreToHost', 'mainCoreToFeatures', 'crossSlice', 'tsxInApi'];

const DESKTOP_CORE_PREFIX = 'apps/emdash-desktop/src/core/';
const MAIN_CORE_PREFIX = 'apps/emdash-desktop/src/main/core/';

function normalizeFilename(filename) {
  const normalized = filename.replaceAll('\\', '/');
  return normalized.startsWith('./') ? normalized.slice(2) : normalized;
}

function boundaryCategory(ruleCode, filename) {
  if (ruleCode === 'emdash(core-module-boundaries)') return 'crossSlice';
  if (ruleCode === 'emdash(no-tsx-in-api)') return 'tsxInApi';
  if (ruleCode === 'emdash(core-host-boundaries)') {
    if (filename.startsWith(MAIN_CORE_PREFIX)) return 'mainCoreToFeatures';
    if (filename.startsWith(DESKTOP_CORE_PREFIX)) return 'coreToHost';
  }
  return undefined;
}

/**
 * Buckets oxlint JSON diagnostics into boundary categories. Filenames are
 * expected to be repo-root-relative (oxlint reports paths relative to its
 * working directory, and the ratchet always runs oxlint from the repo root).
 * Returns `{ coreToHost, mainCoreToFeatures, crossSlice, tsxInApi }` as Sets of paths.
 */
export function collectBoundaryViolations(diagnostics) {
  const violations = Object.fromEntries(
    BOUNDARY_CATEGORIES.map((category) => [category, new Set()])
  );
  for (const diagnostic of diagnostics) {
    const filename = normalizeFilename(diagnostic.filename ?? '');
    const category = boundaryCategory(diagnostic.code, filename);
    if (category) violations[category].add(filename);
  }
  return violations;
}

/**
 * Returns allowlist entries with no matching violation, per category. These
 * are stale: the file no longer violates the boundary rule, so the entry must
 * be removed (the ratchet only shrinks).
 */
export function findStaleAllowlistEntries(allowlists, violations) {
  const stale = {};
  for (const category of BOUNDARY_CATEGORIES) {
    const entries = Array.isArray(allowlists[category]) ? allowlists[category] : [];
    const violating = violations[category] ?? new Set();
    const staleEntries = entries.filter((entry) => !violating.has(normalizeFilename(entry)));
    if (staleEntries.length > 0) stale[category] = staleEntries;
  }
  return stale;
}

export function listAllowlistFiles(allowlistsDir = ALLOWLISTS_DIR) {
  return fs
    .readdirSync(allowlistsDir)
    .filter((name) => name.endsWith('.json'))
    .sort()
    .map((name) => path.join(allowlistsDir, name));
}

/**
 * Runs oxlint over the whole repo with allowlist loading disabled and returns
 * the boundary violations. Boundary diagnostics are errors, so `--quiet`
 * keeps the JSON payload small without hiding them. A non-zero oxlint exit is
 * expected whenever allowlisted violations exist.
 */
export function collectViolationsFromOxlint(repoRoot = REPO_ROOT) {
  const result = spawnSync('pnpm', ['exec', 'oxlint', '--format', 'json', '--quiet', '.'], {
    cwd: repoRoot,
    encoding: 'utf8',
    maxBuffer: 256 * 1024 * 1024,
    shell: process.platform === 'win32',
    env: { ...process.env, EMDASH_DISABLE_BOUNDARY_ALLOWLISTS: '1' },
  });
  if (result.error) throw result.error;

  let parsed;
  try {
    parsed = JSON.parse(result.stdout);
  } catch {
    throw new Error(
      `Failed to parse oxlint JSON output (exit ${result.status}).\n${result.stderr ?? ''}`
    );
  }
  return collectBoundaryViolations(parsed.diagnostics ?? []);
}
