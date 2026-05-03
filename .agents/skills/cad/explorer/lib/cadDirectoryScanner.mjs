import fs from "node:fs";
import path from "node:path";

export const DEFAULT_EXPLORER_ROOT_DIR = "";

const SOURCE_EXTENSIONS = new Set([".step", ".stp", ".stl", ".3mf", ".dxf", ".urdf"]);
export const EXPLORER_SKIPPED_DIRECTORIES = new Set([
  ".agents",
  ".cache",
  ".explorer",
  ".git",
  ".venv",
  "__pycache__",
  "build",
  "coverage",
  "dist",
  "dist-verify",
  "node_modules",
  "viewer",
]);
const EXPLORER_ARTIFACT_FILENAMES = new Set(["model.glb", "topology.json", "topology.bin"]);
const URDF_EXPLORER_METADATA_FILENAME = "explorer.json";
const URDF_ROBOT_MOTION_DIRECTORY = "robot-motion";

function toPosixPath(value) {
  return String(value || "").split(path.sep).join("/");
}

function encodeUrlPath(repoRelativePath) {
  return `/${repoRelativePath.split("/").map((part) => encodeURIComponent(part)).join("/")}`;
}

export function normalizeExplorerRootDir(value = DEFAULT_EXPLORER_ROOT_DIR) {
  const rawValue = String(value ?? "").trim();
  const slashNormalized = rawValue.replace(/\\/g, "/");
  const normalized = path.posix.normalize(slashNormalized);
  if (!normalized || normalized === ".") {
    return DEFAULT_EXPLORER_ROOT_DIR;
  }
  if (normalized === ".." || normalized.startsWith("../")) {
    throw new Error(`Explorer root directory must stay inside the workspace: ${rawValue}`);
  }
  // Preserve a leading slash so absolute paths flow through to
  // resolveExplorerRoot intact; previously we stripped it, which made an
  // absolute EXPLORER_ROOT_DIR silently resolve as a workspace-relative
  // join onto a nonsensical location.
  return normalized.replace(/(?!^\/)\/+$/, "");
}

export function resolveExplorerRoot(repoRoot, rootDir = DEFAULT_EXPLORER_ROOT_DIR) {
  const normalizedDir = normalizeExplorerRootDir(rootDir);
  const resolvedRepoRoot = path.resolve(repoRoot);
  // path.resolve accepts absolute later arguments and uses them verbatim,
  // so an absolute normalizedDir overrides resolvedRepoRoot here. The
  // workspace-containment check below still rejects paths outside repoRoot.
  const rootPath = normalizedDir
    ? path.resolve(resolvedRepoRoot, normalizedDir)
    : resolvedRepoRoot;
  const relativePath = path.relative(resolvedRepoRoot, rootPath);
  if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    throw new Error(`Explorer root directory must stay inside the workspace: ${normalizedDir}`);
  }
  return {
    dir: normalizedDir,
    rootPath,
    rootName: normalizedDir ? path.basename(rootPath) : path.basename(resolvedRepoRoot),
  };
}

export function repoRelativePath(repoRoot, filePath) {
  return toPosixPath(path.relative(path.resolve(repoRoot), path.resolve(filePath)));
}

function scanRelativePath(rootPath, filePath) {
  return toPosixPath(path.relative(path.resolve(rootPath), path.resolve(filePath)));
}

function fileStats(filePath) {
  try {
    const stats = fs.statSync(filePath, { bigint: true });
    return stats.isFile() ? stats : null;
  } catch {
    return null;
  }
}

function fileVersion(filePath) {
  const stats = fileStats(filePath);
  if (!stats) {
    return "";
  }
  return `${stats.size.toString(36)}-${stats.mtimeNs.toString(36)}`;
}

function assetForPath(repoRoot, filePath) {
  const version = fileVersion(filePath);
  if (!version) {
    return null;
  }
  const repoPath = repoRelativePath(repoRoot, filePath);
  return {
    url: `${encodeUrlPath(repoPath)}?v=${encodeURIComponent(version)}`,
    hash: version,
  };
}

function readJsonObject(filePath) {
  try {
    const payload = JSON.parse(fs.readFileSync(filePath, "utf8"));
    return payload && typeof payload === "object" && !Array.isArray(payload) ? payload : null;
  } catch {
    return null;
  }
}

function stepKindFromTopology(topologyPath) {
  const topology = readJsonObject(topologyPath);
  return topology?.assembly?.root && typeof topology.assembly.root === "object"
    ? "assembly"
    : "part";
}

function sourceFormatFromExtension(extension) {
  const normalized = extension.toLowerCase().replace(/^\./, "");
  return normalized === "stp" ? "stp" : normalized;
}

function isPerStepExplorerDirectoryName(name) {
  const normalized = String(name || "").toLowerCase();
  return normalized.startsWith(".") && (normalized.endsWith(".step") || normalized.endsWith(".stp"));
}

function isPerUrdfExplorerDirectoryName(name) {
  const normalized = String(name || "").toLowerCase();
  return normalized.startsWith(".") && normalized.endsWith(".urdf");
}

function isHiddenDirectoryName(name) {
  return String(name || "").startsWith(".");
}

function isPathInsidePerStepExplorerDirectory(filePath) {
  return String(filePath || "")
    .split(path.sep)
    .some((part) => isPerStepExplorerDirectoryName(part));
}

function isPathInsidePerUrdfExplorerDirectory(filePath) {
  return String(filePath || "")
    .split(path.sep)
    .some((part) => isPerUrdfExplorerDirectoryName(part));
}

function fileRefForSource(rootPath, sourcePath) {
  return scanRelativePath(rootPath, sourcePath);
}

function cadPathForStepSource(repoRoot, sourcePath, extension) {
  const relativePath = repoRelativePath(repoRoot, sourcePath);
  return relativePath.slice(0, -extension.length);
}

function createStepEntry({ repoRoot, rootPath, sourcePath, extension }) {
  const explorerDir = path.join(path.dirname(sourcePath), `.${path.basename(sourcePath)}`);
  const glbPath = path.join(explorerDir, "model.glb");
  const topologyPath = path.join(explorerDir, "topology.json");
  const topologyBinaryPath = path.join(explorerDir, "topology.bin");
  const assets = {};

  for (const [key, assetPath] of [
    ["glb", glbPath],
    ["topology", topologyPath],
    ["topologyBinary", topologyBinaryPath],
  ]) {
    const asset = assetForPath(repoRoot, assetPath);
    if (asset) {
      assets[key] = asset;
    }
  }

  const sourceRelPath = fileRefForSource(rootPath, sourcePath);
  return {
    file: fileRefForSource(rootPath, sourcePath),
    cadPath: cadPathForStepSource(repoRoot, sourcePath, extension),
    kind: stepKindFromTopology(topologyPath),
    name: path.basename(sourcePath),
    source: {
      kind: "file",
      format: sourceFormatFromExtension(extension),
      path: sourceRelPath,
    },
    assets,
    step: {
      path: sourceRelPath,
      hash: fileVersion(sourcePath),
    },
  };
}

function createSingleAssetEntry({ repoRoot, rootPath, sourcePath, extension }) {
  const kind = sourceFormatFromExtension(extension);
  const asset = assetForPath(repoRoot, sourcePath);
  const assets = asset ? { [kind]: asset } : {};
  if (kind === "urdf") {
    const explorerDir = path.join(path.dirname(sourcePath), `.${path.basename(sourcePath)}`);
    const explorerMetadataPath = path.join(explorerDir, URDF_EXPLORER_METADATA_FILENAME);
    const explorerMetadataAsset = assetForPath(repoRoot, explorerMetadataPath);
    if (explorerMetadataAsset) {
      assets.explorerMetadata = explorerMetadataAsset;
    }
    const motionExplorerMetadataPath = path.join(explorerDir, URDF_ROBOT_MOTION_DIRECTORY, URDF_EXPLORER_METADATA_FILENAME);
    const motionExplorerMetadataAsset = assetForPath(repoRoot, motionExplorerMetadataPath);
    if (motionExplorerMetadataAsset) {
      assets.motionExplorerMetadata = motionExplorerMetadataAsset;
    }
  }
  return {
    file: fileRefForSource(rootPath, sourcePath),
    kind,
    name: path.basename(sourcePath),
    source: {
      kind: "file",
      format: kind,
      path: repoRelativePath(repoRoot, sourcePath),
    },
    assets,
  };
}

function shouldSkipDirectory(name) {
  return EXPLORER_SKIPPED_DIRECTORIES.has(name) || isHiddenDirectoryName(name) || isPerStepExplorerDirectoryName(name) || isPerUrdfExplorerDirectoryName(name);
}

function collectCadSourceFiles(rootPath, result = []) {
  let entries = [];
  try {
    entries = fs.readdirSync(rootPath, { withFileTypes: true });
  } catch {
    return result;
  }

  for (const entry of entries) {
    const entryPath = path.join(rootPath, entry.name);
    if (entry.isDirectory()) {
      if (!shouldSkipDirectory(entry.name)) {
        collectCadSourceFiles(entryPath, result);
      }
      continue;
    }
    if (!entry.isFile()) {
      continue;
    }
    const extension = path.extname(entry.name).toLowerCase();
    if (SOURCE_EXTENSIONS.has(extension)) {
      result.push(entryPath);
    }
  }
  return result;
}

function compareEntries(a, b) {
  return String(a.file || "").localeCompare(String(b.file || ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

export function scanCadDirectory({ repoRoot, rootDir = DEFAULT_EXPLORER_ROOT_DIR } = {}) {
  if (!repoRoot) {
    throw new Error("repoRoot is required");
  }
  const resolved = resolveExplorerRoot(repoRoot, rootDir);
  const entries = collectCadSourceFiles(resolved.rootPath)
    .map((sourcePath) => {
      const extension = path.extname(sourcePath).toLowerCase();
      if (extension === ".step" || extension === ".stp") {
        return createStepEntry({
          repoRoot,
          rootPath: resolved.rootPath,
          sourcePath,
          extension,
        });
      }
      return createSingleAssetEntry({
        repoRoot,
        rootPath: resolved.rootPath,
        sourcePath,
        extension,
      });
    })
    .sort(compareEntries);

  return {
    schemaVersion: 3,
    root: {
      dir: resolved.dir,
      name: resolved.rootName,
      path: resolved.dir,
    },
    entries,
  };
}

export function isServedCadAsset(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  if (isPathInsidePerStepExplorerDirectory(filePath)) {
    return extension === ".glb" || EXPLORER_ARTIFACT_FILENAMES.has(path.basename(filePath));
  }
  if (isPathInsidePerUrdfExplorerDirectory(filePath)) {
    return path.basename(filePath) === URDF_EXPLORER_METADATA_FILENAME;
  }
  if (SOURCE_EXTENSIONS.has(extension)) {
    return true;
  }
  return false;
}

export function isCatalogRelevantPath(filePath) {
  return isServedCadAsset(filePath);
}
