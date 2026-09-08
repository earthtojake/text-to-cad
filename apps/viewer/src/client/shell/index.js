/**
 * `cad-viewer/shell` — the chrome AROUND a file surface, shared by the two
 * apps that draw one.
 *
 * `./file-view` is one file's contents; this is the row above it and the
 * pieces that row is made of. The standalone CAD Viewer and the desktop app's
 * explorer tab both import from here, so the breadcrumb, its menus, the file
 * icons and the panel toggles are the same code and not merely the same
 * design. The dependency runs one way — the desktop depends on this package
 * and this package depends on nothing of the desktop's — which is why the one
 * thing the hosts genuinely differ on, where a directory listing comes from,
 * is injected as a source adapter rather than imported.
 *
 * Exported as SOURCE, like `./file-view`: JSX in `.jsx` files, plain modules
 * in `.js`, with JSDoc where types earned their keep. The consumer's bundler
 * compiles it and needs the same settings `docs/file-view.md` lists.
 */
export { Breadcrumbs } from "./Breadcrumbs.jsx";
export { FileNavRow, PanelToggle, PANEL_TOGGLE_CLASSES } from "./FileNavRow.jsx";
export { catalogDirectoryListing, createCatalogFileSource } from "./catalogFileSource.js";
export {
  buildCrumbs,
  menuEntries,
  nameOf,
  parentOf,
  stepToward,
  worktreeMark
} from "./crumbs.js";
export { FileIcon, FolderIcon, fileIconFor } from "./icons.jsx";
export { useElementWidth } from "./useElementWidth.js";
