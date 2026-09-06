// The CAD Viewer's per-file surface, as a source-level entry point.
//
// Two consumers, one implementation: the standalone viewer's shell
// (../components/CadWorkspace.js) and any host that wants the same surface for
// one file — the desktop app's explorer tab, which points it at a
// `cadgen viewer --api-only` of its own with `origin`.
//
// See ../../../docs/file-view.md for what a consumer's bundler and Tailwind
// entry have to be told; this package ships SOURCE, not a build.
export { default as CadFileView } from "./CadFileView.js";
export { ViewerOriginProvider, useViewerOrigin } from "./viewerOriginContext.js";
export {
  applyViewerOriginToEntries,
  applyViewerOriginToEntry,
  isAbsoluteViewerUrl,
  normalizeViewerOrigin,
  viewerOriginUrl
} from "./viewerOrigin.js";
