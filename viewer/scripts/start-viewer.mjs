#!/usr/bin/env node
// Thin shim: launch the Python CAD Viewer launcher (server_py.start_viewer)
// using the project's discovered venv Python + cadgen PYTHONPATH, so `npm start`
// can run the Python backend without the caller knowing the venv path. Reuses the
// proven cadPythonExecutable/cadPythonEnv discovery from the STEP pipeline.
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { cadPythonExecutable, cadPythonEnv } from "./cad-python.mjs";
import { resolveDirectoryRoot } from "./directoryRoot.mjs";

const viewerRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(viewerRoot, "..");
const python = cadPythonExecutable(repoRoot);
const baseEnv = cadPythonEnv(repoRoot);
// server_py lives under viewer/ — prepend it so `python -m server_py.*` resolves.
baseEnv.PYTHONPATH = [viewerRoot, baseEnv.PYTHONPATH].filter(Boolean).join(path.delimiter);

// The backend has no configured directory: a URL path IS the directory, and the bare
// origin falls back to the process cwd. So the child's cwd must be where the USER ran
// `npm start` (npm's INIT_CWD), not viewer/ — `npm --prefix` would otherwise make the
// default directory the viewer's own source tree.
const child = spawn(python, ["-m", "server_py.start_viewer", ...process.argv.slice(2)], {
  cwd: resolveDirectoryRoot({ env: baseEnv, appRoot: viewerRoot }),
  env: baseEnv,
  stdio: "inherit",
});
child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
child.on("error", (error) => {
  process.stderr.write(`Failed to start Python CAD Viewer launcher: ${error.message}\n`);
  process.exit(1);
});
