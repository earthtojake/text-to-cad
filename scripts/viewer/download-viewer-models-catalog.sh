#!/usr/bin/env bash
set -euo pipefail

function usage() {
  cat <<'EOF'
Usage:
  VIEWER_VERCEL_BLOB_PREFIX=<public-url-prefix> scripts/viewer/download-viewer-models-catalog.sh <target-dir> [--force]

Downloads catalog.json and all catalog-referenced Blob assets from VIEWER_VERCEL_BLOB_PREFIX.

Environment:
  VIEWER_VERCEL_BLOB_PREFIX  Required. Public Blob URL prefix, for example: https://<store>.public.blob.vercel-storage.com/models
  VIEWER_ASSET_BACKEND       Optional. Defaults to vercel-blob.

Options:
  --force     Replace <target-dir> if it already exists.
  -h, --help  Show this help.
EOF
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

: "${VIEWER_VERCEL_BLOB_PREFIX:?Set VIEWER_VERCEL_BLOB_PREFIX to the public Vercel Blob URL prefix before downloading.}"

export VIEWER_ASSET_BACKEND="${VIEWER_ASSET_BACKEND:-vercel-blob}"

node --input-type=module - "$@" <<'NODE'
import { createWriteStream } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

function usage() {
  return `Usage:
  scripts/viewer/download-viewer-models-catalog.sh <target-dir> [--force]

Downloads catalog.json and all catalog-referenced Blob assets from VIEWER_VERCEL_BLOB_PREFIX.

Options:
  --force  Replace <target-dir> if it already exists.
  -h, --help  Show this help.`;
}

function parseArgs(argv) {
  let targetDir = "";
  let force = false;
  for (const arg of argv) {
    if (arg === "-h" || arg === "--help") {
      return { help: true };
    }
    if (arg === "--force") {
      force = true;
      continue;
    }
    if (!targetDir) {
      targetDir = arg;
      continue;
    }
    throw new Error(`Unexpected argument: ${arg}`);
  }
  if (!targetDir) {
    throw new Error("Missing target directory.");
  }
  return { targetDir, force };
}

function catalogUrlFromPrefix(prefix) {
  const url = new URL(prefix);
  const prefixPath = url.pathname.replace(/^\/+|\/+$/g, "");
  url.pathname = `/${[prefixPath, "catalog.json"].filter(Boolean).join("/")}`;
  url.search = "";
  url.hash = "";
  return url;
}

function fileRefForBlobUrl(rawUrl, prefixUrl) {
  const assetUrl = new URL(rawUrl, prefixUrl);
  if (assetUrl.origin !== prefixUrl.origin) {
    return "";
  }

  const prefixPath = prefixUrl.pathname.replace(/\/+$/g, "");
  const assetPath = assetUrl.pathname;
  let relativePath = "";
  if (!prefixPath || prefixPath === "/") {
    relativePath = assetPath.replace(/^\/+/, "");
  } else if (assetPath.startsWith(`${prefixPath}/`)) {
    relativePath = assetPath.slice(prefixPath.length + 1);
  }

  const decoded = decodeURIComponent(relativePath);
  const normalized = path.posix.normalize(decoded.replace(/\\/g, "/").replace(/^\/+/, ""));
  if (!normalized || normalized === "." || normalized.startsWith("../")) {
    return "";
  }
  return normalized;
}

function collectBlobDownloads(catalog, prefixUrl) {
  const downloads = new Map();
  function visit(value) {
    if (Array.isArray(value)) {
      for (const item of value) {
        visit(item);
      }
      return;
    }
    if (!value || typeof value !== "object") {
      return;
    }
    for (const [key, child] of Object.entries(value)) {
      if (typeof child === "string" && (key === "url" || key.endsWith("Url"))) {
        const fileRef = fileRefForBlobUrl(child, prefixUrl);
        if (fileRef && fileRef !== "catalog.json") {
          downloads.set(fileRef, new URL(child, prefixUrl).toString());
        }
        continue;
      }
      visit(child);
    }
  }
  visit(catalog);
  return [...downloads.entries()]
    .map(([fileRef, url]) => ({ fileRef, url }))
    .sort((a, b) => a.fileRef.localeCompare(b.fileRef));
}

function destinationPath(targetDir, fileRef) {
  const normalized = path.posix.normalize(String(fileRef || "").replace(/\\/g, "/").replace(/^\/+/, ""));
  if (!normalized || normalized === "." || normalized.startsWith("../")) {
    throw new Error(`Unsafe catalog path: ${fileRef}`);
  }
  const resolved = path.resolve(targetDir, ...normalized.split("/"));
  if (!resolved.startsWith(`${targetDir}${path.sep}`)) {
    throw new Error(`Catalog path escapes target directory: ${fileRef}`);
  }
  return resolved;
}

async function fetchChecked(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download ${url}: ${response.status} ${response.statusText}`);
  }
  return response;
}

async function downloadFile(url, filePath) {
  const response = await fetchChecked(url);
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const tmpPath = `${filePath}.download`;
  await pipeline(Readable.fromWeb(response.body), createWriteStream(tmpPath));
  await fs.rename(tmpPath, filePath);
}

function prefixUrlFromEnv() {
  try {
    return new URL(process.env.VIEWER_VERCEL_BLOB_PREFIX);
  } catch {
    throw new Error("VIEWER_VERCEL_BLOB_PREFIX must be a full public Vercel Blob URL for downloads.");
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    console.log(usage());
    return;
  }

  const prefixUrl = prefixUrlFromEnv();
  const catalogUrl = catalogUrlFromPrefix(prefixUrl);
  const targetDir = path.resolve(options.targetDir);
  if (targetDir === path.parse(targetDir).root) {
    throw new Error("Refusing to use filesystem root as target directory.");
  }

  try {
    await fs.lstat(targetDir);
    if (!options.force) {
      throw new Error(`Target directory already exists: ${targetDir}. Pass --force to replace it.`);
    }
    await fs.rm(targetDir, { recursive: true, force: true });
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
  }
  await fs.mkdir(targetDir, { recursive: true });

  console.log(`Downloading ${catalogUrl}`);
  const catalogResponse = await fetchChecked(catalogUrl);
  const catalog = await catalogResponse.json();
  const downloads = collectBlobDownloads(catalog, prefixUrl);
  await fs.writeFile(
    path.join(targetDir, "catalog.json"),
    `${JSON.stringify(catalog, null, 2)}\n`
  );

  for (const download of downloads) {
    console.log(`Downloading ${download.fileRef}`);
    await downloadFile(download.url, destinationPath(targetDir, download.fileRef));
  }
  console.log(`Downloaded catalog and ${downloads.length} assets to ${targetDir}`);
}

main().catch((error) => {
  console.error(error?.message || String(error));
  process.exit(1);
});
NODE
