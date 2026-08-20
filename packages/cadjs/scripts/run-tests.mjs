#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(packageRoot, "..", "..");
const sourceRoot = path.join(packageRoot, "src");

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
const tests = (requestedTests.length ? requestedTests : collectTests(sourceRoot)).sort();
if (!tests.length) {
  console.error("No cadjs tests found.");
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
