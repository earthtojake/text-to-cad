/**
 * The resource a prompt names a document by. A view identifies its file by absolute path (the
 * live state's resource, the catalog's key); what a person copies or sends names it the way the
 * host spells it: by that path, or — where the host's files have an address
 * (`FileSource.address`, a hosted build's `https://host/b/<build>/<path>`) — by that URL, so a
 * reference pasted anywhere still says exactly which file it means.
 *
 * @param {{ address?: (path: string) => string } | null | undefined} source  The view's `FileSource`.
 * @param {{ kind: string, path?: string, revision?: string }} resource  The document, as the view identifies it.
 * @returns {{ kind: string, path?: string, url?: string, revision?: string }}
 */
export function promptResourceFor(source, resource) {
  if (!resource || resource.kind !== "workspace-file" || typeof source?.address !== "function") return resource;
  const url = String(source.address(resource.path) || "").trim();
  if (!url) return resource;
  return resource.revision ? { kind: "url", url, revision: resource.revision } : { kind: "url", url };
}

/** The name a copied reference begins with: the host's address for the file, or its absolute path. */
export function referencePathFor(source, path) {
  const address = typeof source?.address === "function" ? String(source.address(path) || "").trim() : "";
  return address || String(path || "");
}

/** The file's name without its extension, from a path or a URL: what a capture of it is called. */
export function resourceStem(resource) {
  let name = String(resource?.path || "");
  if (!name && resource?.url) {
    try { name = decodeURIComponent(new URL(resource.url).pathname); } catch { name = String(resource.url); }
  }
  return name.split("/").pop().replace(/\.[^.]+$/, "") || "view";
}
