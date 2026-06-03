import { createCadViewerApiMiddleware, sendJson } from "./httpHandlers.mjs";
import { createVercelBlobAssetBackend } from "./vercelBlobAssetBackend.mjs";
import {
  envValue,
  normalizeViewerAssetBackend,
  vercelBlobConfigFromEnv,
  VIEWER_ASSET_BACKENDS,
} from "./viewerEnv.mjs";


function vercelUrlFromHost(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return "";
  }
  try {
    const url = new URL(rawValue.includes("://") ? rawValue : `https://${rawValue}`);
    const pathname = url.pathname.replace(/\/+$/g, "");
    return `${url.protocol}//${url.host}${pathname === "/" ? "" : pathname}`;
  } catch {
    return "";
  }
}


export function hostedViewerPublicUrlFromEnv(env = process.env) {
  const candidates = [
    "VERCEL_PROJECT_PRODUCTION_URL",
    "VERCEL_URL",
    "VERCEL_BRANCH_URL",
  ];
  for (const name of candidates) {
    const url = vercelUrlFromHost(envValue(env, name));
    if (url) {
      return url;
    }
  }
  return "";
}


export function createHostedCadBackendFromEnv(env = process.env) {
  const assetBackend = normalizeViewerAssetBackend(
    envValue(env, "VIEWER_ASSET_BACKEND"),
    VIEWER_ASSET_BACKENDS.VERCEL_BLOB
  );
  if (assetBackend !== VIEWER_ASSET_BACKENDS.VERCEL_BLOB) {
    throw new Error("Hosted CAD API requires VIEWER_ASSET_BACKEND=vercel-blob");
  }
  return createVercelBlobAssetBackend({
    ...vercelBlobConfigFromEnv(env),
    readOnly: true,
  });
}


export function buildHostedViewerServerInfo({
  backend,
  env = process.env,
  rootDir = "",
} = {}) {
  return {
    schemaVersion: 1,
    app: "cad-viewer",
    backend: backend?.kind || "vercel-blob",
    rootDir,
    catalogPath: backend?.catalogPath || vercelBlobConfigFromEnv(env).catalogPath,
    stepArtifactGenerationAvailable: false,
    url: hostedViewerPublicUrlFromEnv(env),
  };
}


export async function handleHostedCadApi(req, res, {
  cadPath,
  backend = createHostedCadBackendFromEnv(),
  env = process.env,
} = {}) {
  const normalizedCadPath = String(cadPath || "").trim();
  if (!normalizedCadPath.startsWith("/__cad/")) {
    sendJson(res, 500, { error: `Invalid CAD API path: ${normalizedCadPath || "(missing)"}` });
    return;
  }

  const blobConfig = vercelBlobConfigFromEnv(env);
  if (req.method === "GET" && normalizedCadPath === "/__cad/catalog" && blobConfig.catalogUrl) {
    res.statusCode = 307;
    res.setHeader("location", blobConfig.catalogUrl);
    res.setHeader("cache-control", "no-store");
    res.setHeader("access-control-allow-origin", "*");
    res.end("");
    return;
  }

  const originalUrl = req.url || "/";
  const originalRequestUrl = new URL(originalUrl, "http://localhost");
  originalRequestUrl.searchParams.delete("dir");
  req.url = `${normalizedCadPath}${originalRequestUrl.search}`;
  try {
    const middleware = createCadViewerApiMiddleware({
      backend,
      rootDir: "",
      enableStepArtifactBackend: false,
      claimDisabledStepArtifactRoute: true,
      preferFileDownloadRedirects: true,
      serverInfo: () => buildHostedViewerServerInfo({ backend, env, rootDir: "" }),
    });
    await middleware(req, res, () => {
      sendJson(res, 404, { error: "CAD API route not found" });
    });
  } finally {
    req.url = originalUrl;
  }
}
