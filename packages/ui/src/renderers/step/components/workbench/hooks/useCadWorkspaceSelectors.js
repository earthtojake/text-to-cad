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
  isAssemblyView,
  supportsPartSelection,
  assemblyParts,
  assemblyPartMap,
  inspectedAssemblyNodeId,
  inspectedAssemblyPartTopologyReferences,
  selectedReferenceIds,
  selectedPartIds,
  hoveredListReferenceId,
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

  const inspectedAssemblyPartId = String(inspectedAssemblyNodeId || "").trim();
  const inspectedAssemblyPartIds = useMemo(
    () => (inspectedAssemblyPartId ? [inspectedAssemblyPartId] : EMPTY_REFERENCES),
    [inspectedAssemblyPartId]
  );
  const inspectedAssemblyPart = useMemo(
    () => (inspectedAssemblyPartId ? normalizedAssemblyPartMap.get(inspectedAssemblyPartId) || null : null),
    [inspectedAssemblyPartId, normalizedAssemblyPartMap]
  );

  const referenceMap = useMemo(() => buildReferenceMap(currentReferences), [currentReferences]);

  const isInspectingAssemblyPart =
    isAssemblyView &&
    Boolean(inspectedAssemblyPartId) &&
    String(inspectedAssemblyPart?.nodeType || "").trim() === "part" &&
    !(Array.isArray(inspectedAssemblyPart?.children) && inspectedAssemblyPart.children.length > 0);
  const inspectedAssemblyPartReferences = useMemo(
    () => (Array.isArray(inspectedAssemblyPartTopologyReferences) && inspectedAssemblyPartTopologyReferences.length
      ? inspectedAssemblyPartTopologyReferences : EMPTY_REFERENCES),
    [inspectedAssemblyPartTopologyReferences]
  );

  const activeReferenceMap = useMemo(() => {
    return buildReferenceMap(isInspectingAssemblyPart ? inspectedAssemblyPartReferences : currentReferences);
  }, [currentReferences, inspectedAssemblyPartReferences, isInspectingAssemblyPart]);

  const inspectedAssemblyPartSourceLabel = String(
    inspectedAssemblyPart?.name ||
    inspectedAssemblyPart?.displayName ||
    "the selected part"
  ).trim();

  const selectedReferences = useMemo(
    () => selectedReferenceIds.map((id) => activeReferenceMap.get(id)).filter(Boolean),
    [activeReferenceMap, selectedReferenceIds]
  );
  const selectedParts = useMemo(
    () => selectedPartIds.map((id) => normalizedAssemblyPartMap.get(id)).filter(Boolean),
    [normalizedAssemblyPartMap, selectedPartIds]
  );

  const hoveredReferenceId = hoveredListReferenceId || hoveredModelReferenceId;
  const hoveredReference = hoveredReferenceId ? activeReferenceMap.get(hoveredReferenceId) || null : null;
  const hoveredPartId = hoveredListPartId || hoveredModelPartId || "";

  return {
    currentReferences,
    assemblyParts: normalizedAssemblyParts,
    assemblyPartMap: normalizedAssemblyPartMap,
    inspectedAssemblyPartIds,
    inspectedAssemblyPartId,
    inspectedAssemblyPart,
    allReferences: currentReferences,
    mixedReferenceList: currentReferences,
    referenceMap,
    isInspectingAssemblyPart,
    activeReferenceMap,
    inspectedAssemblyPartReferences,
    inspectedAssemblyPartSourceLabel,
    selectedReferences,
    selectedParts,
    hoveredReferenceId,
    hoveredReference,
    hoveredPartId,
    visibleReferences: isInspectingAssemblyPart ? inspectedAssemblyPartReferences : currentReferences,
    filteredReferences: isInspectingAssemblyPart ? inspectedAssemblyPartReferences : currentReferences,
    filteredAssemblyParts: normalizedAssemblyParts
  };
}
