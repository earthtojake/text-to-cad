import { useMemo } from "react";
import { buildAssemblyPartMap, buildReferenceMap } from "../../../workbench/selectors.js";

// ONE shared empty list, never a fresh `[]` per render. Everything the workspace tells the
// viewport about parts and references hangs off the two lists below, so a new identity
// carrying the same contents re-ran the whole chain — the reference maps, the render-part id
// lists, every viewport layer keyed on one of them — on a render that changed nothing. The
// viewport held that back with a comparison of its own (`StepViewport`'s `useStableIds`),
// which left a memo load-bearing for how much work happens rather than merely for its speed.
const EMPTY_REFERENCES = Object.freeze([]);

export function useCadWorkspaceSelectors({
  selectedReferencesMatch,
  referenceState,
  supportsPartSelection,
  assemblyParts,
  assemblyPartMap,
  selectedReferenceIds,
  selectedPartIds,
  hoveredModelReferenceId,
  hoveredListPartId,
  hoveredModelPartId
}) {
  const loadedReferences = referenceState?.references;
  const currentReferences = useMemo(
    () => (selectedReferencesMatch && Array.isArray(loadedReferences) ? loadedReferences : EMPTY_REFERENCES),
    [selectedReferencesMatch, loadedReferences]
  );
  const normalizedAssemblyParts = useMemo(
    () => (supportsPartSelection && Array.isArray(assemblyParts) ? assemblyParts : EMPTY_REFERENCES),
    [assemblyParts, supportsPartSelection]
  );
  const normalizedAssemblyPartMap = useMemo(
    () => (assemblyPartMap instanceof Map ? assemblyPartMap : buildAssemblyPartMap(normalizedAssemblyParts)),
    [assemblyPartMap, normalizedAssemblyParts]
  );
  const activeReferenceMap = useMemo(() => buildReferenceMap(currentReferences), [currentReferences]);

  const selectedReferences = useMemo(
    () => selectedReferenceIds.map((id) => activeReferenceMap.get(id)).filter(Boolean),
    [activeReferenceMap, selectedReferenceIds]
  );
  const selectedParts = useMemo(
    () => selectedPartIds.map((id) => normalizedAssemblyPartMap.get(id)).filter(Boolean),
    [normalizedAssemblyPartMap, selectedPartIds]
  );

  return {
    currentReferences,
    activeReferenceMap,
    selectedReferences,
    selectedParts,
    hoveredReferenceId: hoveredModelReferenceId || "",
    hoveredPartId: hoveredListPartId || hoveredModelPartId || ""
  };
}
