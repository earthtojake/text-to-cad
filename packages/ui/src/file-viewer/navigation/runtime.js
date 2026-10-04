/**
 * `@text-to-cad/ui/navigation` — the chrome AROUND a file surface, shared by every
 * app that draws one.
 *
 * A renderer draws one file's contents; this is everything else a person sees:
 * the navbar above it (the home logo, the open file's name, which opens the file
 * explorer, its menu, the host's links), the explorer that browses from the file's
 * folder, the column a file's own declared panels open in, and the empty state.
 * Every app imports from here, so those are the same code and not merely the same
 * design. What differs is injected: what a host can DO with a file (a capability
 * set rather than a fork), where its files are read from, where its links point,
 * and its home.
 */
export { EmptyState } from "./EmptyState.jsx";
export { ViewerNavbar, PanelToggle, PANEL_TOGGLE_CLASSES } from "./ViewerNavbar.jsx";
export { AppMenu } from "./AppMenu.jsx";
export { DiscordMark, GitHubMark } from "./brandMarks.jsx";
export { FilePanelColumn, PANEL_DEFAULT_WIDTH, PANEL_MAX_WIDTH, PANEL_MIN_WIDTH, clampPanelWidth } from "./FilePanelColumn.jsx";
export { FolderExplorer, folderTrail, parentFolder } from "./FolderExplorer.jsx";
export { ENTRY_ACTIONS, entryMenu, revealLabel } from "./entry-menu.js";
export { fuzzyFilter, fuzzyMatch } from "./fuzzy.js";
export { TEXT_TO_CAD_LINKS, releaseNotesUrl, releaseVersion, viewerLinks } from "./links.js";
export { FileIcon, FolderIcon, fileIconFor } from "./icons.jsx";
export { nextOpenPanel, resolveOpenPanel } from "./panels.js";
