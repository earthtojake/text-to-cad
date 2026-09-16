#!/usr/bin/env node
import { availableParallelism } from "node:os";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
// The backend is cadgen.viewer (Python, in packages/cadgen); its suite runs with
// the cadgen package tests. What lives here is the client and its scripts.
const defaultTestRoots = [
  path.join(packageRoot, "src"),
  path.join(packageRoot, "scripts"),
];

function collectTests(dir, tests = []) {
  if (!fs.existsSync(dir)) {
    return tests;
  }
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
const tests = (requestedTests.length ? requestedTests : defaultTestRoots.flatMap((root) => collectTests(root)))
  .sort();

if (!tests.length) {
  console.error("No CAD Viewer tests found.");
  process.exit(1);
}

// Component and hook tests render through scripts/reactHarness.mjs, and so
// import the client's own sources — which are authored the way Vite builds
// them: JSX inside `.js`, the `@/` alias, extensionless relative imports. Those
// files need the module hooks in scripts/jsxLoaderHooks.mjs. Registering the
// hooks starts a worker thread in every `node --test` process, which cost more
// than the rest of the suite put together, so the handful of tests that need
// them run as their own batch.
function rendersComponents(testPath) {
  return fs.readFileSync(testPath, "utf8").includes("reactHarness.mjs");
}

const batches = [
  { tests: tests.filter((test) => !rendersComponents(test)), nodeArgs: [] },
  {
    tests: tests.filter(rendersComponents),
    // A file URL, not a path: Node's ESM loader parses a Windows absolute path
    // (`D:\...`) as a URL with scheme `d:` and refuses it (test.yml's Windows job).
    nodeArgs: ["--import", pathToFileURL(path.join(packageRoot, "scripts", "registerJsxLoader.mjs")).href],
  },
];

// Each test file is its own process, and most of a file's life here is process
// startup and reading fixtures, not CPU. node:test's default of
// availableParallelism() - 1 therefore leaves cores idle; oversubscribing by 2x
// overlaps those waits. The floor keeps a 1- or 2-core runner overlapping too.
const testConcurrency = Math.max(4, availableParallelism() * 2);

let status = 0;
for (const batch of batches) {
  if (!batch.tests.length) {
    continue;
  }
  const result = spawnSync(process.execPath, [
    ...batch.nodeArgs, "--test", `--test-concurrency=${testConcurrency}`, ...batch.tests,
  ], {
    cwd: packageRoot,
    env: process.env,
    stdio: "inherit",
  });
  status = status || (result.status ?? 1);
}

process.exit(status);
