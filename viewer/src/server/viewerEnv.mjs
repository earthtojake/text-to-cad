export const VIEWER_ASSET_BACKENDS = Object.freeze({
  LOCAL_FS: "local-fs",
  VERCEL_BLOB: "vercel-blob",
});

export const DEPRECATED_LOCAL_ROOT_ENV_VARS = Object.freeze([
  "VIEWER_LOCAL_ROOT_DIR",
  "VIEWER_LOCAL_WORKSPACE_ROOT",
]);

const VALID_VIEWER_ASSET_BACKENDS = new Set(Object.values(VIEWER_ASSET_BACKENDS));

export function envValue(env, name, fallback = "") {
  return String(env?.[name] ?? fallback).trim();
}

export function normalizeViewerAssetBackend(value, fallback = VIEWER_ASSET_BACKENDS.LOCAL_FS) {
  const normalized = String(value || fallback || "").trim().toLowerCase();
  if (VALID_VIEWER_ASSET_BACKENDS.has(normalized)) {
    return normalized;
  }
  throw new Error(
    `Unsupported VIEWER_ASSET_BACKEND: ${normalized || "(missing)"}. ` +
    `Expected one of: ${[...VALID_VIEWER_ASSET_BACKENDS].join(", ")}.`
  );
}

export function assertNoDeprecatedLocalRootEnv(env = process.env) {
  const configured = DEPRECATED_LOCAL_ROOT_ENV_VARS.filter((name) => String(env?.[name] || "").trim());
  if (configured.length) {
    throw new Error(
      `${configured.join(", ")} ${configured.length === 1 ? "is" : "are"} no longer supported. ` +
      "Pass ?dir= in the Viewer URL instead."
    );
  }
}

export function vercelBlobCatalogUrlFromPrefix(prefix, catalogPath = "catalog.json") {
  const rawPrefix = envValue({ prefix }, "prefix");
  if (!rawPrefix) {
    return "";
  }
  const normalizedCatalogPath = String(catalogPath || "catalog.json").trim().replace(/^\/+/, "");
  if (!normalizedCatalogPath) {
    return "";
  }
  try {
    const url = new URL(rawPrefix);
    const pathname = url.pathname.replace(/^\/+|\/+$/g, "");
    url.pathname = `/${[pathname, normalizedCatalogPath].filter(Boolean).join("/")}`;
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return "";
  }
}

function normalizeVercelBlobStoreId(value) {
  const normalized = String(value || "").trim().replace(/^store_/i, "");
  return /^[a-z0-9]+$/i.test(normalized) ? normalized.toLowerCase() : "";
}

function vercelBlobStoreIdFromToken(value) {
  const token = String(value || "").trim();
  const parts = token.split("_");
  if (parts[0] !== "vercel" || parts[1] !== "blob") {
    return "";
  }
  const tokenKindLength = parts[2] === "read" && parts[3] === "write" ? 2 : 1;
  return normalizeVercelBlobStoreId(parts[2 + tokenKindLength]);
}

export function vercelBlobStoreIdFromEnv(env = process.env) {
  return (
    normalizeVercelBlobStoreId(envValue(env, "VIEWER_VERCEL_BLOB_STORE_ID")) ||
    normalizeVercelBlobStoreId(envValue(env, "BLOB_STORE_ID")) ||
    vercelBlobStoreIdFromToken(envValue(env, "VIEWER_VERCEL_BLOB_READ_WRITE_TOKEN")) ||
    vercelBlobStoreIdFromToken(envValue(env, "BLOB_READ_WRITE_TOKEN"))
  );
}

export function vercelBlobPrefixFromEnv(env = process.env) {
  const prefix = envValue(env, "VIEWER_VERCEL_BLOB_PREFIX");
  const storeId = vercelBlobStoreIdFromEnv(env);
  if (!prefix || !storeId) {
    return prefix;
  }
  try {
    const url = new URL(prefix);
    const hostname = url.hostname.toLowerCase();
    if (
      hostname.endsWith(".public.blob.vercel-storage.com") ||
      hostname === "blob.vercel-storage.com"
    ) {
      url.hostname = `${storeId}.public.blob.vercel-storage.com`;
      return url.toString();
    }
  } catch {
    const pathname = prefix.replace(/^\/+|\/+$/g, "");
    return `https://${storeId}.public.blob.vercel-storage.com${pathname ? `/${pathname}` : ""}`;
  }
  return prefix;
}

export function vercelBlobConfigFromEnv(env = process.env) {
  const prefix = vercelBlobPrefixFromEnv(env);
  const catalogPath = envValue(env, "VIEWER_VERCEL_BLOB_CATALOG_PATH", "catalog.json") || "catalog.json";
  return {
    prefix,
    catalogPath,
    catalogUrl: vercelBlobCatalogUrlFromPrefix(prefix, catalogPath),
    token: envValue(env, "VIEWER_VERCEL_BLOB_READ_WRITE_TOKEN") || envValue(env, "BLOB_READ_WRITE_TOKEN") || undefined,
  };
}
