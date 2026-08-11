import { entryStepSourceKind } from "./entryIconStatus.js";
import {
  normalizeRelativePath as normalizedRelativePath,
  stripViewerRootDirPrefix,
  viewerRootRelativePath
} from "./pathPresentation.js";
import { fileKey } from "./sidebar.js";

function basenameFromFileRef(value) {
  const normalized = normalizedRelativePath(value);
  return normalized.split("/").filter(Boolean).pop() || "";
}

function normalizedFilePath(value) {
  const normalized = String(value || "").trim().replace(/\\/g, "/").replace(/\/+$/, "");
  return normalized.startsWith("/")
    ? normalized
    : normalized.replace(/^\/+/, "");
}

function dirnameFromFileRef(value) {
  const parts = normalizedRelativePath(value).split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

function joinRelativePath(...parts) {
  return parts
    .map((part) => normalizedRelativePath(part))
    .filter(Boolean)
    .join("/");
}

function sameStemPythonFilename(value) {
  const filename = basenameFromFileRef(value);
  return filename.replace(/\.(step|stp)$/i, ".py");
}

function sameStemPythonFileRef(value) {
  const dirname = dirnameFromFileRef(value);
  const filename = sameStemPythonFilename(value);
  return joinRelativePath(dirname, filename);
}

function isStepFileRef(value) {
  return /\.(step|stp)$/i.test(normalizedRelativePath(value));
}

function explicitSourceFileRef(entry) {
  return (
    normalizedFilePath(entry?.sourceFile) ||
    normalizedFilePath(entry?.source?.file) ||
    normalizedFilePath(entry?.source?.path)
  );
}

function explicitSourceDirectoryFileRef(entry) {
  return (
    normalizedFilePath(entry?.sourceDirectoryFile) ||
    normalizedFilePath(entry?.source?.directoryFile) ||
    normalizedFilePath(entry?.source?.sourcePath)
  );
}

function artifactFileRef(entry, viewerServerInfo = {}) {
  return (
    viewerRootRelativePath(entry?.assetFile || entry?.artifactFile || entry?.artifact?.file, viewerServerInfo, { anchorFile: entry?.file }) ||
    viewerRootRelativePath(entry?.url, viewerServerInfo, { anchorFile: entry?.file })
  );
}

function localPathSeparator(basePath) {
  return String(basePath || "").includes("\\") ? "\\" : "/";
}

function joinLocalPath(basePath, relativePath) {
  const base = String(basePath || "").trim();
  const relative = normalizedRelativePath(relativePath);
  if (!base || !relative) {
    return base || relative;
  }
  const separator = localPathSeparator(base);
  const normalizedBase = base.replace(/[\\/]+$/, "");
  const normalizedRelative = relative.replace(/\//g, separator);
  return `${normalizedBase}${separator}${normalizedRelative}`;
}

function directoryPathIsInsideViewerRoot(directoryRelativePath, rootDir) {
  const directoryPath = normalizedRelativePath(directoryRelativePath);
  const normalizedRootDir = normalizedRelativePath(rootDir);
  if (!directoryPath) {
    return false;
  }
  if (!normalizedRootDir) {
    return true;
  }
  return directoryPath === normalizedRootDir || directoryPath.startsWith(`${normalizedRootDir}/`);
}

function rootRelativePathFromDirectoryRelativePath(directoryRelativePath, rootDir) {
  return directoryPathIsInsideViewerRoot(directoryRelativePath, rootDir)
    ? stripViewerRootDirPrefix(directoryRelativePath, rootDir)
    : "";
}

export function fileAccessAssetsForEntry(entry, {
  stepSourceStatus = null,
  viewerServerInfo = {},
} = {}) {
  const fileRef = fileKey(entry);
  if (!fileRef) {
    return {
      artifact: null,
      output: null,
      source: null,
    };
  }

  const outputFileRef = viewerRootRelativePath(entry?.file || fileRef, viewerServerInfo) ||
    normalizedRelativePath(entry?.file || fileRef);
  const outputFilename = basenameFromFileRef(outputFileRef);
  const artifactRef = artifactFileRef(entry, viewerServerInfo);
  const artifactFilename = basenameFromFileRef(artifactRef);
  const sourceKind = String(stepSourceStatus?.sourceKind || entryStepSourceKind(entry)).trim().toLowerCase();
  const stepSourcePath = normalizedFilePath(stepSourceStatus?.sourcePath);
  const explicitSourceRef = explicitSourceFileRef(entry);
  const explicitSourceDirectoryRef = explicitSourceDirectoryFileRef(entry);
  const inferredSourceRootRef = sourceKind === "python" && isStepFileRef(outputFileRef)
    ? sameStemPythonFileRef(outputFileRef)
    : "";
  const sourceRef = explicitSourceRef || stepSourcePath || inferredSourceRootRef;
  const sourceDirectoryRef = stepSourcePath || explicitSourceDirectoryRef;
  const hasViewerPathContext = Boolean(
    viewerServerInfo?.rootDir ||
    viewerServerInfo?.rootPath ||
    viewerServerInfo?.directoryRoot
  );
  const sourceRootRef = sourceRef
    ? hasViewerPathContext
      ? (viewerRootRelativePath(sourceRef, viewerServerInfo, { anchorFile: outputFileRef }) || sourceRef)
      : sourceDirectoryRef ? "" : (explicitSourceRef || inferredSourceRootRef)
    : "";
  const sourceFilename = sourceRootRef || sourceRef
    ? (basenameFromFileRef(sourceRootRef || sourceRef) || sameStemPythonFilename(outputFileRef))
    : "";

  return {
    artifact: artifactFilename ? {
      asset: "artifact",
      fileRef,
      filename: artifactFilename,
      label: artifactFilename,
      rootRelativePath: artifactRef,
    } : null,
    output: {
      asset: "output",
      fileRef,
      filename: outputFilename || "download",
      label: outputFilename || "download",
      rootRelativePath: outputFileRef,
    },
    source: sourceFilename ? {
      asset: "source",
      fileRef,
      filename: sourceFilename,
      label: sourceFilename,
      rootRelativePath: sourceRootRef,
      directoryRelativePath: sourceDirectoryRef,
    } : null,
  };
}

export function downloadUrlForFileAsset(fileRef, asset = "output", baseUrl = "") {
  const path = `/__cad/download?file=${encodeURIComponent(fileRef)}&asset=${encodeURIComponent(asset || "output")}`;
  if (!baseUrl) {
    return path;
  }
  try {
    return new URL(path, baseUrl).toString();
  } catch {
    return path;
  }
}

export function openUrlForFileAsset(fileRef, asset = "output", baseUrl = "") {
  const path = `/__cad/reveal?file=${encodeURIComponent(fileRef)}&asset=${encodeURIComponent(asset || "output")}`;
  if (!baseUrl) {
    return path;
  }
  try {
    return new URL(path, baseUrl).toString();
  } catch {
    return path;
  }
}

export function copyTargetsForFileAccessAsset(asset, viewerServerInfo = {}) {
  const rootDir = normalizedRelativePath(viewerServerInfo?.rootDir);
  const directoryRelativePath = normalizedRelativePath(asset?.directoryRelativePath);
  const directoryRootRelativePath = rootRelativePathFromDirectoryRelativePath(directoryRelativePath, rootDir);
  const rawRootRelativePath = directoryRootRelativePath || normalizedRelativePath(asset?.rootRelativePath);
  const rootRelativePath = rawRootRelativePath
    ? viewerRootRelativePath(rawRootRelativePath, viewerServerInfo, { anchorFile: asset?.fileRef })
    : "";
  const relativePath = rootRelativePath || directoryRelativePath;
  const absolutePath = rootRelativePath && viewerServerInfo?.rootPath
      ? joinLocalPath(viewerServerInfo.rootPath, rootRelativePath)
      : directoryRelativePath && viewerServerInfo?.directoryRoot
        ? joinLocalPath(viewerServerInfo.directoryRoot, directoryRelativePath)
        : "";

  return {
    path: absolutePath,
    // The asset carries its own display filename; fall back to the basename of
    // whichever path we could resolve so this is never empty when a path is not.
    filename: String(asset?.filename || "").trim() ||
      basenameFromFileRef(relativePath || absolutePath),
    relativePath,
  };
}
