import { entrySourceFormat } from "cadjs/lib/fileFormats.js";
import {
  downloadUrlForFileAsset,
  fileAccessAssetsForEntry,
  openUrlForFileAsset
} from "./fileAccessAssets.js";
import { viewerRootRelativePath } from "./pathPresentation.js";

function cleanText(value) {
  return String(value ?? "").trim();
}

function normalizeKind(value) {
  return cleanText(value).toLowerCase();
}

function titleCase(value) {
  const normalized = cleanText(value);
  return normalized ? `${normalized[0].toUpperCase()}${normalized.slice(1)}` : "";
}

function shortHash(value) {
  const text = cleanText(value);
  return text.length > 24 ? `${text.slice(0, 12)}...${text.slice(-8)}` : text;
}

function metadataRow(label, value, options = {}) {
  const text = cleanText(value);
  if (!text) {
    return null;
  }
  return {
    label,
    value: text,
    displayValue: options.short ? shortHash(text) : text,
    href: cleanText(options.href),
    openUrl: cleanText(options.openUrl),
    action: cleanText(options.action),
    asset: options.asset || null,
    copyValue: options.copy === true ? text : cleanText(options.copyValue),
    mono: options.mono === true,
    title: cleanText(options.title) || text
  };
}

function compactRows(rows) {
  return rows.filter(Boolean);
}

function metadataGroup(title, rows) {
  const compactedRows = compactRows(rows);
  return compactedRows.length ? { title, rows: compactedRows } : null;
}

export function formatFileMetadataBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) {
    return "";
  }
  const roundedBytes = Math.round(bytes);
  if (roundedBytes < 1024) {
    return `${roundedBytes} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let scaled = roundedBytes / 1024;
  let unitIndex = 0;
  while (scaled >= 1024 && unitIndex < units.length - 1) {
    scaled /= 1024;
    unitIndex += 1;
  }
  const precision = scaled >= 10 ? 1 : 2;
  const sizeText = scaled
    .toFixed(precision)
    .replace(/(\.\d*?[1-9])0+$/, "$1")
    .replace(/\.0+$/, "");
  return `${sizeText} ${units[unitIndex]} (${roundedBytes.toLocaleString("en-US")} B)`;
}

function fileKindLabel(entry) {
  const kind = normalizeKind(entry?.kind);
  const format = normalizeKind(entrySourceFormat(entry));
  const parts = [
    kind ? titleCase(kind) : "",
    format && format !== kind ? format.toUpperCase() : ""
  ].filter(Boolean);
  return parts.join(" / ");
}

function sourceKindForEntry(entry) {
  const sourceKind = normalizeKind(entry?.sourceKind || entry?.sourceStatus?.sourceKind || entry?.artifact?.sourceKind);
  if (sourceKind === "python" || sourceKind === "step") {
    return sourceKind;
  }
  return sourceKind;
}

function sourceKindLabel(value) {
  const sourceKind = normalizeKind(value);
  if (sourceKind === "python") {
    return "Python-generated";
  }
  if (sourceKind === "step") {
    return "STEP-backed";
  }
  return titleCase(sourceKind);
}

function sourcePathForEntry(entry, sourceAsset, viewerServerInfo = {}) {
  const rawPath = cleanText(
    entry?.source?.sourcePath ||
    entry?.source?.file ||
    entry?.sourceDirectoryFile ||
    sourceAsset?.directoryRelativePath ||
    entry?.sourceFile ||
    sourceAsset?.rootRelativePath
  );
  return viewerRootRelativePath(rawPath, viewerServerInfo, { anchorFile: entry?.file }) || rawPath;
}

function openActionOptionsForAsset(asset) {
  if (!asset) {
    return {};
  }
  return {
    openUrl: openUrlForFileAsset(asset.fileRef, asset.asset),
    action: "open",
    asset
  };
}

function downloadActionOptionsForAsset(asset) {
  if (!asset) {
    return {};
  }
  return {
    href: cleanText(asset.downloadUrl) || downloadUrlForFileAsset(asset.fileRef, asset.asset),
    action: "download",
    asset
  };
}

function fileActionOptionsForAsset(asset, {
  includeFileOpenActions = false,
  includeFileDownloadActions = false
} = {}) {
  if (includeFileOpenActions) {
    return openActionOptionsForAsset(asset);
  }
  if (includeFileDownloadActions) {
    return downloadActionOptionsForAsset(asset);
  }
  return {};
}

function sourceRowsForEntry(entry, {
  includePythonSource = false,
  suppressDynamicStatus = false,
  viewerServerInfo = {},
} = {}) {
  const sourceKind = sourceKindForEntry(entry);
  if (sourceKind === "python" && !includePythonSource) {
    return [];
  }

  const source = entry?.source && typeof entry.source === "object" ? entry.source : {};
  const sourceStatus = entry?.sourceStatus && typeof entry.sourceStatus === "object" ? entry.sourceStatus : {};
  const sourceAssets = fileAccessAssetsForEntry(entry, { viewerServerInfo });
  const sourceAsset = sourceKind === "python" ? sourceAssets.source : null;
  const sourcePath = sourcePathForEntry(entry, sourceAsset, viewerServerInfo);

  return compactRows([
    metadataRow("Kind", sourceKindLabel(sourceKind)),
    sourceKind === "python"
      ? metadataRow("Python source", sourcePath || sourceAsset?.label, {
          ...openActionOptionsForAsset(sourceAsset),
          mono: true,
          title: sourcePath || sourceAsset?.label || "Python source"
        })
      : null,
    suppressDynamicStatus ? null : metadataRow("Status", sourceStatus.status),
    metadataRow("Source hash", source.sourceHash || sourceStatus.sourceHash, { mono: true, short: true, copy: true }),
    suppressDynamicStatus ? null : metadataRow("Current", sourceStatus.currentHash, { mono: true, short: true, copy: true })
  ]);
}

function generatedRowsForEntry(entry, {
  suppressDynamicStatus = false,
  viewerServerInfo = {},
} = {}) {
  const artifact = entry?.artifact && typeof entry.artifact === "object" ? entry.artifact : {};
  const moduleUrl = cleanText(entry?.moduleUrl);
  const modulePath = viewerRootRelativePath(entry?.moduleFile || moduleUrl, viewerServerInfo, { anchorFile: entry?.file }) || moduleUrl;
  if (suppressDynamicStatus) {
    return compactRows([
      metadataRow("Module", modulePath, { href: moduleUrl, mono: true, title: modulePath })
    ]);
  }
  return compactRows([
    metadataRow("Module", modulePath, { href: moduleUrl, mono: true, title: modulePath }),
    metadataRow("Artifact", artifact.error ? titleCase(String(artifact.error).replace(/_/g, " ")) : ""),
    metadataRow("Artifact hash", artifact.artifactHash, { mono: true, short: true, copy: true }),
    metadataRow("Current hash", artifact.currentHash, { mono: true, short: true, copy: true }),
    metadataRow("Message", artifact.message)
  ]);
}

function headerRowsForEntry(entry) {
  const headers = entry?.headers && typeof entry.headers === "object" ? entry.headers : {};
  return Object.entries(headers).flatMap(([name, value]) => {
    const label = cleanText(name);
    if (!label) {
      return [];
    }
    const text = Array.isArray(value)
      ? value.map(cleanText).filter(Boolean).join(", ")
      : value && typeof value === "object"
        ? JSON.stringify(value)
        : cleanText(value);
    return metadataRow(label, text);
  });
}

function relationRowsForEntry(entry, viewerServerInfo = {}) {
  const relations = entry?.relations && typeof entry.relations === "object" ? entry.relations : {};
  return Object.entries(relations).flatMap(([name, relation]) => {
    const label = cleanText(name).toUpperCase();
    if (!label || !relation || typeof relation !== "object") {
      return [];
    }
    return compactRows([
      metadataRow(`${label} file`, viewerRootRelativePath(relation.file, viewerServerInfo, { anchorFile: entry?.file }) || relation.file, { mono: true }),
      metadataRow(`${label} size`, formatFileMetadataBytes(relation.bytes)),
      metadataRow(`${label} hash`, relation.hash, { mono: true, short: true, copy: true })
    ]);
  });
}

export function fileMetadataGroupsForEntry(entry, options = {}) {
  if (!entry || typeof entry !== "object") {
    return [];
  }
  const includeFileOpenActions = options.includeFileOpenActions === true;
  const includeFileDownloadActions = options.includeFileDownloadActions === true;
  const suppressDynamicStatus = options.suppressDynamicStatus === true;
  const viewerServerInfo = options.viewerServerInfo || {};
  const assets = fileAccessAssetsForEntry(entry, { viewerServerInfo });
  const entryFile = viewerRootRelativePath(entry.file, viewerServerInfo) || entry.file;
  const assetPath = assets.artifact?.rootRelativePath ||
    viewerRootRelativePath(entry.assetFile || entry.url, viewerServerInfo, { anchorFile: entry.file }) ||
    entry.url;

  const fileRows = compactRows([
    metadataRow("Path", entryFile, {
      ...fileActionOptionsForAsset(assets.output, { includeFileOpenActions, includeFileDownloadActions }),
      mono: true
    }),
    metadataRow("Kind", fileKindLabel(entry)),
    metadataRow("Size", formatFileMetadataBytes(entry.bytes)),
    metadataRow("Hash", entry.hash, { mono: true, short: true, copy: true }),
    metadataRow("Asset", assetPath, {
      ...fileActionOptionsForAsset(assets.artifact, { includeFileOpenActions, includeFileDownloadActions }),
      mono: true,
      title: assetPath
    })
  ]);

  return [
    metadataGroup("File", fileRows),
    metadataGroup("Headers", headerRowsForEntry(entry)),
    metadataGroup("Source", sourceRowsForEntry(entry, { ...options, viewerServerInfo, suppressDynamicStatus })),
    metadataGroup("Generated", generatedRowsForEntry(entry, { viewerServerInfo, suppressDynamicStatus })),
    metadataGroup("Relations", relationRowsForEntry(entry, viewerServerInfo))
  ].filter(Boolean);
}
