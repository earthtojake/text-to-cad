/**
 * `@text-to-cad/ui/navigation` — the chrome AROUND a file surface, shared by every
 * app that draws one.
 *
 * A renderer draws one file's contents; this is everything else a person sees:
 * the navbar above it (the home mark, the explorer's toggle, the open file's
 * name and its menu, the host's links), the file explorer that floats over the
 * view's left, the menus a row and the navbar drop down, the column a file's
 * own declared panels open in, and the empty state when nothing is open. Every
 * app imports from here, so those are the same code and not merely the same
 * design. What differs is injected: what a host can DO with a file, which is a
 * capability set rather than a fork, where its links point, and its home.
 *
 * The dependency runs one way — the apps depend on this package and this
 * package depends on nothing of theirs — which is why the things the hosts
 * genuinely differ on, where a directory listing comes from and what an entry
 * menu's items do, are injected as source adapters rather than imported.
 */
export { EmptyState } from "./EmptyState.jsx";
export { EntryMenuItems, useEntryMenuFocusGuard } from "./EntryMenu.jsx";
export { FileExplorer } from "./FileExplorer.jsx";
export { NavbarLinks } from "./NavbarLinks.jsx";
export { ViewerNavbar, PanelToggle, PANEL_TOGGLE_CLASSES } from "./ViewerNavbar.jsx";
export { DiscordMark, GitHubMark } from "./brandMarks.jsx";
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
  ALL_ENTRY_CAPABILITIES,
  ENTRY_ACTIONS,
  FIELD_ENTRY_ACTIONS,
  WEB_ENTRY_CAPABILITIES,
  entryMenu,
  entryMenuActions,
  revealLabel
} from "./entry-menu.js";
export { fuzzyFilter, fuzzyMatch } from "./fuzzy.js";
export { TEXT_TO_CAD_LINKS, releaseNotesUrl, releaseVersion, viewerLinks } from "./links.js";
export { FileIcon, FolderIcon, fileIconFor } from "./icons.jsx";
export {
  FILE_PANEL_TREE,
  nextOpenPanel,
  resolveOpenPanel,
  treePanel
} from "./panels.js";
