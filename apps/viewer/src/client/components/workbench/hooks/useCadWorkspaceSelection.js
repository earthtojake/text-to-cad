import { useEffect } from "react";

export function useCadWorkspaceSelection({
  isAssemblyView,
  supportsPartSelection,
  assemblyPartsLoaded,
  selectedEntryHasReferences,
  setSelectedReferenceIds,
  selectedReferenceIdsRef,
  setHoveredListReferenceId,
  setHoveredModelReferenceId,
  assemblyParts,
  validAssemblyPartIds,
  validHiddenPartIds,
  selectedPartIdsRef,
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
    selectedReferenceIdsRef.current = [];
    setSelectedReferenceIds([]);
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
  }, [
    isAssemblyView,
    selectedEntryHasReferences,
    selectedReferenceIdsRef,
    setHoveredListReferenceId,
    setHoveredModelReferenceId,
    setSelectedReferenceIds
  ]);

  useEffect(() => {
    if (!assemblyPartsLoaded) {
      return;
    }
    if (!supportsPartSelection) {
      selectedPartIdsRef.current = [];
      setSelectedPartIds([]);
      setHiddenPartIds([]);
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
    selectedPartIdsRef.current = selectedPartIdsRef.current.filter((id) => validIds.has(id));
    setSelectedPartIds((current) => current.filter((id) => validIds.has(id)));
    selectedReferenceIdsRef.current = selectedReferenceIdsRef.current.filter((id) => {
      const parsed = parseAssemblyPartReferenceSelectionId(id);
      return !parsed || validIds.has(parsed.partId);
    });
    setSelectedReferenceIds((current) => current.filter((id) => {
      const parsed = parseAssemblyPartReferenceSelectionId(id);
      return !parsed || validIds.has(parsed.partId);
    }));
    setHiddenPartIds((current) => current.filter((id) => validHiddenIds.has(id)));
    setHoveredListPartId((current) => (current && !validIds.has(current) ? "" : current));
    setHoveredModelPartId((current) => (current && !validIds.has(current) ? "" : current));
    setHoveredListReferenceId((current) => {
      const parsed = parseAssemblyPartReferenceSelectionId(current);
      return parsed && !validIds.has(parsed.partId) ? "" : current;
    });
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
    selectedReferenceIdsRef,
    selectedPartIdsRef,
    setHiddenPartIds,
    setHoveredListPartId,
    setHoveredListReferenceId,
    setHoveredModelPartId,
    setHoveredModelReferenceId,
    setSelectedPartIds,
    setSelectedReferenceIds
  ]);
}
