// Resolve the URL of a sub-asset (the assembly.json descriptor or a component GLB) inside a
// component-GLB package, given the package's own asset URL.
//
// The local-fs catalog asset URL is the query form:
//   /__cad/asset?file=<absolute package dir>&v=<hash>
//
// The descriptor and components live INSIDE the package directory (packages are
// self-contained: `assembly.json`, `components/<hash>.glb`). The naive
// `${packageUrl}/assembly.json` would append the sub-path after the query string, leaving
// `file=<dir>` pointing at the directory, which the asset server cannot serve (404 -> "is not a
// component-GLB package"). So we resolve the relative ref against the package dir explicitly and
// rewrite the `file` param.

// A package asset URL is either root-relative (the standalone viewer, same
// origin as its backend) or absolute (an embedded surface pointed at another
// `cadgen viewer`). Sub-assets must come back in the SAME shape: dropping the
// origin would send the fetch — and the surf worker's fetch — at whatever host
// happens to be serving the page.
import { isAbsoluteViewerUrl } from "../../../file-view/viewerOrigin.js";

const URL_RESOLUTION_BASE = "http://cad-viewer.local";

// Join `relPath` under the absolute directory `baseDir`. Package refs are plain
// paths inside the package; nothing escapes the package directory.
export function resolvePackageDirRef(baseDir, relPath) {
  const segments = String(baseDir).split("/");
  for (const part of String(relPath).split("/")) {
    if (part === "" || part === ".") {
      continue;
    }
    segments.push(part);
  }
  const joined = segments.join("/");
  return joined.startsWith("/") ? joined : `/${joined}`;
}

export function resolvePackageAssetUrl(packageAssetUrl, relPath) {
  const base = String(packageAssetUrl || "").trim();
  const ref = String(relPath || "").trim();
  if (!base || !ref) {
    return "";
  }
  // Repoint `file` at the resolved sub-asset path while preserving `v`. Appending to the
  // query string would leave `file` at the directory.
  const parsed = new URL(base, URL_RESOLUTION_BASE);
  const packageDir = parsed.searchParams.get("file");
  if (!packageDir) {
    return "";
  }
  parsed.searchParams.set("file", resolvePackageDirRef(packageDir, ref));
  const originPrefix = isAbsoluteViewerUrl(base) ? parsed.origin : "";
  return `${originPrefix}${parsed.pathname}${parsed.search}`;
}
