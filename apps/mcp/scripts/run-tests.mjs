#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function collectTests(dir, tests = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const entryPath = path.join(dir, entry.name);
    if (entry.isDirectory()) collectTests(entryPath, tests);
    else if (/\.test\.tsx?$/u.test(entry.name)) tests.push(entryPath);
  }
  return tests;
}

// A runner that finds nothing fails rather than reporting a group that never ran.
if (!collectTests(path.join(appRoot, "src")).length) {
  console.error("No CAD app tests found.");
  process.exit(1);
}
const vitest = path.join(appRoot, "../../node_modules/vitest/vitest.mjs");
const result = spawnSync(process.execPath, [vitest, "run", "--config", path.join(appRoot, "vitest.config.mjs"), ...process.argv.slice(2)], {
  cwd: appRoot,
  env: process.env,
  stdio: "inherit",
});
process.exit(result.status ?? 1);
