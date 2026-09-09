import { useEffect, useLayoutEffect, useRef } from "react";

import { filenameLabelForEntry } from "../../../workbench/sidebar.js";

export function shouldActivateUrlSelection({
  selectedKey = "",
  selectedKeyExists = false,
  urlSelectionRequested = false,
  nextSelectedKey = ""
} = {}) {
  if (!urlSelectionRequested || !nextSelectedKey || nextSelectedKey === selectedKey) {
    return false;
  }
  return true;
}

export function createSessionBackedTabRecord({
  key = "",
  createTabRecord,
  initialSelectedTabSnapshot = null,
  fileSessionState = null
} = {}) {
  const restoredTabSnapshot = fileSessionState?.slices?.tab || null;
  return createTabRecord(key, restoredTabSnapshot || initialSelectedTabSnapshot || {});
}

export function useCadDirectorySession({
  manifestEntries,
  cadFileParamForEntry = () => "",
  cadDirectorySessionBootstrappedRef,
  setOpenTabs,
  applyTabRecord,
  selectedEntryKeyFromUrl,
  createTabRecord,
  initialSelectedTabSnapshot = null,
  upsertTabRecord,
  selectedEntry,
  defaultDocumentTitle,
  manageDocumentTitle = true,
  selectedKey,
  entryMap,
  buildActiveTabSnapshot,
  catalogEntries,
  manifestRevision = 0,
  readCadParam = () => null,
  activateEntryTab,
  resetActiveDirectory,
  writeCadParam,
  readEntrySessionState = () => null,
  applyEntrySessionState = () => {}
}) {
  const initialManifestRevisionRef = useRef(manifestRevision);
  const initialUnresolvedUrlSelectionRef = useRef(false);

  useLayoutEffect(() => {
    if (cadDirectorySessionBootstrappedRef.current) {
      return;
    }
    cadDirectorySessionBootstrappedRef.current = true;

    const urlSelectedKey = selectedEntryKeyFromUrl(manifestEntries);
    initialUnresolvedUrlSelectionRef.current = Boolean(readCadParam()) && !urlSelectedKey;

    if (urlSelectedKey) {
      const fileSessionState = readEntrySessionState(urlSelectedKey);
      const nextTab = createSessionBackedTabRecord({
        key: urlSelectedKey,
        createTabRecord,
        initialSelectedTabSnapshot,
        fileSessionState
      });
      setOpenTabs((current) => upsertTabRecord(current, urlSelectedKey, nextTab));
      applyTabRecord(nextTab);
      applyEntrySessionState(urlSelectedKey, fileSessionState);
    }
  }, [
    applyEntrySessionState,
    applyTabRecord,
    createTabRecord,
    manifestEntries,
    readCadParam,
    readEntrySessionState,
    selectedEntryKeyFromUrl,
    setOpenTabs,
    upsertTabRecord,
    initialSelectedTabSnapshot,
    cadDirectorySessionBootstrappedRef
  ]);

  // The browser tab's name belongs to whoever owns the tab. The standalone app
  // does; a host that embeds the surface in one pane of its own window does not,
  // and says so with manageDocumentTitle={false}.
  useEffect(() => {
    if (!manageDocumentTitle) {
      return;
    }
    const filename = filenameLabelForEntry(selectedEntry);
    document.title = filename ? `${defaultDocumentTitle} | ${filename}` : defaultDocumentTitle;
  }, [defaultDocumentTitle, manageDocumentTitle, selectedEntry]);

  useLayoutEffect(() => {
    const urlSelectionRequested = Boolean(readCadParam());
    const nextSelectedKey = selectedEntryKeyFromUrl(catalogEntries);
    const selectedKeyExists = Boolean(selectedKey && entryMap.has(selectedKey));

    if (shouldActivateUrlSelection({
      selectedKey,
      selectedKeyExists,
      urlSelectionRequested,
      nextSelectedKey
    })) {
      initialUnresolvedUrlSelectionRef.current = false;
      activateEntryTab(nextSelectedKey);
      return;
    }

    if (selectedKeyExists) {
      setOpenTabs((current) => upsertTabRecord(current, selectedKey, buildActiveTabSnapshot()));
      return;
    }

    if (!nextSelectedKey) {
      if (selectedKey) {
        if (manifestRevision === initialManifestRevisionRef.current && !entryMap.size) {
          return;
        }
        resetActiveDirectory();
      }
      return;
    }

    if (nextSelectedKey !== selectedKey) {
      activateEntryTab(nextSelectedKey);
    }
  }, [
    activateEntryTab,
    buildActiveTabSnapshot,
    catalogEntries,
    entryMap,
    manifestRevision,
    readCadParam,
    resetActiveDirectory,
    selectedEntryKeyFromUrl,
    selectedKey,
    setOpenTabs,
    upsertTabRecord
  ]);

  // Back/forward used to be handled here, with a popstate listener of its own.
  // It is the HOST's now: the file surface is told which file to show, so the
  // shell that owns the URL turns a popstate into a new `file`, which changes
  // `readCadParam`/`selectedEntryKeyFromUrl` and re-runs the reconciliation
  // above. One path in, instead of two racing on the same event.

  useEffect(() => {
    if (selectedEntry) {
      writeCadParam(cadFileParamForEntry(selectedEntry));
      return;
    }
    if (!selectedKey) {
      const unresolvedUrlSelection = Boolean(readCadParam());
      if (unresolvedUrlSelection) {
        const urlSelectedKey = selectedEntryKeyFromUrl(catalogEntries);
        if (
          urlSelectedKey ||
          readCadParam() ||
          (
            initialUnresolvedUrlSelectionRef.current &&
            (manifestRevision === initialManifestRevisionRef.current || !entryMap.size)
          )
        ) {
          return;
        }
      }
      writeCadParam("");
    }
  }, [
    catalogEntries,
    cadFileParamForEntry,
    manifestRevision,
    readCadParam,
    selectedEntry,
    selectedEntryKeyFromUrl,
    selectedKey,
    writeCadParam
  ]);

  useEffect(() => {
    if (!selectedKey) {
      return;
    }
    setOpenTabs((current) => upsertTabRecord(current, selectedKey, buildActiveTabSnapshot()));
  }, [buildActiveTabSnapshot, selectedKey, setOpenTabs, upsertTabRecord]);
}
