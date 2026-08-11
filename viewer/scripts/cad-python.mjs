// Discover the project's venv Python + cadgen PYTHONPATH for spawning the Python
// CAD Viewer backend (server_py) from Node tooling (the Vite dev proxy and the
// `start` launcher shim). Extracted from the former src/server/step/pythonStepArtifact
// venv discovery so it survives the Node-backend deletion.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = path.resolve(MODULE_DIR, ".."); // viewer/ (scripts/ is under viewer)

function firstExistingFile(paths) {
  return paths.find((candidate) => fs.existsSync(candidate)) || "";
}

function firstExistingDirectory(paths) {
  return paths.find((candidate) => {
    try {
      return fs.statSync(candidate).isDirectory();
    } catch {
      return false;
    }
  }) || "";
}

function findUpFile(relativePath) {
  let current = MODULE_DIR;
  for (;;) {
    const candidate = path.join(current, relativePath);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
    const next = path.dirname(current);
    if (next === current) {
      return "";
    }
    current = next;
  }
}

function findUpDirectory(relativePath) {
  let current = MODULE_DIR;
  for (;;) {
    const candidate = path.join(current, relativePath);
    if (firstExistingDirectory([candidate])) {
      return candidate;
    }
    const next = path.dirname(current);
    if (next === current) {
      return "";
    }
    current = next;
  }
}

export function cadPythonExecutable(repoRoot) {
  const configured = String(process.env.VIEWER_CAD_PYTHON || process.env.CAD_PYTHON || "").trim();
  if (configured) {
    return configured;
  }
  const resolvedRepoRoot = path.resolve(repoRoot || "");
  return firstExistingFile([
    path.join(resolvedRepoRoot, ".venv", "bin", "python"),
    path.join(process.cwd(), ".venv", "bin", "python"),
    path.join(PACKAGE_ROOT, ".venv", "bin", "python"),
    findUpFile(path.join(".venv", "bin", "python")),
  ]) || "python3";
}

export function cadPythonEnv() {
  const pythonPathEntries = [];
  for (const configured of [
    process.env.VIEWER_CAD_PYTHONPATH,
    process.env.CAD_PYTHONPATH,
    process.env.VIEWER_CADPY_PYTHONPATH,
  ]) {
    const value = String(configured || "").trim();
    if (value) {
      pythonPathEntries.push(value);
    }
  }
  for (const discovered of [
    findUpDirectory(path.join("scripts", "packages", "cadgen", "src")),
    findUpDirectory(path.join("viewer", "packages", "cadgen", "src")),
    findUpDirectory(path.join("packages", "cadgen", "src")),
    path.join(PACKAGE_ROOT, "vendor", "python"),
    findUpDirectory(path.join("runtime", "vendor", "python")),
    findUpDirectory(path.join("vendor", "python")),
  ]) {
    if (discovered) {
      pythonPathEntries.push(discovered);
    }
  }
  const existingPythonPath = String(process.env.PYTHONPATH || "").trim();
  if (existingPythonPath) {
    pythonPathEntries.push(existingPythonPath);
  }
  return {
    ...process.env,
    ...(pythonPathEntries.length ? { PYTHONPATH: pythonPathEntries.join(path.delimiter) } : {}),
  };
}
