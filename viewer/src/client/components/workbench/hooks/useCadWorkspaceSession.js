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

export function useCadWorkspaceSession({
  manifestEntries,
  cadFileParamForEntry = () => "",
  cadWorkspaceSessionBootstrappedRef,
  setOpenTabs,
  applyTabRecord,
  selectedEntryKeyFromUrl,
  createTabRecord,
  initialSelectedTabSnapshot = null,
  upsertTabRecord,
  selectedEntry,
  defaultDocumentTitle,
  selectedKey,
  entryMap,
  buildActiveTabSnapshot,
  catalogEntries,
  manifestRevision = 0,
  readCadParam = () => null,
  readCadRefQueryParams = () => [],
  setPendingCadRefQueryParams = () => {},
  activateEntryTab,
  resetActiveWorkspace,
  writeCadParam,
  readEntrySessionState = () => null,
  applyEntrySessionState = () => {}
}) {
  const initialManifestRevisionRef = useRef(manifestRevision);
  const initialUnresolvedUrlSelectionRef = useRef(false);

  useLayoutEffect(() => {
    if (cadWorkspaceSessionBootstrappedRef.current) {
      return;
    }
    cadWorkspaceSessionBootstrappedRef.current = true;

    const initialCadRefQueryParams = readCadRefQueryParams();
    if (initialCadRefQueryParams.length) {
      setPendingCadRefQueryParams(initialCadRefQueryParams);
    }
    const urlSelectedKey = selectedEntryKeyFromUrl(manifestEntries);
    initialUnresolvedUrlSelectionRef.current = Boolean(readCadParam() || initialCadRefQueryParams.length) && !urlSelectedKey;

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
    readCadRefQueryParams,
    readCadParam,
    readEntrySessionState,
    selectedEntryKeyFromUrl,
    setOpenTabs,
    setPendingCadRefQueryParams,
    upsertTabRecord,
    initialSelectedTabSnapshot,
    cadWorkspaceSessionBootstrappedRef
  ]);

  useEffect(() => {
    const filename = filenameLabelForEntry(selectedEntry);
    document.title = filename ? `${defaultDocumentTitle} | ${filename}` : defaultDocumentTitle;
  }, [defaultDocumentTitle, selectedEntry]);

  useLayoutEffect(() => {
    const urlSelectionRequested = Boolean(readCadParam() || readCadRefQueryParams().length);
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
        resetActiveWorkspace();
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
    readCadRefQueryParams,
    resetActiveWorkspace,
    selectedEntryKeyFromUrl,
    selectedKey,
    setOpenTabs,
    upsertTabRecord
  ]);

  useEffect(() => {
    const syncSelectionFromHistory = () => {
      const nextCadRefQueryParams = readCadRefQueryParams();
      setPendingCadRefQueryParams(nextCadRefQueryParams);

      const nextSelectedKey = selectedEntryKeyFromUrl(catalogEntries);
      if (nextSelectedKey) {
        activateEntryTab(nextSelectedKey);
        return;
      }
      resetActiveWorkspace();
    };

    window.addEventListener("popstate", syncSelectionFromHistory);
    return () => {
      window.removeEventListener("popstate", syncSelectionFromHistory);
    };
  }, [
    activateEntryTab,
    catalogEntries,
    readCadRefQueryParams,
    resetActiveWorkspace,
    selectedEntryKeyFromUrl,
    setPendingCadRefQueryParams
  ]);

  useEffect(() => {
    if (selectedEntry) {
      writeCadParam(cadFileParamForEntry(selectedEntry));
      return;
    }
    if (!selectedKey) {
      const unresolvedUrlSelection = Boolean(readCadParam() || readCadRefQueryParams().length);
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
    readCadRefQueryParams,
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
