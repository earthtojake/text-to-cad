import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const currentDir = path.dirname(fileURLToPath(import.meta.url));

export const DEFAULT_REPO_ROOT = path.resolve(currentDir, '../..');
export const DEFAULT_BOUNDARY_ALLOWLIST_PATH = path.join(
  currentDir,
  'allowlists/core-boundaries.json'
);
export const DEFAULT_API_SURFACE_ALLOWLIST_PATH = path.join(
  currentDir,
  'allowlists/api-surfaces.json'
);

const BOUNDARY_CATEGORIES = ['coreToHost', 'mainCoreToFeatures', 'crossSlice', 'tsxInApi'];

const EMPTY_ALLOWLISTS = Object.freeze({});

function normalizePath(value) {
  return value.replaceAll('\\', '/');
}

function normalizeEntry(entry, repoRoot) {
  return normalizePath(
    path.isAbsolute(entry) ? path.resolve(entry) : path.resolve(repoRoot, entry)
  );
}

/**
 * When set, boundary rules report allowlisted violations too. The allowlist
 * ratchet (tooling/oxlint/scripts/check-allowlists.mjs) uses this to compare
 * the full violation set against the allowlist files.
 */
export function isBoundaryAllowlistingDisabled(env = process.env) {
  return env.EMDASH_DISABLE_BOUNDARY_ALLOWLISTS === '1';
}

/**
 * Loads the boundary allowlists. A category key that is absent from the
 * allowlist file is valid and means "no exceptions": the missing key is not
 * synthesized, `isBoundaryFileAllowlisted` returns false for it, and every
 * violation of that boundary is a hard lint error. A missing allowlist file
 * means the same for every boundary category (core-boundaries.json was
 * deleted once all core boundary exceptions were drained).
 */
export function loadBoundaryAllowlists(allowlistPath = DEFAULT_BOUNDARY_ALLOWLIST_PATH) {
  if (isBoundaryAllowlistingDisabled()) return EMPTY_ALLOWLISTS;
  try {
    const parsed = JSON.parse(fs.readFileSync(allowlistPath, 'utf8'));
    const allowlists = {};
    for (const category of BOUNDARY_CATEGORIES) {
      if (Array.isArray(parsed[category])) allowlists[category] = parsed[category];
    }
    return allowlists;
  } catch (error) {
    if (error?.code === 'ENOENT') return EMPTY_ALLOWLISTS;
    throw error;
  }
}

/**
 * `entries` may be undefined when the category has no allowlist key; that
 * means no file is exempt from the boundary rule.
 */
export function isBoundaryFileAllowlisted(filename, entries, repoRoot = DEFAULT_REPO_ROOT) {
  if (!filename || !Array.isArray(entries) || entries.length === 0) return false;
  const normalizedFilename = normalizePath(path.resolve(filename));
  return entries.some((entry) => normalizeEntry(entry, repoRoot) === normalizedFilename);
}
