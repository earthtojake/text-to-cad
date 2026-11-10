#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
// Pure helpers and browser integration tests run in Node; React/editor unit tests use Vitest.
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
  console.error("No UI tests found.");
  process.exit(1);
}

// Browser specs (`*.browser.test.*`) each drive a Chromium doing WebGL, in software on Linux CI:
// four at once saturate a four-core runner until clicks time out. They run as their own pass,
// `UI_BROWSER_TEST_CONCURRENCY` at a time (4 unless set; CI sets 1); everything else stays at 4.
// `UI_BROWSER_TEST_SHARD=I/N` (1-based) splits that pass across N jobs: of the browser specs, sorted by
// path, spec k (0-based) belongs to shard (k % N) + 1 and only shard I's run. It applies to whatever
// browser specs were collected or named on the command line. `UI_TEST_PASS=browser` runs the browser
// pass alone (no Node tests, no Vitest), for the job that runs only a shard.
const fail = (message) => {
  console.error(`run-tests.mjs: ${message}`);
  process.exit(2);
};
const testPass = process.env.UI_TEST_PASS || "";
if (testPass !== "" && testPass !== "browser") {
  fail(`UI_TEST_PASS wants "browser" or nothing, not "${testPass}"`);
}
let shard = null;
const shardValue = process.env.UI_BROWSER_TEST_SHARD || "";
if (shardValue !== "") {
  const match = /^(\d+)\/(\d+)$/u.exec(shardValue);
  const index = match ? Number(match[1]) : 0;
  const count = match ? Number(match[2]) : 0;
  if (!match || index < 1 || index > count) {
    fail(`UI_BROWSER_TEST_SHARD wants I/N with integers 1 <= I <= N (e.g. 1/2), not "${shardValue}"`);
  }
  shard = { index, count };
}
const allBrowserTests = tests.filter((test) => /\.browser\.test\.[cm]?js$/u.test(test));
const browserTests = shard
  ? allBrowserTests.filter((_, k) => k % shard.count === shard.index - 1)
  : allBrowserTests;
if (shard) {
  console.log(`Browser shard ${shard.index}/${shard.count}: ${browserTests.length} of ${allBrowserTests.length} browser specs.`);
  if (!browserTests.length) console.log("This shard has no browser specs; nothing to run in the browser pass.");
}
const nodeTests = testPass === "browser" ? [] : tests.filter((test) => !allBrowserTests.includes(test));
const browserConcurrency = Math.max(1, Number.parseInt(process.env.UI_BROWSER_TEST_CONCURRENCY || "4", 10) || 4);
const run = (files, concurrency) => files.length ? spawnSync(process.execPath, [
  "--test",
  `--test-concurrency=${concurrency}`,
  "--import", path.join(packageRoot, "scripts/registerJsxLoader.mjs"),
  ...files,
], {
  cwd: packageRoot,
  env: process.env,
  stdio: "inherit",
}).status ?? 1 : 0;

// Every pass runs, so one failing pass still reports the others' results.
const status = run(nodeTests, 4) || 0;
// The renderer harness every browser spec serves, bundled once for the pass (`harness/bundle.mjs`).
let browserStatus = 0;
if (browserTests.length) {
  const { HARNESS_DIR, buildHarness } = await import("../src/renderers/harness/bundle.mjs");
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), "text-to-cad-harness-"));
  try {
    await buildHarness(folder);
    process.env[HARNESS_DIR] = folder;
    browserStatus = run(browserTests, browserConcurrency) || 0;
  } finally {
    fs.rmSync(folder, { recursive: true, force: true });
  }
}
if (status !== 0 || browserStatus !== 0) process.exit(status || browserStatus);
if (!requestedTests.length && testPass !== "browser") {
  const unit = spawnSync(process.execPath, [path.join(packageRoot, '../../node_modules/vitest/vitest.mjs'), 'run', '--config', path.join(packageRoot, 'vitest.config.ts')], { cwd: packageRoot, env: process.env, stdio: 'inherit' });
  process.exit(unit.status ?? 1);
}
