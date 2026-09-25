import { useEffect } from "react";
import { filterPreservingIdentity } from "../../../workbench/valueUtils.js";

export function useCadWorkspaceSelection({
  isAssemblyView,
  supportsPartSelection,
  assemblyPartsLoaded,
  selectedEntryHasReferences,
  setSelectedReferenceIds,
  setHoveredModelReferenceId,
  assemblyParts,
  validAssemblyPartIds,
  validHiddenPartIds,
  setSelectedPartIds,
  parseAssemblyPartReferenceSelectionId,
  setHiddenPartIds,
  setHoveredListPartId,
  setHoveredModelPartId
}) {
  useEffect(() => {
    if (isAssemblyView || selectedEntryHasReferences) {
      return;
    }
    setSelectedReferenceIds((current) => current.length ? [] : current);
    setHoveredModelReferenceId("");
  }, [
    isAssemblyView,
    selectedEntryHasReferences,
    setHoveredModelReferenceId,
    setSelectedReferenceIds
  ]);

  useEffect(() => {
    if (!assemblyPartsLoaded) {
      return;
    }
    if (!supportsPartSelection) {
      setSelectedPartIds((current) => current.length ? [] : current);
      setHiddenPartIds((current) => current.length ? [] : current);
      setHoveredListPartId("");
      setHoveredModelPartId("");
      return;
    }
    const validIds = new Set(
      (Array.isArray(validAssemblyPartIds) ? validAssemblyPartIds : assemblyParts.map((part) => part.id))
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    const validHiddenIds = new Set(
      (Array.isArray(validHiddenPartIds) ? validHiddenPartIds : [...validIds])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    // LOD changes the valid-ID containers without changing their members.
    // Replacing equal selections here causes a second workspace render and
    // rebuilds persistence callbacks, retaining earlier render contexts.
    setSelectedPartIds((current) => filterPreservingIdentity(current, (id) => validIds.has(id)));
    setSelectedReferenceIds((current) => filterPreservingIdentity(current, (id) => {
      const parsed = parseAssemblyPartReferenceSelectionId(id);
      return !parsed || validIds.has(parsed.partId);
    }));
    setHiddenPartIds((current) => filterPreservingIdentity(current, (id) => validHiddenIds.has(id)));
    setHoveredListPartId((current) => (current && !validIds.has(current) ? "" : current));
    setHoveredModelPartId((current) => (current && !validIds.has(current) ? "" : current));
    setHoveredModelReferenceId((current) => {
      const parsed = parseAssemblyPartReferenceSelectionId(current);
      return parsed && !validIds.has(parsed.partId) ? "" : current;
    });
  }, [
    assemblyParts,
    assemblyPartsLoaded,
    supportsPartSelection,
    validAssemblyPartIds,
    validHiddenPartIds,
    parseAssemblyPartReferenceSelectionId,
    setHiddenPartIds,
    setHoveredListPartId,
    setHoveredModelPartId,
    setHoveredModelReferenceId,
    setSelectedPartIds,
    setSelectedReferenceIds
  ]);
}
