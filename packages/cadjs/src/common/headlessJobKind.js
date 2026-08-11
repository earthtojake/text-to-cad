// Which backend renders a headless snapshot job: the mesh path (STEP/GLB/STL/3MF)
// or the implicit raymarch path. Kept dependency-free so it is unit-testable in
// the node test runner (headlessRenderEntry.js pulls in gifenc/three/implicitjs
// and is only loadable through the esbuild bundle).
//
// The Python CLI stamps resolved.kind at resolve time; the .implicit.js
// URL-suffix fallback keeps direct/programmatic callers working without a
// resolved payload.
export function resolveHeadlessJobKind(job) {
  const resolved = job && typeof job === "object" && job.resolved && typeof job.resolved === "object"
    ? job.resolved
    : {};
  const kind = String(resolved.kind || (job && typeof job === "object" ? job.kind : "") || "").trim().toLowerCase();
  if (kind === "implicit") {
    return "implicit";
  }
  if (kind) {
    // A robot resolves to ordinary mesh data (loadSource assembles it), so it renders
    // through the mesh backend rather than needing a third one.
    return "mesh";
  }
  const url = String(
    resolved.inputUrl
    || resolved.url
    || (job && typeof job === "object" ? job.inputUrl || job.url : "")
    || (typeof job === "string" ? job : "")
    || ""
  ).toLowerCase();
  return url.endsWith(".implicit.js") ? "implicit" : "mesh";
}
