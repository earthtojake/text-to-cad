#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
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
const browserTests = tests.filter((test) => /\.browser\.test\.[cm]?js$/u.test(test));
const nodeTests = tests.filter((test) => !browserTests.includes(test));
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

// Both passes run, so one failing pass still reports the other's results.
const status = run(nodeTests, 4) || 0;
const browserStatus = run(browserTests, browserConcurrency) || 0;
if (status !== 0 || browserStatus !== 0) process.exit(status || browserStatus);
if (!requestedTests.length) {
  const vitest = fileURLToPath(new URL('vitest.mjs', import.meta.resolve('vitest/package.json')));
  const unit = spawnSync(process.execPath, [vitest, 'run', '--config', path.join(packageRoot, 'vitest.config.ts')], { cwd: packageRoot, env: process.env, stdio: 'inherit' });
  process.exit(unit.status ?? 1);
}
