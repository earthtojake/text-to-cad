import path from "node:path";

import {
  DEFAULT_VIEWER_ROOT_DIR,
  normalizeViewerRootDir,
  resolveViewerRoot,
} from "./catalog/cadDirectoryScanner.mjs";

export const VIEWER_SERVER_INFO_SCHEMA_VERSION = 1;
export const VIEWER_SERVER_API_VERSION = 2;
export const VIEWER_SERVER_APP_ID = "cad-viewer";
export const DEFAULT_VIEWER_HOST = "127.0.0.1";
export const DEFAULT_VIEWER_PORT = 4178;

export function normalizeViewerPort(value, fallback = DEFAULT_VIEWER_PORT) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (Number.isInteger(parsed) && parsed > 0 && parsed <= 65535) {
    return parsed;
  }
  return fallback;
}

function normalizeViewerActiveDirectory(value, directoryRoot) {
  if (!value || typeof value !== "object") {
    return null;
  }
  const rawDir = String(value.dir || "").trim();
  const rawRootPath = String(value.rootPath || "").trim();
  if (!rawDir && !rawRootPath) {
    return null;
  }
  const resolvedRawRootPath = rawRootPath
    ? path.resolve(path.isAbsolute(rawRootPath) ? rawRootPath : path.join(directoryRoot, rawRootPath))
    : "";
  const resolvedRoot = rawRootPath
    ? {
        dir: rawDir,
        rootPath: resolvedRawRootPath,
        rootName: path.basename(resolvedRawRootPath),
      }
    : path.isAbsolute(rawDir)
      ? {
          dir: path.resolve(rawDir),
          rootPath: path.resolve(rawDir),
          rootName: path.basename(path.resolve(rawDir)),
        }
      : resolveViewerRoot(directoryRoot, normalizeViewerRootDir(rawDir));
  const dir = rawDir || resolvedRoot.dir || "";
  const rootPath = resolvedRoot.rootPath || "";
  if (!rootPath) {
    return null;
  }
  return {
    dir,
    rootPath,
    rootName: String(value.rootName || resolvedRoot.rootName || path.basename(rootPath) || dir || "Directory"),
  };
}

export function normalizeViewerActiveDirectories(activeDirectories, directoryRoot) {
  if (!Array.isArray(activeDirectories) || !directoryRoot) {
    return [];
  }
  const seen = new Set();
  const normalized = [];
  for (const value of activeDirectories) {
    const directory = normalizeViewerActiveDirectory(value, directoryRoot);
    if (!directory || !directory.dir || seen.has(directory.rootPath)) {
      continue;
    }
    seen.add(directory.rootPath);
    normalized.push(directory);
  }
  return normalized;
}

export function buildViewerServerInfo({
  directoryRoot,
  rootDir = DEFAULT_VIEWER_ROOT_DIR,
  port = DEFAULT_VIEWER_PORT,
  pid = process.pid,
  host = DEFAULT_VIEWER_HOST,
  backend = "local-fs",
  dynamicRoot = false,
  stepArtifactGenerationAvailable = true,
  viewerVersion = "",
  git = "",
  serverFeatures = [],
  activeDirectories = [],
} = {}) {
  if (!directoryRoot) {
    throw new Error("directoryRoot is required");
  }
  const resolvedDirectoryRoot = path.resolve(directoryRoot);
  const rawRootDir = String(rootDir || "").trim();
  const resolvedViewerRoot = rawRootDir
    ? path.isAbsolute(rawRootDir)
      ? {
          dir: path.resolve(rawRootDir),
          rootPath: path.resolve(rawRootDir),
          rootName: path.basename(path.resolve(rawRootDir)),
        }
      : resolveViewerRoot(resolvedDirectoryRoot, normalizeViewerRootDir(rawRootDir))
    : {
        dir: DEFAULT_VIEWER_ROOT_DIR,
        rootPath: "",
        rootName: "",
      };
  const normalizedPort = normalizeViewerPort(port);
  const normalizedGit = String(git || "").trim();
  const normalizedActiveDirectories = normalizeViewerActiveDirectories(activeDirectories, resolvedDirectoryRoot);
  return {
    schemaVersion: VIEWER_SERVER_INFO_SCHEMA_VERSION,
    serverApiVersion: VIEWER_SERVER_API_VERSION,
    app: VIEWER_SERVER_APP_ID,
    viewerVersion: String(viewerVersion || ""),
    ...(normalizedGit ? { git: normalizedGit } : {}),
    serverFeatures: Array.isArray(serverFeatures)
      ? serverFeatures.map((feature) => String(feature || "").trim()).filter(Boolean)
      : [],
    backend,
    dynamicRoot: Boolean(dynamicRoot),
    directoryRoot: resolvedDirectoryRoot,
    rootDir: resolvedViewerRoot.dir,
    rootPath: resolvedViewerRoot.rootPath,
    rootName: resolvedViewerRoot.rootName,
    activeDirectories: normalizedActiveDirectories,
    port: normalizedPort,
    pid: Number.isInteger(pid) ? pid : process.pid,
    stepArtifactGenerationAvailable: stepArtifactGenerationAvailable !== false,
    url: `http://${host}:${normalizedPort}`,
  };
}

export function isViewerServerInfo(value) {
  return Boolean(
    value &&
    typeof value === "object" &&
    value.app === VIEWER_SERVER_APP_ID &&
    typeof value.rootPath === "string" &&
    Number.isInteger(value.port)
  );
}
