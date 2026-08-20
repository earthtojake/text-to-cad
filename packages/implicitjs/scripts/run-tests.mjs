#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(packageRoot, "..", "..");
const testRoots = [
  path.join(packageRoot, "src"),
  path.join(packageRoot, "scripts"),
];

function collectTests(dir, tests = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const entryPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      collectTests(entryPath, tests);
    } else if (/\.test\.[cm]?js$/u.test(entry.name)) {
      tests.push(entryPath);
    }
  }
  return tests;
}

const requestedTests = process.argv.slice(2).map((testPath) => path.resolve(packageRoot, testPath));
const tests = (requestedTests.length ? requestedTests : testRoots.flatMap((root) => collectTests(root))).sort();
if (!tests.length) {
  console.error("No implicitjs tests found.");
  process.exit(1);
}

// This suite writes temporary `.implicit.js` fixtures -- bare .js files whose body is
// `export default { ... }`, in a temp dir with no package.json -- and imports them, both
// in-process and through the spawned export CLI. Only Node 22+ reads module syntax out of
// an ambiguous .js, so the floor is a property of the fixtures, not a preference.
//
// This used to pass `--experimental-default-type=module` on every Node below 22, which was
// wrong at both ends: Node 18 has no such flag and died with `bad option: ...` before
// running a single test, and on Node 20/21 the flag reached only THIS process, so the tests
// that spawn the CLI failed anyway. Say the version out loud instead of half-fixing it.
const nodeMajor = Number(process.versions.node.split(".")[0] || 0);
if (nodeMajor > 0 && nodeMajor < 22) {
  console.error(
    `implicitjs tests require Node 22 or newer (running ${process.versions.node}): the .implicit.js `
    + "fixtures are plain .js files with module syntax, which older Node reads as CommonJS."
  );
  process.exit(1);
}

const result = spawnSync(process.execPath, [
  "--test",
  ...tests,
], {
  cwd: packageRoot,
  env: {
    ...process.env,
    ...(fs.existsSync(path.join(repoRoot, ".venv", "bin", "python"))
      ? { CAD_PYTHON: path.join(repoRoot, ".venv", "bin", "python") }
      : {}),
    ...(fs.existsSync(path.join(repoRoot, "packages", "cadgen", "src"))
      ? { CAD_PYTHONPATH: path.join(repoRoot, "packages", "cadgen", "src") }
      : {}),
  },
  stdio: "inherit",
});

process.exit(result.status ?? 1);
