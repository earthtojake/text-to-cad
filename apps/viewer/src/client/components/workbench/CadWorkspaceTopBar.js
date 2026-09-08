import { useMemo } from "react";
import { FolderTree, LoaderCircle, Palette, SlidersHorizontal } from "lucide-react";

import { useSidebar } from "@/components/ui/sidebar";
import {
  buildCrumbs,
  createCatalogFileSource,
  FileNavRow,
  PanelToggle
} from "@/shell/index.js";
import { cadFileParamForEntry, fileKey } from "@/workbench/sidebar";

import FileAccessContextMenu from "./FileAccessContextMenu";
import ViewerLinks from "./ViewerLinks";

/**
 * The standalone viewer's nav row.
 *
 * The row itself, the breadcrumb in it and the menus that breadcrumb drops
 * down are `cad-viewer/shell` — the same code the desktop app's file tab
 * draws, so the two are one bar and not two that resemble each other. What is
 * left here is the standalone's own half: where the listings come from (its
 * catalog, walked in place), the links only a web build has, and the toggles
 * for the two panels the surface owns.
 *
 * The listings are the catalog's, so the menus list what this app can OPEN —
 * every CAD file the served directory holds, and nothing else. The desktop
 * lists a directory as it is on disk, because it can open anything in it.
 */

function fileSheetLabel(fileSheetKind) {
  if (fileSheetKind === "dxf") {
    return "DXF sheet";
  }
  if (fileSheetKind === "urdf") {
    return "URDF sheet";
  }
  if (fileSheetKind === "srdf") {
    return "SRDF sheet";
  }
  if (fileSheetKind === "sdf") {
    return "SDF sheet";
  }
  if (fileSheetKind === "step") {
    return "STEP sheet";
  }
  return "file sheet";
}

/**
 * A bare spinner after the filename. No chip, no text, no percent.
 *
 * The overlay already carries the words and the number; repeating them in the
 * breadcrumb gave the same state two competing readouts that could disagree
 * mid-poll. This says only "this file is busy" and leaves the detail to the
 * one place that owns it. The label still rides on `title` and the
 * screen-reader text, so nothing is lost for a11y or hover. It sits where the
 * desktop's unsaved-changes dot does — one small mark about the open file,
 * after its name.
 */
function FilenameLoadStatus({ activity }) {
  if (!activity?.loading) {
    return null;
  }

  const label = String(activity?.label || "").trim();
  const title = String(activity?.title || label || "Loading").trim();

  return (
    <span role="status" aria-live="polite" title={title} className="ml-1 inline-flex shrink-0 items-center">
      <LoaderCircle className="size-3 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />
      <span className="sr-only">{title}</span>
    </span>
  );
}

export default function CadWorkspaceTopBar({
  previewMode,
  directoryTree = null,
  selectedEntry,
  onSelectEntry,
  filenameLoadActivity = null,
  selectedStepSourceStatus = null,
  canCopyFileAssetPaths = false,
  onRevealInExplorerView,
  onCopyFileAssetReference,
  fileSheetKind = "",
  fileSheetOpen = false,
  onToggleFileSheet,
  themeEditing = false,
  onToggleThemeEditor,
  navigationAvailable = true
}) {
  const { open: sidebarOpen, toggleSidebar } = useSidebar();
  // The open file in the crumb path space: served-root-relative, which is what
  // `?file=` carries and what the catalog's directory ids extend.
  const activePath = selectedEntry ? cadFileParamForEntry(selectedEntry) : null;
  const crumbs = useMemo(
    // Always folded: this bar is one file wide at any window size, and the
    // desktop folds at 720px of pane. Measuring the window here would be
    // measuring the wrong box the moment a panel opens.
    () => buildCrumbs({ path: activePath, narrow: false }),
    [activePath]
  );

  const source = useMemo(
    () => ({
      ...createCatalogFileSource({ directoryTree: navigationAvailable ? directoryTree : null }),
      // The file crumb's right-click: copy this file's paths, reveal it. The
      // desktop's crumbs carry its own entry menu in the same slot.
      wrapCrumb: ({ crumb, children }) =>
        crumb.kind === "file" && selectedEntry ? (
          <FileAccessContextMenu
            entry={selectedEntry}
            stepSourceStatus={selectedStepSourceStatus}
            canCopyFileAssetPaths={canCopyFileAssetPaths}
            onRevealInExplorerView={onRevealInExplorerView}
            onCopyFileAssetReference={onCopyFileAssetReference}
          >
            {children}
          </FileAccessContextMenu>
        ) : (
          children
        )
    }),
    [
      directoryTree,
      navigationAvailable,
      selectedEntry,
      selectedStepSourceStatus,
      canCopyFileAssetPaths,
      onRevealInExplorerView,
      onCopyFileAssetReference
    ]
  );

  if (previewMode) {
    return null;
  }

  // A file picked from a crumb's menu is a catalog entry the menu already
  // carried, so it opens by key rather than by a second lookup on its path.
  const openEntry = (path, item) => {
    const entry = item?.value;
    if (entry && typeof onSelectEntry === "function") {
      onSelectEntry(fileKey(entry));
    }
  };

  const showFileSheetToggle = !!fileSheetKind && typeof onToggleFileSheet === "function";
  const fileSheetToggleLabel = fileSheetOpen
    ? `Collapse ${fileSheetLabel(fileSheetKind)}`
    : `Expand ${fileSheetLabel(fileSheetKind)}`;
  const themeToggleLabel = themeEditing ? "Close theme settings" : "Open theme settings";

  return (
    <FileNavRow
      activePath={activePath}
      crumbs={crumbs}
      onOpen={openEntry}
      source={source}
      status={<FilenameLoadStatus activity={filenameLoadActivity} />}
      trailing={
        <>
          <ViewerLinks previewMode={previewMode} />
          {/* The same glyph the desktop's theme panel declares, so one row of
              toggles does not read as two designs. */}
          <PanelToggle
            active={themeEditing}
            icon={Palette}
            id="cad-theme"
            label={themeToggleLabel}
            onClick={onToggleThemeEditor}
          />
          {showFileSheetToggle ? (
            <PanelToggle
              active={fileSheetOpen && !themeEditing}
              icon={SlidersHorizontal}
              id="cad-file-sheet"
              label={fileSheetToggleLabel}
              onClick={onToggleFileSheet}
            />
          ) : null}
          {/*
            The file list, last and never moving — the desktop's rule, and the
            one control a person can always find in the same place. What it
            opens here is still the LEFT sidebar; folding that into this row's
            panel column is the next piece of work, and the toggle is in its
            final place already so it does not move twice.
          */}
          {navigationAvailable ? (
            <PanelToggle
              active={sidebarOpen}
              icon={FolderTree}
              id="files"
              label={sidebarOpen ? "Hide files" : "Show files"}
              onClick={toggleSidebar}
              testId="tree-toggle"
            />
          ) : null}
        </>
      }
    />
  );
}
