import { useCallback, useMemo, useState } from 'react';
import { STEP_MODEL_ROOT_ID } from '@hardcore/core/lib/step/stepTree.js';
import FileSheet from '../../../kit/inspector/FileSheet.js';
import FileSheetTabbedSurface from '../../../kit/inspector/FileSheetTabbedSurface.js';
import { buildFileStatusTab } from './FileStatusSection.js';
import { buildMotionControlsTab } from './MotionControlsSection.js';
import { StepReferenceSection } from './StepReferenceSection.js';
import ModelingTree from './ModelingTree.jsx';
import { useStepModeling } from '../../workbench/useStepModeling.js';
import { stepGeometryMeasurements } from '../../workbench/stepGeometryMeasurements.js';
const EMPTY = [];

export default function StepFileSheet({
  headerActions = null,
  client, open, isDesktop, width, onOpenChange, onStartResize, selectedEntry, viewerLoading,
  geometryInspection = null, stepTreeRoot, isAssemblyView = false,
  selectedMeshData = null, selectedSourceAppearance = null,
  selectedPartIds = EMPTY, selectedReferenceIds = EMPTY, selectedReferences = EMPTY,
  hiddenPartIds = EMPTY, focusedNodeIds = EMPTY, selectableNodeIds = null,
  expandedTreeNodeIds = EMPTY, onToggleTreeNode, onVisibleFeatureTargetsChange,
  activeTreeNodeScrollKey = '', onSelectTreeNode, onSelectReferenceGroup, onClearSelection,
  onFocusTreeNode, onUnfocusTreeNode, onExitAllIsolate, onTogglePartVisibility,
  onCopyTreeNodeReference, onHoverTreeNode, showAllHiddenParts,
  treeSelectionDisabled = false, treeSelectionDisabledReason = '',
  stepModule = null, stepAnimation = null, statusItems = EMPTY,
  openSectionIds = EMPTY, onOpenSectionIdsChange, settingsTabs = EMPTY,
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
    id: 'tree', title: 'Features', keepMounted: true, scrollsContent: true,
    titleAttr: treeSelectionDisabled ? treeSelectionDisabledReason : undefined,
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
        onTogglePartVisibility, showAllHiddenParts, onCopyTreeNodeReference, onHoverTreeNode}}
    />,
  }, buildMotionControlsTab({
    poseRuntime: stepModule, animationRuntime: stepAnimation,
    poseProps: { loadingLabel: 'Loading kinematics...', noParametersLabel: 'No pose controls.' },
  }), ...settingsTabs, buildFileStatusTab(statusItems)].filter(Boolean);
  return <FileSheet open={open} title="STEP" isDesktop={isDesktop} width={width}
    onOpenChange={onOpenChange} onStartResize={onStartResize} scrollBody={false}>
    <FileSheetTabbedSurface headerActions={headerActions} sections={sections} openSectionIds={openSectionIds}
      onOpenSectionIdsChange={onOpenSectionIdsChange} />
  </FileSheet>;
}
