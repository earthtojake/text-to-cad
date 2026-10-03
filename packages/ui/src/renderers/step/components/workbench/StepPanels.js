import { useCallback, useMemo, useRef, useState } from 'react';
import { buildPositionSection } from './MotionControlsSection.js';
import { STEP_MODEL_ROOT_ID } from '@text-to-cad/core/lib/step/stepTree.js';
import { useStepReference } from './StepReferenceSection.js';
import ModelingTree from './ModelingTree.jsx';
import ToolPanel from '../../../kit/tools/ToolPanel.jsx';
import { useStepModeling } from '../../workbench/useStepModeling.js';
import { stepGeometryMeasurements } from '../../workbench/stepGeometryMeasurements.js';
const EMPTY = [];

/**
 * `fn` behind one identity for the life of the panels, calling whatever `fn` is now: the tree's
 * rows are memoized, so a host callback rebuilt on every render must not re-render them. Absent
 * stays absent (a row reads whether an action is offered from whether its callback exists).
 */
function useLatestCallback(fn) {
  const latest = useRef(fn);
  latest.current = fn;
  const stable = useCallback((...args) => latest.current?.(...args), []);
  return typeof fn === 'function' ? stable : fn;
}

/** An object of callbacks (`partMenuActions`) the same way: one object while its names stay the same. */
function useLatestActions(actions) {
  const latest = useRef(actions);
  latest.current = actions;
  const names = actions ? Object.keys(actions).filter(name => typeof actions[name] === 'function').sort().join('\n') : null;
  return useMemo(() => names === null ? actions : Object.fromEntries(names.split('\n').filter(Boolean)
    .map(name => [name, (...args) => latest.current?.[name]?.(...args)])), [names]);
}

/**
 * A STEP's panels in the tool stack, top to bottom: while Select is the tool, **Features** (the
 * filter and the model tree) and the **Reference** for what is selected; while Position is the
 * tool, **Position**. Each stays mounted while its tool is not
 * up, so the tree keeps its expansion, filter and scroll. The kept effects' panels follow them
 * (`ModelTools.jsx`); the stack itself is the shell's (`kit/shell/RendererShell.jsx`).
 *
 * `selectActive`: Features is on screen, which is when recognition is worth running and a pick
 * is scrolled to. `selectMode` is the Select tool's mode, which the tree's disclosure follows.
 */
export function useStepPanels({
  client, selectActive, positionActive, selectedEntry, viewerLoading,
  geometryInspection = null, stepTreeRoot, isAssemblyView = false,
  selectedMeshData = null,
  selectedPartIds = EMPTY, selectedReferenceIds = EMPTY, selectedReferences = EMPTY,
  hiddenPartIds = EMPTY, focusedNodeIds = EMPTY, selectableNodeIds = null,
  expandedTreeNodeIds = EMPTY, onToggleTreeNode,
  activeTreeNodeScrollKey = '', onSelectTreeNode, onSelectReferenceGroup, onClearSelection,
  onFocusTreeNode, onUnfocusTreeNode, onExitAllIsolate, onTogglePartVisibility,
  onCopySelection, onHoverTreeNode, showAllHiddenParts,
  // The Reference panel's Copy (Copy All): `{ label, shortcut, onCopy }`, or null with nothing to copy.
  selectionCopy = null,
  // The menus a tree row carries: a part's descriptor per node, a feature's per set of faces
  // and edges (the viewport's menu over that topology), and the one set of actions behind both.
  menuForNode = null, menuForReferences = null, partMenuActions = null,
  treeSelectionDisabled = false, selectMode = 'all', loadingGeometry = false,
  positionRuntime = null, selectModeMenu = null, onClosePosition = null,
  // The viewport's hover (`workbench/hoverStore.js`): a large tree under Faces or Edges asks for the
  // topology of the part the pointer rests on.
  hoverStore = null,
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
  // A part's or a subassembly's own size, from the boxes of the parts it is made of: the browsed
  // one's in a multi-selection, where the selection's size is all of them together.
  const partsSize = useCallback(ids => stepGeometryMeasurements({ partIds: ids }, EMPTY, modelParts).size, [modelParts]);
  // A face or edge is named after its part as the tree names that part.
  const partNames = useMemo(() => {
    const names = new Map();
    const visit = node => { if (!node) return; if (node.id) names.set(String(node.id), String(node.displayName || node.name || '').trim()); (node.children || EMPTY).forEach(visit); };
    visit(stepTreeRoot);
    return names;
  }, [stepTreeRoot]);
  const partName = useCallback(id => partNames.get(String(id || '')) || '', [partNames]);
  const reference = useStepReference({ references: selectedReferences, meshData: selectedMeshData, measurements, partsSize, partName });
  // What every tree row is handed, the same object until something in it changes: the host's
  // actions behind stable identities, its menus and state as they are.
  const toggleTreeNode = useLatestCallback(onToggleTreeNode), selectTreeNode = useLatestCallback(onSelectTreeNode);
  const focusTreeNode = useLatestCallback(onFocusTreeNode), unfocusTreeNode = useLatestCallback(onUnfocusTreeNode);
  const exitAllIsolate = useLatestCallback(onExitAllIsolate), togglePartVisibility = useLatestCallback(onTogglePartVisibility);
  const showAll = useLatestCallback(showAllHiddenParts), copySelection = useLatestCallback(onCopySelection);
  const hoverTreeNode = useLatestCallback(onHoverTreeNode);
  // A row's menu is built when it opens, from the host's descriptors as they are then.
  const nodeMenu = useLatestCallback(menuForNode), referencesMenu = useLatestCallback(menuForReferences);
  const menuActions = useLatestActions(partMenuActions);
  const partControls = useMemo(() => ({ isAssemblyView, hiddenPartIds, focusedNodeIds, selectableNodeIds, expandedTreeNodeIds,
    onToggleTreeNode: toggleTreeNode, onSelectTreeNode: selectTreeNode, onFocusTreeNode: focusTreeNode, onUnfocusTreeNode: unfocusTreeNode,
    onExitAllIsolate: exitAllIsolate, onTogglePartVisibility: togglePartVisibility, showAllHiddenParts: showAll, onCopySelection: copySelection,
    onHoverTreeNode: hoverTreeNode, menuForNode: nodeMenu, menuForReferences: referencesMenu, partMenuActions: menuActions }), [isAssemblyView,
    hiddenPartIds, focusedNodeIds, selectableNodeIds, expandedTreeNodeIds, toggleTreeNode, selectTreeNode, focusTreeNode, unfocusTreeNode,
    exitAllIsolate, togglePartVisibility, showAll, copySelection, hoverTreeNode, nodeMenu, referencesMenu, menuActions]);
  const loadTopology = useLatestCallback(geometryInspection?.onLoadTopology);
  const selectReferenceGroup = useLatestCallback(onSelectReferenceGroup), clearSelection = useLatestCallback(onClearSelection);
  const closePosition = useLatestCallback(onClosePosition);
  if (!selectedEntry) return null;
  const selectionDetails = selectedReferences.length || measuredSelection.partIds.length ? reference : null;
  const position = buildPositionSection({ poseRuntime: positionRuntime });
  return <>
    {/* Features, then the Reference for a selection: both the tree's, which knows what is picked in it. */}
    <ModelingTree key={`${selectedEntry.file}:${geometryInspection?.revision}`}
      modeling={modeling} stepRoot={stepTreeRoot} active={selectActive} mode={selectMode} modeMenu={selectModeMenu} loading={loadingGeometry}
      onRequestRecognition={onRequestRecognition}
      disabled={treeSelectionDisabled || viewerLoading}
      references={modelReferences} selectedReferences={selectedReferences}
      selectedReferenceIds={selectedReferenceIds} selectedPartIds={selectedPartIds}
      selectionDetails={selectionDetails} selectionCopy={selectionCopy} activeTreeNodeScrollKey={activeTreeNodeScrollKey}
      onLoadTopology={loadTopology} onSelect={selectReferenceGroup} onClearSelection={clearSelection}
      partControls={partControls} hoverStore={hoverStore}
    />
    {/* Headed "Position" with its Reset; sized like the tree: its content's height, up to half the stack. */}
    {/* Its X puts Position down, back to Select; the values stay. */}
    {position ? <ToolPanel id="position" title={position.title} actions={position.actions} label="Position controls" fit="details" resizable
      collapsible={false} onClose={closePosition} closeLabel="Close position" hidden={!positionActive}>{position.content}</ToolPanel> : null}
  </>;
}
