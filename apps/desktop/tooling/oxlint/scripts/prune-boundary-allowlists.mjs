/**
 * Prune-only maintenance for the boundary allowlists.
 *
 * Removes allowlist entries whose files no longer violate the boundary rules.
 * Never adds entries: new violations must be fixed, not allowlisted. The
 * violation set comes from the same oxlint run the ratchet check uses.
 */
import fs from 'node:fs';
import path from 'node:path';
import {
  BOUNDARY_CATEGORIES,
  collectViolationsFromOxlint,
  findStaleAllowlistEntries,
  listAllowlistFiles,
  REPO_ROOT,
} from './allowlist-ratchet.mjs';

const violations = collectViolationsFromOxlint();

let removedCount = 0;
for (const allowlistPath of listAllowlistFiles()) {
  const allowlists = JSON.parse(fs.readFileSync(allowlistPath, 'utf8'));
  const stale = findStaleAllowlistEntries(allowlists, violations);
  const relativePath = path.relative(REPO_ROOT, allowlistPath);

  const staleTotal = Object.values(stale).reduce((sum, entries) => sum + entries.length, 0);
  if (staleTotal === 0) {
    console.log(`prune-boundary-allowlists: ${relativePath} has no stale entries.`);
    continue;
  }

  const pruned = { ...allowlists };
  for (const category of BOUNDARY_CATEGORIES) {
    const staleEntries = new Set(stale[category] ?? []);
    if (staleEntries.size === 0) continue;
    pruned[category] = allowlists[category].filter((entry) => !staleEntries.has(entry));
    for (const entry of stale[category]) {
      console.log(`removed: ${relativePath} ${category}: ${entry}`);
    }
  }

  fs.writeFileSync(allowlistPath, `${JSON.stringify(pruned, null, 2)}\n`);
  removedCount += staleTotal;
}

console.log(
  `prune-boundary-allowlists: removed ${removedCount} stale ${
    removedCount === 1 ? 'entry' : 'entries'
  }.`
);
