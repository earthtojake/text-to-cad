import { useCallback, useMemo, useState } from 'react';
import { buildPositionSection } from './MotionControlsSection.js';
import { STEP_MODEL_ROOT_ID } from '@hardcore/core/lib/step/stepTree.js';
import { buildIssuesSection } from './FileStatusSection.js';
import { useStepReference } from './StepReferenceSection.js';
import ModelingTree from './ModelingTree.jsx';
import ToolPanel from '../../../kit/tools/ToolPanel.jsx';
import { useStepModeling } from '../../workbench/useStepModeling.js';
import { stepGeometryMeasurements } from '../../workbench/stepGeometryMeasurements.js';
const EMPTY = [];

/**
 * A STEP's panels in the tool stack, top to bottom: while Select is the tool, **Features** (the
 * filter and the model tree), the **Reference** for what is selected, and **Issues** when there
 * are any; while Position is the tool, **Position**. Each stays mounted while its tool is not
 * up, so the tree keeps its expansion, filter and scroll. The kept effects' panels follow them
 * (`ModelTools.jsx`); the stack itself is the shell's (`kit/shell/RendererShell.jsx`).
 *
 * `selectActive`: Features is on screen, which is when recognition is worth running and a pick
 * is scrolled to. `selectMode` is the Select tool's mode, which the tree's disclosure follows.
 */
export function useStepPanels({
  client, selectActive, positionActive, selectedEntry, viewerLoading,
  geometryInspection = null, stepTreeRoot, isAssemblyView = false,
  selectedMeshData = null, selectedSourceAppearance = null,
  selectedPartIds = EMPTY, selectedReferenceIds = EMPTY, selectedReferences = EMPTY,
  hiddenPartIds = EMPTY, focusedNodeIds = EMPTY, selectableNodeIds = null,
  expandedTreeNodeIds = EMPTY, onToggleTreeNode,
  activeTreeNodeScrollKey = '', onSelectTreeNode, onSelectReferenceGroup, onClearSelection,
  onFocusTreeNode, onUnfocusTreeNode, onExitAllIsolate, onTogglePartVisibility,
  onCopySelection, onCopyTreeNodeReference, onHoverTreeNode, showAllHiddenParts,
  // The menus a tree row carries: a part's descriptor per node, a feature's per set of faces
  // and edges (the viewport's menu over that topology), and the one set of actions behind both.
  menuForNode = null, menuForReferences = null, partMenuActions = null,
  treeSelectionDisabled = false, selectMode = 'all', loadingGeometry = false,
  statusItems = EMPTY, positionRuntime = null,
}) {
  const recognitionKey = `${selectedEntry?.file}:${geometryInspection?.revision}`;
  const [recognitionRequest, setRecognitionRequest] = useState({ key: recognitionKey, ids: EMPTY });
  const requestedOccurrenceIds = recognitionRequest.key === recognitionKey ? recognitionRequest.ids : EMPTY;
  const onRequestRecognition = useCallback((ids) => setRecognitionRequest(current => (
    current.key === recognitionKey && current.ids.length === ids.length && current.ids.every((id, index) => id === ids[index])
      ? current : { key: recognitionKey, ids }
  )), [recognitionKey]);
  const modeling = useStepModeling(selectedEntry, selectActive && !treeSelectionDisabled && !viewerLoading, { client, requestedOccurrenceIds });
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
  // A face or edge is named after its part as the tree names that part.
  const partNames = useMemo(() => {
    const names = new Map();
    const visit = node => { if (!node) return; if (node.id) names.set(String(node.id), String(node.displayName || node.name || '').trim()); (node.children || EMPTY).forEach(visit); };
    visit(stepTreeRoot);
    return names;
  }, [stepTreeRoot]);
  const partName = useCallback(id => partNames.get(String(id || '')) || '', [partNames]);
  const reference = useStepReference({ references: selectedReferences, meshData: selectedMeshData, sourceAppearance: selectedSourceAppearance, measurements, partName });
  if (!selectedEntry) return null;
  const selectionDetails = selectedReferences.length || measuredSelection.partIds.length ? reference : null;
  const position = buildPositionSection({ poseRuntime: positionRuntime });
  const issues = buildIssuesSection(statusItems);
  return <>
    {/* Features, then the Reference for a selection: both the tree's, which knows what is picked in it. */}
    <ModelingTree key={`${selectedEntry.file}:${geometryInspection?.revision}`}
      modeling={modeling} stepRoot={stepTreeRoot} active={selectActive} mode={selectMode} loading={loadingGeometry}
      onRequestRecognition={onRequestRecognition}
      disabled={treeSelectionDisabled || viewerLoading}
      references={modelReferences} selectedReferences={selectedReferences}
      selectedReferenceIds={selectedReferenceIds} selectedPartIds={selectedPartIds}
      selectionDetails={selectionDetails} activeTreeNodeScrollKey={activeTreeNodeScrollKey}
      onLoadTopology={geometryInspection?.onLoadTopology} onSelect={onSelectReferenceGroup} onClearSelection={onClearSelection}
      partControls={{isAssemblyView, hiddenPartIds, focusedNodeIds, selectableNodeIds, expandedTreeNodeIds, onToggleTreeNode,
        onSelectTreeNode, onFocusTreeNode, onUnfocusTreeNode, onExitAllIsolate,
        onTogglePartVisibility, showAllHiddenParts, onCopySelection, onCopyTreeNodeReference, onHoverTreeNode,
        menuForNode, menuForReferences, partMenuActions}}
    />
    {issues ? <ToolPanel title={issues.title} label="Issues" fit="details" collapsible hidden={!selectActive}>{issues.content}</ToolPanel> : null}
    {/* No heading: its Pose row leads it. */}
    {position ? <ToolPanel label="Position controls" fit="details" hidden={!positionActive}>{position.content}</ToolPanel> : null}
  </>;
}
