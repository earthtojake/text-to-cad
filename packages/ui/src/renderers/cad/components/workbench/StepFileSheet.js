import { useEffect, useMemo, useState } from 'react';
import { STEP_MODEL_ROOT_ID } from '@hardcore/core/lib/step/stepTree.js';
import FileSheet from './FileSheet.js';
import FileSheetTabbedSurface from './FileSheetTabbedSurface.js';
import { buildFileStatusTab } from './FileStatusSection.js';
import { buildPoseControlsTab } from './PoseControlsSection.js';
import { buildAnimationControlsTab } from './AnimationControlsSection.js';
import { buildStepReferenceTab } from './StepReferenceSection.js';
import ModelingTree from './ModelingTree.jsx';
import StepGeometryProperties from './StepGeometryProperties.jsx';
import { useStepModeling } from '../../workbench/useStepModeling.js';
import { stepGeometryMeasurements, stepGeometryDimension } from '../../workbench/stepGeometryMeasurements.js';
import { FILE_SHEET_SECTION_IDS } from '../../workbench/fileSheetSections.js';
const EMPTY = [];

export default function StepFileSheet({
  open, isDesktop, width, onOpenChange, onStartResize, selectedEntry, viewerLoading,
  geometryInspection = null, stepTreeRoot, isAssemblyView = false,
  selectedPartIds = EMPTY, selectedReferenceIds = EMPTY, selectedReferences = EMPTY,
  hiddenPartIds = EMPTY, focusedNodeIds = EMPTY, selectableNodeIds = null,
  activeTreeNodeScrollKey = '', onSelectTreeNode, onSelectReferenceGroup,
  onFocusTreeNode, onUnfocusTreeNode, onExitAllIsolate, onTogglePartVisibility,
  onCopyTreeNodeReference, onHoverTreeNode, showAllHiddenParts,
  treeSelectionDisabled = false, treeSelectionDisabledReason = '',
  stepModule = null, stepAnimation = null, statusItems = EMPTY, themeTabs = EMPTY,
  openSectionIds = EMPTY, onOpenSectionIdsChange,
}) {
  const modeling = useStepModeling(selectedEntry, !treeSelectionDisabled && !viewerLoading);
  const [inspection, setInspection] = useState(null);
  const modelReferences = geometryInspection?.references || EMPTY;
  const modelParts = geometryInspection?.parts || EMPTY;
  const highlight = geometryInspection?.onHighlight;
  const measuredSelection = useMemo(() => ({
    faceIds: selectedReferences.filter(ref => ref.selectorType === 'face').map(ref => ref.id),
    partIds: [...new Set([
      ...(selectedPartIds || []).flatMap(id => id === STEP_MODEL_ROOT_ID ? modelParts.map(part => part.id) : modelParts.some(part => part.id === id) ? [id] : []),
      ...selectedReferences.filter(ref => ref.selectorType === 'occurrence' && modelParts.some(part => part.id === ref.id)).map(ref => ref.id),
    ])],
  }), [selectedReferences, selectedPartIds, modelParts]);
  const measurements = useMemo(() => stepGeometryMeasurements(measuredSelection, modelReferences, modelParts), [measuredSelection, modelReferences, modelParts]);
  const selectionKey = [...selectedReferenceIds, ...measuredSelection.partIds].join('|');
  useEffect(() => setInspection(null), [selectionKey]);
  useEffect(() => {
    if (!inspection) return;
    const selection = inspection.kind === 'axis'
      ? { ...measuredSelection, measurement: stepGeometryDimension(measuredSelection, modelReferences, modelParts, inspection.value) }
      : { partIds: [], faceIds: modelReferences.filter(ref => measuredSelection.faceIds.includes(ref.id) && ['cylinder', 'sphere'].includes(ref.pickData?.surfaceType || ref.pickData?.params?.kind) && Number.isFinite(ref.pickData?.params?.radius) && Number(ref.pickData.params.radius.toPrecision(10)) === inspection.value).map(ref => ref.id) };
    highlight?.(selection, 'Selected geometry', {file: selectedEntry?.file, label: 'Selected geometry', measurements, inspection});
    return () => highlight?.(null);
  }, [inspection, measuredSelection, modelReferences, modelParts, highlight, selectedEntry?.file, measurements]);
  const inspect = (kind, value) => setInspection(current => current?.kind === kind && current.value === value ? null : {kind, value});

  if (!selectedEntry) return null;
  const selectionDetails = selectedReferences.length || measuredSelection.partIds.length ? <>
    <StepGeometryProperties measurements={measurements} inspection={inspection} inspect={inspect} />
    {selectedReferences.length > 0 && buildStepReferenceTab({ references: selectedReferences }).content}
  </> : null;
  const sections = [{
    id: 'tree', title: 'Model', keepMounted: true, scrollsContent: true,
    titleAttr: treeSelectionDisabled ? treeSelectionDisabledReason : undefined,
    content: active => <ModelingTree key={`${selectedEntry.file}:${geometryInspection?.revision}`}
      modeling={modeling} stepRoot={stepTreeRoot} active={active && open}
      disabled={treeSelectionDisabled || viewerLoading}
      references={modelReferences} selectedReferences={selectedReferences}
      selectedReferenceIds={selectedReferenceIds} selectedPartIds={selectedPartIds}
      selectionDetails={selectionDetails} activeTreeNodeScrollKey={activeTreeNodeScrollKey}
      onLoadTopology={geometryInspection?.onLoadTopology} onSelect={onSelectReferenceGroup}
      partControls={{isAssemblyView, hiddenPartIds, focusedNodeIds, selectableNodeIds,
        onSelectTreeNode, onFocusTreeNode, onUnfocusTreeNode, onExitAllIsolate,
        onTogglePartVisibility, showAllHiddenParts, onCopyTreeNodeReference, onHoverTreeNode}}
    />,
  }, buildPoseControlsTab({
    value: FILE_SHEET_SECTION_IDS.STEP_POSE, runtime: stepModule,
    loadingLabel: 'Loading kinematics...', noParametersLabel: 'No pose controls.',
    showEnableToggle: true, enableAriaLabel: 'Enable pose', resetTitle: 'Reset pose',
  }), buildAnimationControlsTab({ value: FILE_SHEET_SECTION_IDS.STEP_ANIMATION, runtime: stepAnimation }),
  ...themeTabs, buildFileStatusTab(statusItems)];
  return <FileSheet open={open} title="STEP" isDesktop={isDesktop} width={width}
    onOpenChange={onOpenChange} onStartResize={onStartResize} scrollBody={false}>
    <FileSheetTabbedSurface kind="step" sections={sections} openSectionIds={openSectionIds}
      onOpenSectionIdsChange={onOpenSectionIdsChange} />
  </FileSheet>;
}
