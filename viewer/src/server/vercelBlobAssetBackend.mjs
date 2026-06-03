import path from "node:path";

function normalizePrefix(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return "";
  }
  try {
    return new URL(rawValue).pathname.replace(/^\/+|\/+$/g, "");
  } catch {
    return rawValue.replace(/^\/+|\/+$/g, "");
  }
}

function joinBlobPath(prefix, fileRef) {
  const normalizedRef = normalizeFileRef(fileRef);
  return [normalizePrefix(prefix), normalizedRef].filter(Boolean).join("/");
}

function publicBlobUrlForRef(prefix, fileRef) {
  const rawPrefix = String(prefix || "").trim();
  if (!rawPrefix) {
    return "";
  }
  try {
    const url = new URL(rawPrefix);
    const prefixPath = url.pathname.replace(/^\/+|\/+$/g, "");
    const normalizedRef = normalizeFileRef(fileRef);
    if (!normalizedRef) {
      return "";
    }
    url.pathname = `/${[prefixPath, normalizedRef].filter(Boolean).join("/")}`;
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return "";
  }
}

function normalizeFileRef(value) {
  const normalized = path.posix.normalize(String(value || "").trim().replace(/\\/g, "/").replace(/^\/+/, ""));
  return normalized && normalized !== "." && !normalized.startsWith("../") ? normalized : "";
}

function catalogEntryForFileRef(catalog, fileRef) {
  const normalized = normalizeFileRef(fileRef);
  if (!normalized || !Array.isArray(catalog?.entries)) {
    return null;
  }
  return catalog.entries.find((entry) => (
    normalizeFileRef(entry?.file) === normalized
  )) || null;
}

function normalizeString(value) {
  return String(value || "").trim();
}

function sourceUrlFromEntry(entry) {
  return normalizeString(entry?.sourceUrl || entry?.source?.url);
}

function stepUrlFromEntry(entry) {
  const explicitStepUrl = normalizeString(entry?.stepUrl || entry?.step?.url);
  if (explicitStepUrl) {
    return explicitStepUrl;
  }
  const sourceKind = String(entry?.sourceKind || entry?.stepSourceKind || "").trim().toLowerCase();
  return sourceKind === "python" ? "" : sourceUrlFromEntry(entry);
}

function outputUrlFromEntry(entry, fileRef) {
  const extension = path.posix.extname(normalizeFileRef(fileRef)).toLowerCase();
  if (extension === ".step" || extension === ".stp") {
    return stepUrlFromEntry(entry);
  }
  return normalizeString(entry?.outputUrl || entry?.output?.url || entry?.url);
}

function sourceFileRefFromEntry(entry) {
  return (
    normalizeFileRef(entry?.sourceFile || entry?.source?.file || entry?.source?.path) ||
    normalizeFileRef(filenameFromUrl(sourceUrlFromEntry(entry)))
  );
}

function stepFileRefFromEntry(entry, fallback = "") {
  return (
    normalizeFileRef(entry?.stepFile || entry?.step?.file || entry?.step?.path) ||
    normalizeFileRef(fallback)
  );
}

function filenameFromUrl(url) {
  try {
    return path.posix.basename(new URL(url).pathname);
  } catch {
    return "";
  }
}

function artifactFileRefFromEntry(entry) {
  return (
    normalizeFileRef(entry?.assetFile || entry?.asset?.file || entry?.artifactFile || entry?.artifact?.file) ||
    normalizeFileRef(filenameFromUrl(entry?.url))
  );
}

function normalizedFileAssetKind(value) {
  const asset = String(value || "output").trim().toLowerCase();
  if (asset === "asset") {
    return "artifact";
  }
  if (asset === "output" || asset === "source" || asset === "artifact") {
    return asset;
  }
  throw new Error(`Unsupported file asset: ${asset || "(missing)"}`);
}

export function contentTypeForFileRef(fileRef, fallback = "") {
  const extension = path.posix.extname(normalizeFileRef(fileRef)).toLowerCase();
  if (fallback) {
    return fallback;
  }
  if (extension === ".glb") {
    return "model/gltf-binary";
  }
  if (extension === ".stl") {
    return "model/stl";
  }
  if (extension === ".3mf") {
    return "model/3mf";
  }
  if (extension === ".step" || extension === ".stp") {
    return "application/step";
  }
  if (extension === ".dxf") {
    return "application/dxf";
  }
  if (extension === ".gcode") {
    return "text/plain; charset=utf-8";
  }
  if (extension === ".js" || extension === ".mjs") {
    return "text/javascript; charset=utf-8";
  }
  if (extension === ".json") {
    return "application/json; charset=utf-8";
  }
  if (extension === ".urdf" || extension === ".srdf" || extension === ".sdf") {
    return "application/xml; charset=utf-8";
  }
  return "application/octet-stream";
}

const contentTypeForSourceRef = contentTypeForFileRef;

async function loadBlobClient(client) {
  if (client) {
    return client;
  }
  try {
    return await import("@vercel/blob");
  } catch (error) {
    throw new Error(
      `Vercel Blob backend requires @vercel/blob to be installed: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

async function readJsonFromUrl(url, { fetchImpl = globalThis.fetch } = {}) {
  if (!fetchImpl) {
    throw new Error("Vercel Blob backend requires fetch to read catalog URLs");
  }
  const response = await fetchImpl(url);
  if (!response.ok) {
    throw new Error(`Failed to read Vercel Blob catalog: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function readJsonFromBlobGetResult(result, pathname) {
  if (!result) {
    throw new Error(`Vercel Blob catalog not found: ${pathname}`);
  }
  if (!result.stream) {
    throw new Error(`Vercel Blob catalog response had no body: ${pathname}`);
  }
  return new Response(result.stream).json();
}

function hasBlobSdkReadCredentials(token) {
  return Boolean(
    normalizeString(token) ||
    normalizeString(process.env.BLOB_READ_WRITE_TOKEN) ||
    (normalizeString(process.env.VERCEL_OIDC_TOKEN) && normalizeString(process.env.BLOB_STORE_ID))
  );
}

export function createVercelBlobAssetBackend({
  prefix = "",
  catalogPath = "catalog.json",
  catalogUrl = "",
  client = null,
  fetchImpl = globalThis.fetch,
  token = process.env.VIEWER_VERCEL_BLOB_READ_WRITE_TOKEN || process.env.BLOB_READ_WRITE_TOKEN,
  readOnly = false,
} = {}) {
  const normalizedPrefix = normalizePrefix(prefix);
  const normalizedCatalogPath = joinBlobPath(normalizedPrefix, catalogPath || "catalog.json");
  const resolvedCatalogUrl = catalogUrl || publicBlobUrlForRef(prefix, catalogPath || "catalog.json");

  async function blobClient() {
    return loadBlobClient(client);
  }

  async function readCatalog() {
    if (resolvedCatalogUrl) {
      return readJsonFromUrl(resolvedCatalogUrl, { fetchImpl });
    }
    if (hasBlobSdkReadCredentials(token)) {
      const blob = await blobClient();
      if (typeof blob.get === "function") {
        const getOptions = { access: "public" };
        if (token) {
          getOptions.token = token;
        }
        return readJsonFromBlobGetResult(
          await blob.get(normalizedCatalogPath, getOptions),
          normalizedCatalogPath
        );
      }
    }
    const blob = await blobClient();
    const listing = await blob.list({ prefix: normalizedCatalogPath, token });
    const catalogBlob = Array.isArray(listing?.blobs)
      ? listing.blobs.find((entry) => entry.pathname === normalizedCatalogPath) || listing.blobs[0]
      : null;
    if (!catalogBlob?.url) {
      throw new Error(`Vercel Blob catalog not found: ${normalizedCatalogPath}`);
    }
    return readJsonFromUrl(catalogBlob.url, { fetchImpl });
  }

  async function writeAsset({ fileRef, body, contentType = "application/octet-stream" } = {}) {
    const pathname = joinBlobPath(normalizedPrefix, fileRef);
    if (!pathname) {
      throw new Error("Missing Vercel Blob asset path");
    }
    const blob = await blobClient();
    return blob.put(pathname, body, {
      access: "public",
      addRandomSuffix: false,
      allowOverwrite: true,
      contentType,
      token,
    });
  }

  async function writeCatalog(catalog) {
    return writeAsset({
      fileRef: catalogPath || "catalog.json",
      body: JSON.stringify({
        schemaVersion: 4,
        entries: Array.isArray(catalog?.entries) ? catalog.entries : [],
      }, null, 2),
      contentType: "application/json; charset=utf-8",
    });
  }

  async function refreshCatalog() {
    return readCatalog();
  }

  async function urlForBlobRef(fileRef) {
    const pathname = joinBlobPath(normalizedPrefix, fileRef);
    if (!pathname) {
      return "";
    }
    const blob = await blobClient();
    const listing = await blob.list({ prefix: pathname, token });
    const match = Array.isArray(listing?.blobs)
      ? listing.blobs.find((entry) => entry.pathname === pathname)
      : null;
    return match?.url || "";
  }

  async function resolveFileAssetAccess({ fileRef, asset = "output", catalog = null } = {}) {
    const assetKind = normalizedFileAssetKind(asset);
    const requestedFileRef = normalizeFileRef(fileRef);
    if (assetKind === "source") {
      throw new Error(
        `Source code is not available in Vercel Blob deployments for ${requestedFileRef || "(missing)"}`
      );
    }
    const currentCatalog = catalog || await readCatalog();
    const entry = catalogEntryForFileRef(currentCatalog, requestedFileRef);
    if (!entry) {
      throw new Error(`CAD catalog entry not found: ${requestedFileRef || "(missing)"}`);
    }

    const outputRef = normalizeFileRef(entry.file || requestedFileRef);
    const outputExtension = path.posix.extname(outputRef).toLowerCase();
    const explicitSourceUrl = sourceUrlFromEntry(entry);
    const explicitSourceRef = sourceFileRefFromEntry(entry);
    const explicitStepUrl = stepUrlFromEntry(entry);
    const explicitStepRef = stepFileRefFromEntry(entry, outputRef);
    const explicitArtifactUrl = normalizeString(entry?.url);
    const explicitArtifactRef = artifactFileRefFromEntry(entry);
    const fileRefForAsset = assetKind === "source"
      ? explicitSourceRef
      : assetKind === "artifact"
        ? explicitArtifactRef
        : outputExtension === ".step" || outputExtension === ".stp"
          ? explicitStepRef
          : outputRef;
    const fallbackUrl = assetKind === "source"
      ? explicitSourceUrl
      : assetKind === "artifact"
        ? explicitArtifactUrl
        : outputUrlFromEntry(entry, fileRefForAsset || outputRef || requestedFileRef);
    const blobUrl = fallbackUrl || !fileRefForAsset ? "" : await urlForBlobRef(fileRefForAsset);
    const url = fallbackUrl || blobUrl;
    if (!fileRefForAsset || !url) {
      throw new Error(
        assetKind === "source"
          ? `Source code is not available in Vercel Blob for ${requestedFileRef || "(missing)"}`
          : assetKind === "artifact"
            ? `Artifact file is not available in Vercel Blob for ${requestedFileRef || "(missing)"}`
          : `Output file is not available in Vercel Blob for ${requestedFileRef || "(missing)"}`
      );
    }
    return {
      asset: assetKind,
      file: fileRefForAsset,
      url,
      filename: path.posix.basename(fileRefForAsset) || filenameFromUrl(url),
      contentType: contentTypeForFileRef(fileRefForAsset),
    };
  }

  async function readFileAsset(request = {}) {
    if (!fetchImpl) {
      throw new Error("Vercel Blob backend requires fetch to download file assets");
    }
    const access = await resolveFileAssetAccess(request);
    const response = await fetchImpl(access.url);
    if (!response.ok) {
      throw new Error(`Failed to download file asset from Blob: ${response.status} ${response.statusText}`);
    }
    const contentType = response.headers?.get?.("content-type") || access.contentType;
    return {
      ...access,
      body: Buffer.from(await response.arrayBuffer()),
      contentType: contentTypeForFileRef(access.file, contentType),
    };
  }

  async function resolveSourceFileAccess(request = {}) {
    return resolveFileAssetAccess({ ...request, asset: "source" });
  }

  async function readSourceFile(request = {}) {
    return readFileAsset({ ...request, asset: "source" });
  }

  async function readStepSourceStatus({ fileRef, catalog = null } = {}) {
    const requestedFileRef = normalizeFileRef(fileRef);
    const currentCatalog = catalog || await readCatalog();
    const entry = catalogEntryForFileRef(currentCatalog, requestedFileRef);
    if (!entry) {
      throw new Error(`STEP catalog entry not found: ${requestedFileRef || "(missing)"}`);
    }
    const repoStepRef = stepFileRefFromEntry(entry, entry.file || requestedFileRef);
    const sourceUrl = stepUrlFromEntry(entry) || (
      readOnly ? "" : await urlForBlobRef(repoStepRef)
    );
    return {
      ok: Boolean(sourceUrl),
      file: repoStepRef,
      stepPath: repoStepRef,
      sourceKind: "step",
      step: sourceUrl
        ? {
            ok: true,
            status: "current",
            missing: false,
            stale: false,
          }
        : {
            ok: false,
            status: "missing",
            missing: true,
            stale: false,
            message: "STEP file is missing.",
          },
    };
  }

  const backend = {
    kind: "vercel-blob",
    readOnly: Boolean(readOnly),
    canGenerateStepArtifacts: false,
    prefix: normalizedPrefix,
    catalogPath: normalizedCatalogPath,
    readCatalog,
    readStepSourceStatus,
    resolveFileAssetAccess,
    readFileAsset,
    resolveSourceFileAccess,
    readSourceFile,
    refreshCatalog,
    urlForBlobRef,
  };

  if (!readOnly) {
    return {
      ...backend,
      writeAsset,
      writeCatalog,
    };
  }

  return backend;
}
