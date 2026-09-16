#!/usr/bin/env node
import { availableParallelism } from "node:os";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(packageRoot, "..", "..");
// Both roots: src/ holds the library tests, scripts/ the CLI ones. A runner that only
// walked src/ would silently stop running any CLI test that lands beside this file.
const testRoots = [path.join(packageRoot, "src"), path.join(packageRoot, "scripts")];

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

// Node 22 is this repo's DECLARED runtime floor (PR #234, after Node 24 broke the JS test
// runners): the packages, the viewer's vite build and CI all assume it, so a suite that
// started on an older Node would be testing a runtime nothing else supports. Refuse up
// front rather than failing somewhere deep in a dependency.
//
// This used to pass `--experimental-default-type=module` on every Node below 22, which was
// wrong at both ends: Node 18 has no such flag and died with `bad option: ...` before
// running a single test, and on Node 20/21 the flag reached only THIS process, so the tests
// that spawn a CLI failed anyway. Say the version out loud instead of half-fixing it.
const nodeMajor = Number(process.versions.node.split(".")[0] || 0);
if (nodeMajor > 0 && nodeMajor < 22) {
  console.error(
    `cadgen-js tests require Node 22 or newer (running ${process.versions.node}): 22 is this `
    + "repository's declared runtime floor."
  );
  process.exit(1);
}

const requestedTests = process.argv.slice(2).map((testPath) => path.resolve(packageRoot, testPath));
const tests = (
  requestedTests.length
    ? requestedTests
    : testRoots.filter((root) => fs.existsSync(root)).flatMap((root) => collectTests(root))
).sort();
if (!tests.length) {
  console.error("No cadgen-js tests found.");
  process.exit(1);
}

// node:test defaults to availableParallelism() - 1 test PROCESSES. Every file here
// spends a good share of its life starting a process and reading fixtures off disk,
// not on the CPU, so that default leaves cores idle: on a 10-core Mac the whole
// suite took 7.3 s at the default 9 and 5.3 s at 20. Oversubscribe by 2x, with a
// floor so a 1- or 2-core runner still overlaps its waits.
const testConcurrency = Math.max(4, availableParallelism() * 2);

const result = spawnSync(process.execPath, [
  "--test",
  `--test-concurrency=${testConcurrency}`,
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
