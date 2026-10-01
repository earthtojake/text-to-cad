/**
 * The walk `listPaths` replaced, kept as it was, and the tree both are run
 * over: `explorer-list-paths.test.ts` checks the two answer the same, and
 * `scripts/bench/explorer-list-paths/list-paths.mjs` times one against the
 * other. Relative imports only: the bench bundles this file without the
 * app's aliases.
 */
import fs from "node:fs/promises";
import path from "node:path";

import { toRelative } from "../../../src/main/explorer/fs";

/** Named exactly as in `src/main/explorer/fs.ts`: the directories walked last. */
const DEFERRED = new Set([
  ".git", ".hg", ".svn", ".DS_Store", "node_modules", "__pycache__", ".venv",
  ".mypy_cache", ".pytest_cache", ".ruff_cache", ".turbo", ".next", ".vite", ".gradle",
]);
const COLLATOR = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

/** The walk before read-ahead: one `readdir` per await, `shift()` off the queue. */
export async function serialListPaths(root: string, limit = 20_000) {
  const realRoot = await fs.realpath(root);
  const paths: string[] = [];
  const queue: string[] = [realRoot];
  const deferred: string[] = [];
  let truncated = false;
  while ((queue.length > 0 || deferred.length > 0) && !truncated) {
    const current = (queue.length > 0 ? queue : deferred).shift() as string;
    const dirents = await fs.readdir(current, { withFileTypes: true }).catch(() => []);
    for (const dirent of dirents) {
      const child = path.join(current, dirent.name);
      const relative = toRelative(realRoot, child);
      if (dirent.isDirectory()) {
        (relative.split("/").some((segment) => DEFERRED.has(segment)) ? deferred : queue).push(child);
      } else if (dirent.isFile()) {
        if (paths.length >= limit) {
          truncated = true;
          break;
        }
        paths.push(relative);
      }
    }
  }
  paths.sort(COLLATOR.compare);
  return { paths, truncated };
}

/**
 * 300 directories, three deep, with a dependency cache the walk must leave for
 * last: ~5,000 paths, the size of project the measurement pass timed.
 */
export async function writeProjectTree(root: string): Promise<void> {
  const writes: Promise<void>[] = [];
  for (let a = 0; a < 10; a += 1) {
    for (let b = 0; b < 5; b += 1) {
      for (let c = 0; c < 5; c += 1) {
        const dir = path.join(root, `part-${a}`, `v${b}`, `s${c}`);
        await fs.mkdir(dir, { recursive: true });
        for (let f = 0; f < 16; f += 1) writes.push(fs.writeFile(path.join(dir, `f${f}.step`), ""));
      }
    }
  }
  for (let p = 0; p < 20; p += 1) {
    const dir = path.join(root, "node_modules", `pkg-${p}`);
    await fs.mkdir(dir, { recursive: true });
    for (let f = 0; f < 10; f += 1) writes.push(fs.writeFile(path.join(dir, `m${f}.js`), ""));
  }
  await Promise.all(writes);
}
