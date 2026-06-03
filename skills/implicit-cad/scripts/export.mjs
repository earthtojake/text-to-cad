#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptsDir = path.dirname(fileURLToPath(import.meta.url));
const packageCli = path.join(scriptsDir, "packages", "implicitjs", "scripts", "export.mjs");

if (!fs.existsSync(packageCli)) {
  process.stderr.write(
    `Missing implicitjs export CLI at ${packageCli}. Restore the development symlink layout or rebuild the production skill bundle.\n`
  );
  process.exit(1);
}

const completed = spawnSync(process.execPath, [packageCli, ...process.argv.slice(2)], {
  cwd: process.cwd(),
  stdio: "inherit",
});

process.exitCode = completed.status ?? 1;
