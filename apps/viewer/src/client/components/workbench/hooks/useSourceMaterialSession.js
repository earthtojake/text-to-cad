// The whole per-model material editing session in one place: the overlays the
// browser tab is holding, the single undo record behind them, which parts the
// Materials panel is editing, and the sessionStorage slice. It was four regions
// of CadWorkspace that had to be kept in agreement by hand.
//
// It lives at workspace level rather than in the panel because both the
// overlays and the undo record outlive the panel: the Materials tab unmounts
// every time the user looks at Studio, and an undo record kept inside it went
// with it.
import { useCallback, useEffect, useMemo, useState } from "react";

import { fileKey } from "../../../workbench/sidebar";
import {
  sourceMaterialOverlayIsEmpty,
  sourceMaterialsPanelEnabled,
  sourceMaterialTargets
} from "../../../workbench/sourceMaterialSession";

const EMPTY_IDS = Object.freeze([]);

// An overlay belongs to the appearance it was authored against. A re-exported
// sidecar or a rebuilt bare STEP is a different model at the same path, so the
// signature travels with the overlay and a mismatch silently drops it.
export function sourceAppearanceKeyForEntry(entry) {
  const appearance = entry?.editingPreview ? entry.previewAppearance : entry?.sourceSidecar?.appearance;
  if (!appearance) return String(entry?.documentHash || entry?.hash || "").trim();
  return String(entry?.appearanceHash || entry?.documentHash || entry?.hash || "").trim();
}

function storeOverlay(current, key, signature, overlay) {
  if (!key) return current;
  if (sourceMaterialOverlayIsEmpty(overlay)) {
    if (!current[key]) return current;
    const next = { ...current };
    delete next[key];
    return next;
  }
  return { ...current, [key]: { signature, overlay } };
}

export function useSourceMaterialSession(selectedEntry, selectedMeshData, {
  appearance = null,
  fileSheetKind = "",
  renderEnabled = false
} = {}) {
  // Per-model Render material edits live only for this Viewer session. The
  // package and the authored source sidecar remain immutable.
  const [overlayByFile, setOverlayByFile] = useState({});
  const [undoRecord, setUndoRecord] = useState(null);
  const [selection, setSelection] = useState(null);

  const scope = selectedEntry ? fileKey(selectedEntry) : "";
  const appearanceKey = sourceAppearanceKeyForEntry(selectedEntry);
  const stored = scope ? overlayByFile[scope] || null : null;
  const overlay = stored?.signature === appearanceKey ? stored.overlay : null;

  const targets = useMemo(
    () => sourceMaterialTargets(selectedMeshData, scope),
    [scope, selectedMeshData]
  );

  useEffect(() => {
    if (!renderEnabled) setSelection(null);
  }, [renderEnabled]);

  // One step of history, and only while it is still the change on screen:
  // switching model or editing again replaces it, and any other write to the
  // overlay makes it stale (undo.after stops matching) rather than wrong.
  const undo = undoRecord && undoRecord.scope === scope && undoRecord.after === overlay
    ? undoRecord
    : null;

  const change = useCallback((nextOverlay) => {
    if (!scope) return;
    setUndoRecord({ before: overlay, after: nextOverlay, scope });
    setOverlayByFile((current) => storeOverlay(current, scope, appearanceKey, nextOverlay));
  }, [appearanceKey, overlay, scope]);

  const undoLast = useCallback(() => {
    if (!undo) return;
    setUndoRecord(null);
    setOverlayByFile((current) => storeOverlay(current, undo.scope, appearanceKey, undo.before));
  }, [appearanceKey, undo]);

  const reset = useCallback(() => change(null), [change]);

  // Leaving the served directory behind: every model's overlay goes with it,
  // and so does the history and the selection that pointed into it.
  const clearAll = useCallback(() => {
    setOverlayByFile({});
    setUndoRecord(null);
    setSelection(null);
  }, []);

  const snapshotSlice = useCallback((entry) => {
    const key = entry ? fileKey(entry) : "";
    const record = key ? overlayByFile[key] || null : null;
    return record?.signature === sourceAppearanceKeyForEntry(entry) ? record.overlay : null;
  }, [overlayByFile]);

  const restoreSlice = useCallback((key, entry, slice) => {
    setOverlayByFile((current) => storeOverlay(current, key, sourceAppearanceKeyForEntry(entry), slice || null));
  }, []);

  // Selection is the one part of the session the workspace cannot hand over
  // whole: until the panel has a selection of its own, the parts being edited
  // are the ones carried in from Inspect, and that list is derived far below
  // this call. Bind it where it is known; everything else is already resolved.
  const withViewerSelection = useCallback((viewerSelectedPartIds = EMPTY_IDS) => {
    const selectedIds = selection?.scope === scope ? selection.ids : viewerSelectedPartIds;
    const select = (ids) => setSelection({ scope, ids });
    return {
      selectedIds,
      select,
      activate: (id, { multiSelect = false } = {}) => {
        const known = targets.some((target) => !target.group && target.occurrenceIds.includes(id));
        if (!known) {
          if (!multiSelect) select(EMPTY_IDS);
          return;
        }
        if (!multiSelect) {
          select([id]);
          return;
        }
        select(selectedIds.includes(id)
          ? selectedIds.filter((value) => value !== id)
          : [...selectedIds, id]);
      }
    };
  }, [scope, selection, targets]);

  const viewerless = withViewerSelection(EMPTY_IDS);

  return {
    scope,
    enabled: sourceMaterialsPanelEnabled(fileSheetKind, appearance),
    overlay,
    undo,
    targets,
    selectedIds: viewerless.selectedIds,
    select: viewerless.select,
    activate: viewerless.activate,
    withViewerSelection,
    change,
    undoLast,
    reset,
    clearAll,
    snapshotSlice,
    restoreSlice
  };
}
