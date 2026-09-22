import { useCallback, useMemo, useState } from 'react';
import { STEP_MODEL_ROOT_ID } from '@hardcore/core/lib/step/stepTree.js';
import { buildIssuesSection } from './FileStatusSection.js';
import { buildPositionSection } from './MotionControlsSection.js';
import { StepReferenceSection } from './StepReferenceSection.js';
import ModelingTree from './ModelingTree.jsx';
import { useStepModeling } from '../../workbench/useStepModeling.js';
import { stepGeometryMeasurements } from '../../workbench/stepGeometryMeasurements.js';
const EMPTY = [];

/**
 * A STEP's own panel: its Features tree, its Position when it has joints to drive, and its
 * Issues when there are any — sections stacked in one column, named for what the file is (a
 * part, an assembly). A file with no joints and no issues is its Features alone. The sheet
 * around it, and the Display panel beside it, are the shell's (`kit/shell/RendererShell.jsx`).
 *
 * `open`: the panel is on screen, which is when recognition is worth running.
 */
export function useStepPanel({
  client, open, selectedEntry, viewerLoading,
  geometryInspection = null, stepTreeRoot, isAssemblyView = false,
  selectedMeshData = null, selectedSourceAppearance = null,
  selectedPartIds = EMPTY, selectedReferenceIds = EMPTY, selectedReferences = EMPTY,
  hiddenPartIds = EMPTY, focusedNodeIds = EMPTY, selectableNodeIds = null,
  expandedTreeNodeIds = EMPTY, onToggleTreeNode, onVisibleFeatureTargetsChange,
  activeTreeNodeScrollKey = '', onSelectTreeNode, onSelectReferenceGroup, onClearSelection,
  onFocusTreeNode, onUnfocusTreeNode, onExitAllIsolate, onTogglePartVisibility,
  onCopyTreeNodeReference, onHoverTreeNode, showAllHiddenParts,
  // The menus a tree row carries: a part's descriptor per node, a feature's per set of faces
  // and edges (the viewport's menu over that topology), and the one set of actions behind both.
  menuForNode = null, menuForReferences = null, partMenuActions = null,
  treeSelectionDisabled = false,
  stepModule = null, stepAnimation = null, statusItems = EMPTY,
}) {
  const recognitionKey = `${selectedEntry?.file}:${geometryInspection?.revision}`;
  const [recognitionRequest, setRecognitionRequest] = useState({ key: recognitionKey, ids: EMPTY });
  const requestedOccurrenceIds = recognitionRequest.key === recognitionKey ? recognitionRequest.ids : EMPTY;
  const onRequestRecognition = useCallback((ids) => setRecognitionRequest(current => (
    current.key === recognitionKey && current.ids.length === ids.length && current.ids.every((id, index) => id === ids[index])
      ? current : { key: recognitionKey, ids }
  )), [recognitionKey]);
  const modeling = useStepModeling(selectedEntry, open && !treeSelectionDisabled && !viewerLoading, { client, requestedOccurrenceIds });
  const modelReferences = geometryInspection?.references || EMPTY;
  const modelParts = geometryInspection?.parts || EMPTY;
  const measuredSelection = useMemo(() => ({
    faceIds: selectedReferences.filter(ref => ref.selectorType === 'face').map(ref => ref.id),
    partIds: [...new Set([
      ...(selectedPartIds || []).flatMap(id => id === STEP_MODEL_ROOT_ID ? modelParts.map(part => part.id) : modelParts.some(part => part.id === id) ? [id] : []),
      ...selectedReferences.filter(ref => ref.selectorType === 'occurrence' && modelParts.some(part => part.id === ref.id)).map(ref => ref.id),
    ])],
  }), [selectedReferences, selectedPartIds, modelParts]);
  const measurements = useMemo(() => stepGeometryMeasurements(measuredSelection, modelReferences, modelParts), [measuredSelection, modelReferences, modelParts]);
  if (!selectedEntry) return null;
  const selectionDetails = selectedReferences.length || measuredSelection.partIds.length ? <StepReferenceSection
    references={selectedReferences} meshData={selectedMeshData} sourceAppearance={selectedSourceAppearance} measurements={measurements}
  /> : null;
  const sections = [{
    id: 'features', title: 'Features',
    content: active => <ModelingTree key={`${selectedEntry.file}:${geometryInspection?.revision}`}
      modeling={modeling} stepRoot={stepTreeRoot} active={active && open}
      onRequestRecognition={onRequestRecognition} onVisibleFeatureTargetsChange={onVisibleFeatureTargetsChange}
      disabled={treeSelectionDisabled || viewerLoading}
      references={modelReferences} selectedReferences={selectedReferences}
      selectedReferenceIds={selectedReferenceIds} selectedPartIds={selectedPartIds}
      selectionDetails={selectionDetails} activeTreeNodeScrollKey={activeTreeNodeScrollKey}
      onLoadTopology={geometryInspection?.onLoadTopology} onSelect={onSelectReferenceGroup} onClearSelection={onClearSelection}
      partControls={{isAssemblyView, hiddenPartIds, focusedNodeIds, selectableNodeIds, expandedTreeNodeIds, onToggleTreeNode,
        onSelectTreeNode, onFocusTreeNode, onUnfocusTreeNode, onExitAllIsolate,
        onTogglePartVisibility, showAllHiddenParts, onCopyTreeNodeReference, onHoverTreeNode,
        menuForNode, menuForReferences, partMenuActions}}
    />,
  }, buildPositionSection({
    poseRuntime: stepModule, animationRuntime: stepAnimation,
    poseProps: { loadingLabel: 'Loading kinematics...', noParametersLabel: 'No pose controls.' },
  }), buildIssuesSection(statusItems)].filter(Boolean);
  return { title: isAssemblyView ? 'Assembly' : 'Part', sections };
}
