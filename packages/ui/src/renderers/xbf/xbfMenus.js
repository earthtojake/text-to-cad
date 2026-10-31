import { implicitXbfRoots } from "./xbfTree.js";

// The three menus an engine document offers, as a STEP's were, as descriptors
// (`xbfMenuItems.js` renders them):
// the model as a whole (a press on empty space), one node's part menu (the viewport and a model
// tree row alike), and a face's or edge's. Each is built from what the surface holds when the
// menu is asked for; nothing here holds state.

const unique = ids => [...new Set(ids.filter(Boolean))];

/** The rows the menus open and shut: every assembly and part but the document's wrapper and the tree's implicit roots. */
export function xbfExpandableIds(tree) {
  const fixed = new Set([tree.wrapper?.selectionId, ...implicitXbfRoots(tree.roots).map(node => node.selectionId)].filter(Boolean));
  return [...tree.nodes.keys()].filter(id => !fixed.has(id));
}

function expansionState({ tree, expandedIds, actionNodeIds }) {
  const expandable = xbfExpandableIds(tree);
  const open = new Set(expandedIds);
  const actions = actionNodeIds.filter(id => expandable.includes(id));
  return {
    collapsedActionNodeIds: actions.filter(id => !open.has(id)),
    expandedActionNodeIds: actions.filter(id => open.has(id)),
    collapsedExpandableTreeNodeIds: expandable.filter(id => !open.has(id)),
    expandedExpandableTreeNodeIds: expandable.filter(id => open.has(id))
  };
}

/**
 * The menu over empty space: reveal what is hidden, open or close the tree, and frame it again.
 * A lone part's carries the whole document's reference for Copy Reference (the model IS the part).
 */
export function xbfModelMenu({ tree, assembly, expandedIds, hiddenCount, zoomSelectionAvailable, copyText = "", shape = "all" }) {
  const expansion = expansionState({ tree, expandedIds, actionNodeIds: [] });
  const expandAllDisabled = expansion.collapsedExpandableTreeNodeIds.length < 1;
  const collapseAllDisabled = expansion.expandedExpandableTreeNodeIds.length < 1;
  return {
    global: true, label: "Viewer", hidden: true, zoomSelectionAvailable,
    copyText: assembly ? "" : copyText,
    showShowAll: hiddenCount > 0,
    // Picking only parts or only topology, the filter holds the tree's shape: there is nothing to expand or collapse.
    showExpandCollapse: assembly && shape === "all" && !(expandAllDisabled && collapseAllDisabled),
    ...expansion, expandAllDisabled, collapseAllDisabled
  };
}

/**
 * The part menu for ONE node of the model; its actions take the whole selection with them
 * (`actionNodeIds`).
 */
export function xbfPartMenu({ tree, nodeId, assembly, hiddenIds, isolatedIds, selectedNodeIds, expandedIds, copyText, zoomSelectionAvailable, shape = "all" }) {
  const node = tree.nodes.get(nodeId);
  if (!node) return null;
  const hidden = node.leafPartIds.length > 0 && node.leafPartIds.every(id => hiddenIds.includes(id));
  const focused = isolatedIds.includes(nodeId);
  const selected = selectedNodeIds.includes(nodeId);
  const actionNodeIds = unique([...selectedNodeIds, nodeId]);
  const expansion = expansionState({ tree, expandedIds, actionNodeIds });
  return {
    nodeId, label: node.label, zoomSelectionAvailable, selected, hidden, focused, actionNodeIds,
    actionCount: actionNodeIds.length || 1, copyText,
    selectDisabled: !selected && hidden,
    showIsolate: assembly, isolateDisabled: false,
    showExitAllIsolate: isolatedIds.length > 1, exitAllIsolateDisabled: isolatedIds.length < 2,
    showHideOther: true, hideOtherDisabled: hidden,
    showVisibility: !focused, visibilityDisabled: focused,
    showHideAll: false, hideAllDisabled: false,
    showExpandCollapse: assembly && shape === "all",
    ...expansion,
    expandSelectedDisabled: expansion.collapsedActionNodeIds.length < 1,
    collapseSelectedDisabled: expansion.expandedActionNodeIds.length < 1,
    expandAllDisabled: expansion.collapsedExpandableTreeNodeIds.length < 1,
    collapseAllDisabled: expansion.expandedExpandableTreeNodeIds.length < 1
  };
}

/** The menu over a face or an edge: Copy Reference, Select or Deselect, and the framing. */
export function xbfTopologyMenu({ elementId, label, selectedElementIds, copyText, zoomSelectionAvailable }) {
  const referenceIds = unique([...selectedElementIds, elementId]);
  return {
    referenceId: elementId, referenceIds, label, selected: selectedElementIds.includes(elementId), hidden: false, focused: false,
    actionCount: referenceIds.length, copyText, zoomSelectionAvailable,
    showIsolate: false, showHideOther: false, showVisibility: false, showHideAll: false
  };
}
