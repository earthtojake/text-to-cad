"use client";

import { useCallback, useEffect, useState } from "react";

import CadFileView from "../file-view/CadFileView.js";
import CadWorkspaceHome from "./workbench/CadWorkspaceHome";
import CadWorkspaceTopBar from "./workbench/CadWorkspaceTopBar";
import FileViewerSidebar from "./workbench/FileViewerSidebar";
import {
  entryHasDxf,
  entryHasMesh,
  entryHasUrdf
} from "cadgen-js/lib/entryAssets";
import { entrySourceFormat } from "cadgen-js/lib/fileFormats";
import {
  normalizeCadFileQueryParam,
  readCadParam,
  sidebarLabelForEntry,
  writeCadParam
} from "@/workbench/sidebar";

// The STANDALONE app's shell, and nothing else.
//
// Everything the viewer draws for one file lives in <CadFileView>, which the
// desktop app renders too. What is left here is what only a browser tab at a
// bare origin has: the URL is where "which file is open" is written down, and
// the workspace chrome — top bar, file sidebar, home screen — is drawn into the
// surface's three slots from the `chrome` state it hands back.
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
    <CadFileView
      origin=""
      file={file}
      onOpenFile={handleOpenFile}
      catalog={{
        entries: manifestEntries,
        revision: manifestRevision,
        hydrated: catalogHydrated,
        refreshing: catalogRefreshing,
        error: catalogError
      }}
      renderTopBar={(chrome) => (
        <CadWorkspaceTopBar
          previewMode={chrome.previewMode}
          sidebarLabelForEntry={sidebarLabelForEntry}
          directoryTree={chrome.allEntriesTree}
          selectedKey={chrome.selectedKey}
          selectedEntry={chrome.selectedEntry}
          onSelectEntry={chrome.onSelectEntry}
          entrySourceFormat={entrySourceFormat}
          entryHasMesh={entryHasMesh}
          entryHasDxf={entryHasDxf}
          entryHasUrdf={entryHasUrdf}
          activeStepArtifactGenerationFile={chrome.activeStepArtifactGenerationFiles}
          loadingFiles={chrome.viewerLoadingFiles}
          stepArtifactGenerationAvailable={chrome.stepArtifactGenerationAvailable}
          filenameLoadActivity={chrome.filenameLoadActivity}
          selectedStepSourceStatus={chrome.selectedStepSourceStatus}
          canCopyFileAssetPaths={chrome.canCopyFileAssetPaths}
          onRevealInExplorerView={chrome.onRevealInExplorerView}
          onCopyFileAssetReference={chrome.onCopyFileAssetReference}
          fileSheetKind={chrome.fileSheetKind}
          fileSheetOpen={chrome.fileSheetOpen}
          onToggleFileSheet={chrome.onToggleFileSheet}
          themeEditing={chrome.themeEditing}
          onToggleThemeEditor={chrome.onToggleThemeEditor}
        />
      )}
      renderSidebar={(chrome) => (
        <FileViewerSidebar
          previewMode={chrome.previewMode}
          query={chrome.query}
          onQueryChange={chrome.onQueryChange}
          filteredEntries={chrome.filteredEntries}
          catalogEntries={chrome.catalogEntries}
          filteredEntriesTree={chrome.filteredEntriesTree}
          selectedKey={chrome.selectedKey}
          expandedDirectoryIds={chrome.expandedDirectoryIds}
          onToggleDirectory={chrome.onToggleDirectory}
          onSelectEntry={chrome.onSelectEntry}
          entrySourceFormat={entrySourceFormat}
          entryHasMesh={entryHasMesh}
          entryHasDxf={entryHasDxf}
          entryHasUrdf={entryHasUrdf}
          activeStepArtifactGenerationFile={chrome.activeStepArtifactGenerationFiles}
          loadingFiles={chrome.viewerLoadingFiles}
          stepArtifactGenerationAvailable={chrome.stepArtifactGenerationAvailable}
          canCopyFileAssetPaths={chrome.canCopyFileAssetPaths}
          onRevealInExplorerView={chrome.onRevealInExplorerView}
          onCopyFileAssetReference={chrome.onCopyFileAssetReference}
          catalogHydrated={chrome.catalogHydrated}
          catalogRefreshing={chrome.catalogRefreshing}
          catalogError={chrome.catalogError}
          resizable={chrome.sidebarResizable}
          onStartResize={chrome.onStartSidebarResize}
        />
      )}
      renderHome={(chrome) => (
        <CadWorkspaceHome
          entries={chrome.catalogEntries}
          onSelectEntry={chrome.onSelectEntry}
          catalogHydrated={chrome.catalogHydrated}
          catalogRefreshing={chrome.catalogRefreshing}
          catalogError={chrome.catalogError}
        />
      )}
    />
  );
}
