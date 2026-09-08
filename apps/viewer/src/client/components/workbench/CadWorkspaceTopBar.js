import { useMemo } from "react";
import { EllipsisVertical, LoaderCircle } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import {
  EntryContextMenu,
  EntryMenuItems,
  FileNavRow,
  PanelToggle,
  buildCrumbs,
  createCatalogFileSource,
  useEntryMenuFocusGuard
} from "@/shell/index.js";
import { cadFileParamForEntry } from "@/workbench/sidebar";

import { useStandaloneEntryActions, webEntryCapabilities } from "./standaloneEntryActions.js";
import { useWorkspacePanels } from "./workspacePanels.js";

/**
 * The standalone viewer's nav row.
 *
 * The row itself, the breadcrumb in it, the menus that breadcrumb drops down,
 * the `⋯` after the file's name and the panel toggles at the right end are all
 * `cad-viewer/shell` — the same code the desktop app's file tab draws, so the
 * two are one bar and not two that resemble each other. What is left here is
 * the standalone's own half: where the listings come from (its catalog, walked
 * in place) and the links only a web build has.
 *
 * The links are the ONE visible difference between this row and the desktop
 * app's: Discord, GitHub and the version, after the toggles. The toggles
 * themselves are the shared panel list in declaration order with the file tree
 * last, which is the desktop's rule and the reason the control a person
 * reaches for is in the same place in both.
 *
 * The listings are the catalog's, so the menus and the tree list what this app
 * can OPEN — every CAD file the served directory holds, and nothing else. The
 * desktop lists a directory as it is on disk, because it can open anything in
 * it.
 */

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

/**
 * The file crumb's `⋯`: the menu the right-click opens, drawn as a dropdown.
 *
 * One table, one set of actions, two doors — because a right-click is not a
 * control anybody can see. The desktop app draws the same button, in the same
 * place, over the same table; the only difference is which items survive the
 * capability filter.
 */
function CrumbActions({ path, capabilities, platform, onAction }) {
  const guard = useEntryMenuFocusGuard(onAction);
  const entry = { path, kind: "file", surface: "crumb" };
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button
          aria-label="File actions"
          className="flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-accent data-[state=open]:text-accent-foreground"
          data-testid="crumb-actions"
          title="File actions"
          type="button"
        >
          <EllipsisVertical className="size-3.5" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className="w-56"
        data-entry-menu={entry.path}
        onCloseAutoFocus={guard.onCloseAutoFocus}
        sideOffset={6}
      >
        <EntryMenuItems
          capabilities={capabilities}
          entry={entry}
          onAction={guard.onAction}
          platform={platform}
          surface="dropdown"
        />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default function CadWorkspaceTopBar({ chrome }) {
  const {
    previewMode,
    selectedEntry,
    allEntriesTree,
    filenameLoadActivity,
    canCopyFileAssetPaths,
    openPanel,
    onTogglePanel
  } = chrome;

  const panels = useWorkspacePanels(chrome);
  const { onAction, platform } = useStandaloneEntryActions(chrome);
  const capabilities = useMemo(
    () => webEntryCapabilities(canCopyFileAssetPaths),
    [canCopyFileAssetPaths]
  );

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
    () => createCatalogFileSource({
      directoryTree: allEntriesTree,
      slots: {
        // A crumb's right-click and the file crumb's `⋯`: the shared entry
        // menu, filtered to what a browser tab can do.
        wrapCrumb: ({ crumb, children }) => (
          <EntryContextMenu
            capabilities={capabilities}
            entry={{ path: crumb.path, kind: crumb.kind === "file" ? "file" : "directory", surface: "crumb" }}
            onAction={onAction}
            platform={platform}
          >
            {children}
          </EntryContextMenu>
        ),
        renderCrumbActions: ({ crumb }) => (
          <CrumbActions
            capabilities={capabilities}
            onAction={onAction}
            path={crumb.path}
            platform={platform}
          />
        )
      }
    }),
    [allEntriesTree, capabilities, onAction, platform]
  );

  if (previewMode) {
    return null;
  }

  // A file picked from a crumb's menu opens by path, the same door the tree's
  // rows use — the surface maps it back to the catalog entry it came from.
  const openEntry = (path) => {
    chrome.onOpenPath(path);
  };

  return (
    <FileNavRow
      activePath={activePath}
      crumbs={crumbs}
      onOpen={openEntry}
      source={source}
      status={<FilenameLoadStatus activity={filenameLoadActivity} />}
      trailing={
        <>
          {/*
            One toggle per panel, in declaration order with the files toggle
            last, and never any other order: the right end of this row is the
            same control whatever is open, so it is the one thing a person can
            always find in the same place — in this app and in the desktop one.
          */}
          {panels.map((panel) => (
            <PanelToggle
              active={panel.id === openPanel}
              icon={panel.icon}
              id={panel.id}
              key={panel.id}
              label={panel.label}
              onClick={() => onTogglePanel(panel.id)}
              testId={panel.content === "tree" ? "tree-toggle" : undefined}
            />
          ))}
        </>
      }
    />
  );
}
