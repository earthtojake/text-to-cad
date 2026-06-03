import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { inlineStepGlbArtifactPathForSource } from "cadjs/common/stepSidecars.mjs";

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = path.resolve(MODULE_DIR, "../../..");

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
    findUpDirectory(path.join("scripts", "packages", "cadpy", "src")),
    findUpDirectory(path.join("scripts", "packages")),
    findUpDirectory(path.join("viewer", "packages", "cadpy", "src")),
    findUpDirectory(path.join("packages", "cadpy", "src")),
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

export function ensurePythonStepTopologyArtifact({
  repoRoot,
  stepPath,
  sourcePath = "",
  force = false,
  skipStepWrite = false,
  writeStepAfterArtifact = false,
  resolveOnFirstResult = false,
  verbose = false,
  meshTolerance = null,
  meshAngularTolerance = null,
} = {}) {
  const resolvedRepoRoot = path.resolve(repoRoot || "");
  const resolvedStepPath = path.resolve(stepPath || "");
  const args = [
    "-m",
    "cadpy.step_artifact",
    "--repo-root",
    resolvedRepoRoot,
    "--step",
    resolvedStepPath,
  ];
  const resolvedSourcePath = sourcePath ? path.resolve(sourcePath) : "";
  if (resolvedSourcePath) {
    args.push("--source-path", resolvedSourcePath);
  }
  if (force) {
    args.push("--force");
  }
  if (skipStepWrite) {
    args.push("--skip-step-write");
  }
  if (writeStepAfterArtifact) {
    args.push("--write-step-after-artifact");
  }
  if (meshTolerance !== null && meshTolerance !== undefined) {
    args.push("--mesh-tolerance", String(meshTolerance));
  }
  if (meshAngularTolerance !== null && meshAngularTolerance !== undefined) {
    args.push("--mesh-angular-tolerance", String(meshAngularTolerance));
  }
  if (verbose || process.env.VIEWER_STEP_ARTIFACT_VERBOSE === "1") {
    args.push("--verbose");
  }
  return new Promise((resolve) => {
    let resolved = false;
    const resolveOnce = (result) => {
      if (resolved) {
        return;
      }
      resolved = true;
      resolve(result);
    };
    const normalizeResult = (result) => {
      if (result?.ok) {
        result.stepPath = resolvedStepPath;
        result.glbPath = inlineStepGlbArtifactPathForSource(resolvedStepPath);
      }
      return result;
    };
    const maybeResolveEarly = () => {
      if (!resolveOnFirstResult || resolved) {
        return;
      }
      for (const line of stdout.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("{")) {
          continue;
        }
        try {
          const result = normalizeResult(JSON.parse(trimmed));
          if (result?.ok) {
            resolveOnce(result);
            return;
          }
        } catch {
          // Keep waiting for a complete JSON line.
        }
      }
    };
    const child = spawn(cadPythonExecutable(resolvedRepoRoot), args, {
      cwd: resolvedRepoRoot,
      env: cadPythonEnv(resolvedRepoRoot),
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
      maybeResolveEarly();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", (error) => {
      resolveOnce({
        ok: false,
        stepPath: resolvedStepPath,
        error: error instanceof Error ? error.message : String(error),
      });
    });
    child.on("close", (code) => {
      const output = stdout.trim();
      const lastJsonLine = output.split(/\r?\n/).reverse().find((line) => line.trim().startsWith("{"));
      if (code === 0 && lastJsonLine) {
        try {
          resolveOnce(normalizeResult(JSON.parse(lastJsonLine)));
          return;
        } catch {
          // Fall through to the structured failure below.
        }
      }
      resolveOnce({
        ok: false,
        stepPath: resolvedStepPath,
        exitCode: code,
        error: (stderr || stdout || `STEP artifact generator exited with code ${code}`).trim(),
      });
    });
  });
}
