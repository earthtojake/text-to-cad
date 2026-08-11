// Resolve the URL of a sub-asset (the assembly.json descriptor or a component GLB) inside a
// component-GLB package, given the package's own asset URL.
//
// The local-fs catalog asset URL is the query form:
//   /__cad/asset?file=<absolute package dir>&dir=<root>&v=<hash>
//
// The descriptor and components live INSIDE the package directory. The naive
// `${packageUrl}/assembly.json` would append the sub-path after the query string, leaving
// `file=<dir>` pointing at the directory, which the asset server cannot serve (404 -> "is not a
// component-GLB package"). So we resolve the relative ref against the package dir explicitly and
// rewrite the `file` param. This is layout-agnostic: it handles the self-contained
// `components/<hash>.glb` refs and any legacy `../../components/<hash>.glb` refs alike.

const URL_RESOLUTION_BASE = "http://cad-viewer.local";

// POSIX-resolve `relPath` against the absolute directory `baseDir`, collapsing "." and "..".
export function resolvePackageDirRef(baseDir, relPath) {
  const segments = String(baseDir).split("/");
  for (const part of String(relPath).split("/")) {
    if (part === "" || part === ".") {
      continue;
    }
    if (part === "..") {
      if (segments.length > 1) {
        segments.pop();
      }
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
  // Repoint `file` at the resolved sub-asset path while preserving `dir`/`v`. Appending to the
  // query string would leave `file` at the directory.
  const parsed = new URL(base, URL_RESOLUTION_BASE);
  const packageDir = parsed.searchParams.get("file");
  if (!packageDir) {
    return "";
  }
  parsed.searchParams.set("file", resolvePackageDirRef(packageDir, ref));
  return `${parsed.pathname}${parsed.search}`;
}
