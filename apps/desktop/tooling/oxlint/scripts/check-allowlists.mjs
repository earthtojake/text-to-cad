/**
 * Shrink-only allowlist ratchet check.
 *
 * Fails when any entry in tooling/oxlint/allowlists/*.json no longer matches
 * a real boundary violation. Violations missing from the allowlists already
 * fail normal lint, so this script only guards the other direction: allowlists
 * must never carry entries for files that have been fixed.
 *
 * Run `pnpm run prune:boundary-allowlists` to remove stale entries.
 */
import fs from 'node:fs';
import path from 'node:path';
import {
  collectViolationsFromOxlint,
  findStaleAllowlistEntries,
  listAllowlistFiles,
  REPO_ROOT,
} from './allowlist-ratchet.mjs';

const violations = collectViolationsFromOxlint();

let staleCount = 0;
for (const allowlistPath of listAllowlistFiles()) {
  const allowlists = JSON.parse(fs.readFileSync(allowlistPath, 'utf8'));
  const stale = findStaleAllowlistEntries(allowlists, violations);
  const relativePath = path.relative(REPO_ROOT, allowlistPath);
  for (const [category, entries] of Object.entries(stale)) {
    for (const entry of entries) {
      staleCount += 1;
      console.error(`stale allowlist entry: ${relativePath} ${category}: ${entry}`);
    }
  }
}

if (staleCount > 0) {
  console.error(
    `\ncheck-allowlists: ${staleCount} stale ${staleCount === 1 ? 'entry' : 'entries'} — ` +
      'these files no longer violate boundary rules. ' +
      'Run `pnpm run prune:boundary-allowlists` to remove them.'
  );
  process.exit(1);
}

console.log('check-allowlists: all boundary allowlist entries still match violations.');
