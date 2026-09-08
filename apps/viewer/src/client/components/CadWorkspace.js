"use client";

import { useCallback, useEffect, useState } from "react";

import CadFileView from "../file-view/CadFileView.js";
import CadWorkspaceTopBar from "./workbench/CadWorkspaceTopBar";
import ViewerTopBar from "./workbench/ViewerTopBar";
import { FilePanelColumn, FileTree, useCatalogTreeSource } from "@/shell/index.js";
import {
  cadFileParamForEntry,
  normalizeCadFileQueryParam,
  readCadParam,
  writeCadParam
} from "@/workbench/sidebar";

import { useStandaloneEntryActions, webEntryCapabilities } from "./workbench/standaloneEntryActions.js";
import { useWorkspacePanels } from "./workbench/workspacePanels.js";

// The STANDALONE app's shell, and nothing else.
//
// Everything the viewer draws for one file lives in <CadFileView>, which the
// desktop app renders too, and everything AROUND that file — the nav row, the
// breadcrumb, the entry menus, the panel column and the file tree in it — is
// `cad-viewer/shell`, which the desktop app draws too. The two are one file
// explorer. What is left here is the standalone's own half: the URL is where
// "which file is open" is written down, and the panel column is assembled from
// the surface's state and handed back through the surface's two slots.
//
// The one visible difference from the desktop app's file tab is the Discord,
// GitHub and version buttons at the right end of the nav row. Everything a
// browser tab cannot honestly do — open with, reveal, rename, duplicate,
// trash, new file, terminal — is absent as a capability rather than present
// and broken (`shell/entry-menu.js`).
export default function CadWorkspace({
  manifestEntries = [],
  manifestRevision = 0,
  catalogHydrated = false,
  catalogRefreshing = false,
  catalogError = "",
}) {
  // `?file=` IS the selection for this app: the surface is told which file to
  // show and asks for another by calling back here, and the two stay in step
  // through this one piece of state. Back/forward is the same conversation.
  const [file, setFile] = useState(() => readCadParam() || "");
  /**
   * The box the surface draws its own panels into. State rather than a ref,
   * because the surface has to be TOLD when it attaches: given one it portals
   * the theme editor and the Inspector there and draws no column of its own,
   * so this app's file tree and the surface's two panels share one frame.
   */
  const [panelSlot, setPanelSlot] = useState(null);

  useEffect(() => {
    const syncFromHistory = () => {
      setFile(readCadParam() || "");
    };
    window.addEventListener("popstate", syncFromHistory);
    return () => {
      window.removeEventListener("popstate", syncFromHistory);
    };
  }, []);

  const handleOpenFile = useCallback((path, { history = "replace" } = {}) => {
    writeCadParam(path, { history });
    setFile(normalizeCadFileQueryParam(path) || "");
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ViewerTopBar />
      <div className="min-h-0 flex-1">
        <CadFileView
          origin=""
          file={file}
          onOpenFile={handleOpenFile}
          panelSlot={panelSlot}
          catalog={{
            entries: manifestEntries,
            revision: manifestRevision,
            hydrated: catalogHydrated,
            refreshing: catalogRefreshing,
            error: catalogError
          }}
          renderTopBar={(chrome) => <CadWorkspaceTopBar chrome={chrome} />}
          renderPanel={(chrome) => (
            <WorkspacePanelColumn
              chrome={chrome}
              manifestRevision={manifestRevision}
              onSlotChange={setPanelSlot}
            />
          )}
        />
      </div>
    </div>
  );
}

/**
 * The panel column, and what is in it.
 *
 * One column with one width and one open panel, exactly as the desktop app's
 * file tab has: the shared `FilePanelColumn` frame, the shared panel list with
 * the file tree appended last, and either the shared `FileTree` or the box the
 * surface portals its own panels into. A closed panel is not rendered at all,
 * so the toggle for it exists in the document exactly once — in the nav row.
 */
function WorkspacePanelColumn({ chrome, manifestRevision, onSlotChange }) {
  const panels = useWorkspacePanels(chrome);
  const openPanel = panels.find((entry) => entry.id === chrome.openPanel) ?? null;
  const treeSource = useWorkspaceTreeSource(chrome, manifestRevision);

  if (chrome.previewMode || !openPanel) {
    return null;
  }

  return (
    <FilePanelColumn
      id={openPanel.id}
      label={openPanel.label}
      onWidthChange={chrome.onPanelWidthChange}
      width={chrome.panelWidth}
    >
      {openPanel.content === "tree" ? (
        <FileTree
          activePath={chrome.selectedEntry ? cadFileParamForEntry(chrome.selectedEntry) : null}
          onOpen={chrome.onOpenPath}
          source={treeSource}
        />
      ) : (
        <div className="h-full min-h-0" ref={onSlotChange} />
      )}
    </FilePanelColumn>
  );
}

/** The tree's source: the catalog, walked in place (`shell/catalogTreeSource.js`). */
function useWorkspaceTreeSource(chrome, manifestRevision) {
  const { platform, onAction } = useStandaloneEntryActions(chrome);
  return useCatalogTreeSource({
    capabilities: webEntryCapabilities(chrome.canCopyFileAssetPaths),
    directoryTree: chrome.allEntriesTree,
    expanded: chrome.treeExpanded,
    onAction,
    platform,
    revision: manifestRevision,
    rootName: "This directory",
    setExpanded: chrome.onTreeExpandedChange
  });
}
