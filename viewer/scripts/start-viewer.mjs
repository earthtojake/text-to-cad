#!/usr/bin/env node
// Self-contained `npm start` for the CAD Viewer runtime.
//
// Run `npm start` where the viewer runtime is installed (source checkout or the
// bundled skill copy under scripts/viewer) and it boots the Python backend. The
// script is intentionally dependency-free so it ships inside the bundled skill
// (scripts/ is copied by build_runtime in scripts/bundle/skills/bundle-cad-viewer.sh);
// the dev-only helpers it used to import (cad-python.mjs, directoryRoot.mjs) are
// not part of the runtime distribution.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const viewerRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// Python: explicit env override wins, then a local venv / python found on PATH.
function findPython() {
  const configured = String(process.env.VIEWER_CAD_PYTHON || process.env.CAD_PYTHON || "").trim();
  if (configured) return configured;
  const candidates = [
    path.join(viewerRoot, ".venv", "Scripts", "python.exe"),
    path.join(viewerRoot, ".venv", "bin", "python"),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return process.platform === "win32" ? "python" : "python3";
}

// PYTHONPATH: same sources the Python tooling uses, so `python -m server_py.*`
// can see the bundled cadgen and this directory's server_py module.
function buildPythonPath() {
  const entries = [];
  for (const key of ["VIEWER_CAD_PYTHONPATH", "CAD_PYTHONPATH", "VIEWER_CADPY_PYTHONPATH"]) {
    const value = String(process.env[key] || "").trim();
    if (value) entries.push(value);
  }
  const bundledCadgen = path.join(viewerRoot, "packages", "cadgen", "src");
  if (existsSync(bundledCadgen) && !entries.includes(bundledCadgen)) entries.push(bundledCadgen);
  if (process.env.PYTHONPATH) entries.push(process.env.PYTHONPATH);
  return entries;
}

// The backend serves whatever directory the URL path names, defaulting to the
// launcher's cwd. Respect npm's INIT_CWD (where `npm start` was run) but stay
// inside the runtime's filesystem reach.
function directoryRoot() {
  const cwd = process.cwd();
  const initCwd = process.env.INIT_CWD ? path.resolve(process.env.INIT_CWD) : "";
  const candidate = initCwd || cwd;
  if (!candidate) return cwd;
  return candidate;
}

const python = findPython();
const pythonPath = buildPythonPath();
const env = {
  ...process.env,
  ...(pythonPath.length ? { PYTHONPATH: pythonPath.join(path.delimiter) } : {}),
};

const child = spawn(python, ["-m", "server_py.start_viewer", ...process.argv.slice(2)], {
  cwd: directoryRoot(),
  env,
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