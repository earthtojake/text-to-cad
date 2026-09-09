/**
 * `@hardcore/ui/navigation` — the chrome AROUND a file surface, shared by the two
 * apps that draw one.
 *
 * `./file-view` is one file's contents; this is everything else a person sees:
 * the nav row above it, the breadcrumb in that row, the menus a crumb and a
 * row drop down, the panel column at the right end, the file tree that lives
 * in it, and the empty state when nothing is open. The standalone CAD Viewer
 * and the desktop app's file tab both import from here, so those are the same
 * code and not merely the same design — the two differ in exactly two things:
 * the links only a web build has (Discord, GitHub, the version), and what a
 * host can DO with a file, which is a capability set rather than a fork.
 *
 * The dependency runs one way — the desktop depends on this package and this
 * package depends on nothing of the desktop's — which is why the two things
 * the hosts genuinely differ on, where a directory listing comes from and what
 * an entry menu's items do, are injected as source adapters rather than
 * imported.
 *
 * Exported as SOURCE, like `./file-view`: JSX in `.jsx` files, plain modules
 * in `.js`, with JSDoc where types earned their keep. The consumer's bundler
 * compiles it and needs the same settings `docs/file-view.md` lists.
 */
export { Breadcrumbs } from "./Breadcrumbs.jsx";
export { EmptyState } from "./EmptyState.jsx";
export { EntryContextMenu, EntryMenuItems, useEntryMenuFocusGuard } from "./EntryMenu.jsx";
export { FileNavRow, PanelToggle, PANEL_TOGGLE_CLASSES } from "./FileNavRow.jsx";
export {
  FilePanelColumn,
  PANEL_DEFAULT_WIDTH,
  PANEL_MAX_WIDTH,
  PANEL_MIN_WIDTH,
  clampPanelWidth
} from "./FilePanelColumn.jsx";
export { FileTree } from "./FileTree.jsx";
export { InlineName } from "./InlineName.jsx";
export {
  buildCrumbs,
  menuEntries,
  nameOf,
  parentOf,
  stepToward,
  worktreeMark
} from "./crumbs.js";
export {
  ALL_ENTRY_CAPABILITIES,
  ENTRY_ACTIONS,
  FIELD_ENTRY_ACTIONS,
  WEB_ENTRY_CAPABILITIES,
  entryMenu,
  entryMenuActions,
  revealLabel
} from "./entry-menu.js";
export { fuzzyFilter, fuzzyMatch } from "./fuzzy.js";
export { FileIcon, FolderIcon, fileIconFor } from "./icons.jsx";
export {
  CAD_PANEL,
  FILE_PANEL_TREE,
  SOURCE_PANEL,
  cadPanels,
  markdownPanels,
  nextOpenPanel,
  panelClosedBy,
  panelsFor,
  resolveOpenPanel,
  treePanel
} from "./panels.js";
export { useElementWidth } from "./useElementWidth.js";
