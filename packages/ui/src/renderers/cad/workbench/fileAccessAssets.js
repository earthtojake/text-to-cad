// File-access assets are ARTIFACTS ONLY.
//
// This module used to synthesize a third "source" asset by guessing a same-stem `.py`
// sibling for any Python-backed STEP (`moonwatch.step` -> `moonwatch.py`), which put a
// script name in front of the user for a file that is not there: model scripts live in
// `src/` directories, not beside their output. The guess and every affordance built on it
// are gone. Provenance still travels in the sidecar and drives freshness gates; it never
// names a file in the UI.
import {
  normalizeRelativePath as normalizedRelativePath,
  viewerRootRelativePath
} from "./pathPresentation.js";
import { fileKey, normalizeCadFileQueryParam } from "./entryPaths.js";

function basenameFromFileRef(value) {
  const normalized = normalizedRelativePath(value);
  return normalized.split("/").filter(Boolean).pop() || "";
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

export function fileAccessAssetsForEntry(entry, {
  viewerServerInfo = {},
} = {}) {
  const fileRef = fileKey(entry);
  if (!fileRef) {
    return {
      artifact: null,
      output: null,
    };
  }

  const outputFileRef = viewerRootRelativePath(entry?.file || fileRef, viewerServerInfo) ||
    normalizedRelativePath(entry?.file || fileRef);
  const outputFilename = basenameFromFileRef(outputFileRef);
  const artifactRef = artifactFileRef(entry, viewerServerInfo);
  const artifactFilename = basenameFromFileRef(artifactRef);

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
      // No placeholder fallback: copy actions resolve a missing filename from the
      // path basename (copyTargetsForFileAccessAsset) or fail with a clear status.
      filename: outputFilename,
      label: outputFilename,
      rootRelativePath: outputFileRef,
    },
  };
}

export function copyTargetsForFileAccessAsset(asset, viewerServerInfo = {}) {
  // A path relative to the served directory IS a path relative to the root: they are
  // the same directory now, so the old re-basing between them is gone.
  const rawRootRelativePath = normalizedRelativePath(asset?.rootRelativePath);
  const relativePath = rawRootRelativePath
    ? viewerRootRelativePath(rawRootRelativePath, viewerServerInfo, { anchorFile: asset?.fileRef })
    : "";
  const absolutePath = relativePath && viewerServerInfo?.rootPath
    ? joinLocalPath(viewerServerInfo.rootPath, relativePath)
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

// Copy Link renders only for an asset that carries a root-relative ref — without one
// there is no `?file=` value to build, so the item does not appear for that entry.
export function fileAccessAssetHasDeepLink(asset) {
  return Boolean(normalizedRelativePath(asset?.rootRelativePath));
}

export function viewerDeepLinkForFileAccessAsset(asset, viewerServerInfo = {}, {
  origin = "",
} = {}) {
  // A deep link is the URL the app itself lands on when this entry is selected: the
  // bare origin plus `?file=<root-relative ref>`. The ref goes through the same
  // normalization (normalizeCadFileQueryParam) and the same URLSearchParams
  // serialization as writeCadParam, so a copied link and an app-navigated link are
  // byte-identical for the same entry.
  const { relativePath } = copyTargetsForFileAccessAsset(asset, viewerServerInfo);
  const fileParam = normalizeCadFileQueryParam(relativePath);
  const baseOrigin = String(origin || "").trim().replace(/\/+$/, "");
  if (!fileParam || !baseOrigin) {
    return "";
  }
  const params = new URLSearchParams();
  params.set("file", fileParam);
  return `${baseOrigin}/?${params.toString()}`;
}
