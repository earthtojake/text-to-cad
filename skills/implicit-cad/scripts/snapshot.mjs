#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptsDir = path.dirname(fileURLToPath(import.meta.url));
const packageCli = path.join(scriptsDir, "packages", "implicitjs", "scripts", "snapshot.mjs");

const { runRenderCli } = await import(pathToFileURL(packageCli).href).catch((error) => {
  process.stderr.write(
    `Missing implicitjs snapshot CLI at ${packageCli}. Restore the development symlink layout or rebuild the production skill bundle.\n${error instanceof Error ? error.message : String(error)}\n`
  );
  process.exit(1);
});

process.exitCode = await runRenderCli(process.argv.slice(2), {
  cwd: process.cwd(),
  stdin: process.stdin,
  stdout: process.stdout,
  stderr: process.stderr,
});
