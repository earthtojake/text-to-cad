import fs from "node:fs";
import path from "node:path";

import { DEFAULT_VIEWER_ROOT_DIR, normalizeViewerRootDir, resolveViewerRoot } from "./cadDirectoryScanner.mjs";
import { toPosixPath } from "cadjs/lib/pathUtils.mjs";

export const GENERATION_STATUS_SCHEMA_VERSION = 1;
export const GENERATION_LOCK_SUFFIX = ".generation.lock.json";
const DEFAULT_ACTIVE_STATUS_MAX_AGE_MS = 30_000;
const IGNORED_STATUS_SCAN_DIRS = new Set([
  ".cache",
  ".git",
  ".hg",
  ".mypy_cache",
  ".pytest_cache",
  ".ruff_cache",
  ".svn",
  ".tox",
  ".venv",
  "build",
  "dist",
  "env",
  "node_modules",
  "site-packages",
  "venv",
  "__pycache__",
]);

function emptyGenerationStatus() {
  return {
    schemaVersion: GENERATION_STATUS_SCHEMA_VERSION,
    runs: [],
    files: {},
  };
}

export function generationStatusDir(repoRoot, rootDir = DEFAULT_VIEWER_ROOT_DIR) {
  const resolvedRepoRoot = path.resolve(repoRoot);
  return resolveViewerRoot(resolvedRepoRoot, normalizeViewerRootDir(rootDir)).rootPath;
}

function pathIsInside(filePath, rootPath) {
  const relative = path.relative(path.resolve(rootPath), path.resolve(filePath));
  return (
    relative === "" ||
    (
      relative !== ".." &&
      !relative.startsWith(`..${path.sep}`) &&
      !path.isAbsolute(relative)
    )
  );
}

function isGenerationLockFileName(name) {
  return String(name || "").startsWith(".") && String(name || "").endsWith(GENERATION_LOCK_SUFFIX);
}

function resolveStatusPath(repoRoot, value, { statusPath = "", rootPath = "" } = {}) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  if (raw.includes("\0")) {
    return "";
  }
  if (path.isAbsolute(raw)) {
    return path.resolve(raw);
  }
  const normalized = raw.replace(/\\/g, "/");
  const statusDir = statusPath ? path.dirname(statusPath) : "";
  const repoCandidate = path.resolve(repoRoot, normalized);
  const shouldPreferStatusDir = (
    statusDir &&
    (
      normalized.startsWith("../") ||
      normalized.startsWith("./") ||
      !normalized.includes("/")
    )
  );
  if (shouldPreferStatusDir) {
    return path.resolve(statusDir, normalized);
  }
  if (rootPath && pathIsInside(repoCandidate, rootPath)) {
    return repoCandidate;
  }
  return repoCandidate;
}

function processIsAlive(pid) {
  const normalizedPid = Number(pid);
  if (!Number.isInteger(normalizedPid) || normalizedPid <= 0) {
    return false;
  }
  try {
    process.kill(normalizedPid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

function timestampMs(value) {
  const ms = Date.parse(String(value || ""));
  return Number.isFinite(ms) ? ms : 0;
}

function statusIsActive(payload, { nowMs = Date.now(), maxAgeMs = DEFAULT_ACTIVE_STATUS_MAX_AGE_MS } = {}) {
  if (String(payload?.status || "").trim().toLowerCase() !== "running") {
    return false;
  }
  if (!processIsAlive(payload?.pid)) {
    return false;
  }
  const updatedAtMs = timestampMs(payload?.updatedAt || payload?.startedAt);
  return !updatedAtMs || nowMs - updatedAtMs <= maxAgeMs;
}

function readStatusPayload(statusPath) {
  try {
    const payload = JSON.parse(fs.readFileSync(statusPath, "utf8"));
    return payload && typeof payload === "object" ? payload : null;
  } catch {
    return null;
  }
}

function listStatusFiles(repoRoot, rootDir = DEFAULT_VIEWER_ROOT_DIR) {
  const statusRoot = generationStatusDir(repoRoot, rootDir);
  const statusFiles = [];
  const visit = (directory) => {
    let entries = [];
    try {
      entries = fs.readdirSync(directory, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const entryPath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        if (!IGNORED_STATUS_SCAN_DIRS.has(entry.name)) {
          visit(entryPath);
        }
        continue;
      }
      if (entry.isFile() && isGenerationLockFileName(entry.name)) {
        statusFiles.push(entryPath);
      }
    }
  };
  visit(statusRoot);
  return statusFiles;
}

function outputEntries(payload) {
  return (Array.isArray(payload?.outputs) ? payload.outputs : [])
    .map((output) => {
      if (typeof output === "string") {
        return { path: output, kind: path.extname(output).toLowerCase().replace(".", "") };
      }
      return {
        path: String(output?.path || "").trim(),
        kind: String(output?.kind || "").trim().toLowerCase(),
      };
    })
    .filter((output) => output.path);
}

export function readGenerationStatus({
  repoRoot,
  rootDir = DEFAULT_VIEWER_ROOT_DIR,
  nowMs = Date.now(),
  maxAgeMs = DEFAULT_ACTIVE_STATUS_MAX_AGE_MS,
} = {}) {
  if (!repoRoot) {
    throw new Error("repoRoot is required");
  }
  const resolvedRepoRoot = path.resolve(repoRoot);
  const resolvedRoot = resolveViewerRoot(resolvedRepoRoot, normalizeViewerRootDir(rootDir));
  const status = emptyGenerationStatus();
  const runsById = new Map();

  for (const statusPath of listStatusFiles(resolvedRepoRoot, rootDir)) {
    const payload = readStatusPayload(statusPath);
    if (!payload || !statusIsActive(payload, { nowMs, maxAgeMs })) {
      continue;
    }
    const runId = String(payload.id || path.basename(statusPath, GENERATION_LOCK_SUFFIX));
    let run = runsById.get(runId);
    if (!run) {
      run = {
        id: runId,
        pid: Number(payload.pid) || 0,
        startedAt: String(payload.startedAt || ""),
        updatedAt: String(payload.updatedAt || ""),
        sourcePath: sourcePathFromStatusPayload(resolvedRepoRoot, payload.sourcePath, statusPath),
        generator: String(payload.generator || ""),
        files: [],
      };
      runsById.set(runId, run);
    }
    for (const output of outputEntries(payload)) {
      const outputPath = resolveStatusPath(resolvedRepoRoot, output.path, {
        statusPath,
        rootPath: resolvedRoot.rootPath,
      });
      if (!outputPath || !pathIsInside(outputPath, resolvedRoot.rootPath)) {
        continue;
      }
      const file = toPosixPath(path.relative(resolvedRoot.rootPath, outputPath));
      if (!file || file.startsWith("../")) {
        continue;
      }
      const fileStatus = {
        running: true,
        runId: run.id,
        pid: run.pid,
        startedAt: run.startedAt,
        updatedAt: run.updatedAt,
        sourcePath: run.sourcePath,
        generator: run.generator,
        kind: output.kind,
      };
      status.files[file] = fileStatus;
      if (!run.files.includes(file)) {
        run.files.push(file);
      }
    }
  }

  status.runs = Array.from(runsById.values()).filter((run) => run.files.length);
  return status;
}

function sourcePathFromStatusPayload(repoRoot, value, statusPath) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  const resolved = resolveStatusPath(repoRoot, raw, { statusPath, rootPath: repoRoot });
  return resolved && pathIsInside(resolved, repoRoot)
    ? toPosixPath(path.relative(path.resolve(repoRoot), resolved))
    : raw.replace(/\\/g, "/");
}

export function isGenerationStatusPath(filePath, repoRoot) {
  if (!repoRoot) {
    return false;
  }
  const resolved = path.resolve(filePath);
  return pathIsInside(resolved, path.resolve(repoRoot)) && isGenerationLockFileName(path.basename(resolved));
}
