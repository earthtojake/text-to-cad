import { buildSelectionCopyPayload, uniqueStringList } from "../workbench/referenceSelection.js";
import {
  buildStepTreeExpansionMenuState,
  copyPayloadWithSelectedIdFallback,
  copyReferenceForAssemblyPartSelection,
  copyReferenceForRawSelectorSelection,
  copyReferenceForStepTreeNodeSelection
} from "./stepTreeSelection.js";

// The three menus a STEP offers, as DESCRIPTORS: plain objects saying what the menu is about
// and what it can do (`viewportMenuEntries` and the Features tree render them). Each is built
// from what the surface holds at the moment the menu is asked for, and nothing here holds
// state: the surface hands in the model's tree, the selection, what is hidden and isolated.

const idList = (values) => uniqueStringList((Array.isArray(values) ? values : []).map((id) => String(id || "").trim()).filter(Boolean));

/**
 * The menu over empty space: the model as a whole — reveal what is hidden, open or close the
 * tree, and frame it again. The framing is always worth offering (a press on the backdrop is
 * how somebody who zoomed off the model gets it back); the rest comes and goes with what it
 * could do.
 */
export function modelMenuDescriptor({ root, isAssemblyView, expandedIds, loadableIds, hiddenCount, zoomSelectionAvailable }) {
  const expansion = buildStepTreeExpansionMenuState({
    root, isAssemblyView, expandedTreeNodeIds: expandedIds, loadableTreeNodeIds: loadableIds, actionNodeIds: []
  });
  const expandAllDisabled = expansion.collapsedExpandableTreeNodeIds.length < 1;
  const collapseAllDisabled = expandedIds.length < 1;
  const showExpandCollapse = expansion.showExpandCollapse || expandedIds.length > 0;
  return {
    global: true,
    label: "Viewer",
    hidden: true,
    zoomSelectionAvailable,
    showShowAll: hiddenCount > 0,
    showExpandCollapse: showExpandCollapse && !(expandAllDisabled && collapseAllDisabled),
    collapsedExpandableTreeNodeIds: expansion.collapsedExpandableTreeNodeIds,
    expandedExpandableTreeNodeIds: expandedIds,
    expandAllDisabled,
    collapseAllDisabled
  };
}

/**
 * The part menu for ONE node of the model. The viewport's secondary tap and the Features
 * tree's row menu both ask for it, so the two are the same menu over the same node by
 * construction. Its actions take the whole selection with them (`actionNodeIds`).
 *
 * @param {{ nodeId: string, renderPartId?: string, node: object | null, leafIds: string[], hiddenPartIds: string[],
 *   focusedNodeIds: string[], selectedPartIds: string[], root: object | null, isAssemblyView: boolean,
 *   expandedIds: string[], loadableIds: string[], copyReferenceMap: Map<string, object>, entry: object,
 *   zoomSelectionAvailable: boolean }} context  `renderPartId` is the leaf the pointer landed on, in the viewport.
 */
export function partMenuDescriptor({
  nodeId, renderPartId = "", node, leafIds, hiddenPartIds, focusedNodeIds, selectedPartIds, root, isAssemblyView,
  expandedIds, loadableIds, copyReferenceMap, entry, zoomSelectionAvailable
}) {
  const id = String(nodeId || "").trim();
  if (!id) return null;
  const label = String(node?.displayName || node?.name || node?.label || id).trim();
  const hidden = leafIds.length > 0 && leafIds.every((leafId) => hiddenPartIds.includes(leafId));
  const focused = focusedNodeIds.includes(id);
  const selected = selectedPartIds.includes(id);
  const actionNodeIds = idList([...selectedPartIds, id]);
  const expansion = buildStepTreeExpansionMenuState({
    root, isAssemblyView, expandedTreeNodeIds: expandedIds, loadableTreeNodeIds: loadableIds, actionNodeIds
  });
  const reference = copyReferenceMap.get(id) ||
    copyReferenceForStepTreeNodeSelection(node, id, "assembly-part") ||
    copyReferenceForAssemblyPartSelection(node, id) ||
    copyReferenceForRawSelectorSelection(id, "assembly-part");
  const { lines } = copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
    references: reference ? [reference] : [], parts: [], entry
  }), { selectedPartIds: actionNodeIds, copyReferenceMap });
  return {
    nodeId: id,
    renderPartId: String(renderPartId || "").trim() || id,
    label,
    zoomSelectionAvailable,
    selected,
    hidden,
    focused,
    actionNodeIds,
    actionCount: actionNodeIds.length || 1,
    copyText: lines[0] || "",
    selectDisabled: !selected && hidden,
    showIsolate: isAssemblyView,
    isolateDisabled: false,
    showExitAllIsolate: focusedNodeIds.length > 1,
    exitAllIsolateDisabled: focusedNodeIds.length < 2,
    showHideOther: true,
    hideOtherDisabled: hidden,
    showVisibility: !focused,
    visibilityDisabled: focused,
    showHideAll: false,
    hideAllDisabled: false,
    hideAllLabel: "Show all",
    showExpandCollapse: expansion.showExpandCollapse,
    collapsedActionNodeIds: expansion.collapsedActionNodeIds,
    expandedActionNodeIds: expansion.expandedActionNodeIds,
    collapsedExpandableTreeNodeIds: expansion.collapsedExpandableTreeNodeIds,
    expandedExpandableTreeNodeIds: expansion.expandedExpandableTreeNodeIds,
    expandSelectedDisabled: expansion.collapsedActionNodeIds.length < 1,
    collapseSelectedDisabled: expansion.expandedActionNodeIds.length < 1,
    expandAllDisabled: expansion.collapsedExpandableTreeNodeIds.length < 1,
    collapseAllDisabled: expansion.expandedExpandableTreeNodeIds.length < 1
  };
}

/**
 * The menu over topology: the faces and edges of one pick in the viewport, or of one Features
 * row (its feature, group or body) — one descriptor for both. Topology is not a part, so it
 * offers no isolate or visibility; its actions take the selection with them, as a part's do.
 * `referenceIds` may be empty while a row's topology is still loading: the menu then opens
 * with nothing to copy yet, rather than not at all.
 *
 * @param {{ referenceIds: string[], label?: string, selectedReferenceIds: string[], referenceMap: Map<string, object>,
 *   copyReferenceMap: Map<string, object>, entry: object, zoomSelectionAvailable: boolean }} context
 */
export function topologyMenuDescriptor({ referenceIds, label = "", selectedReferenceIds, referenceMap, copyReferenceMap, entry, zoomSelectionAvailable }) {
  const ids = idList(referenceIds);
  const selectedIds = idList(selectedReferenceIds);
  const actionReferenceIds = ids.length ? idList([...selectedIds, ...ids]) : [];
  const references = actionReferenceIds
    .map((id) => copyReferenceMap.get(id) || referenceMap.get(id) || copyReferenceForRawSelectorSelection(id, "topology"))
    .filter(Boolean);
  const { lines } = actionReferenceIds.length ? copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
    references, parts: [], entry
  }), { selectedReferenceIds: actionReferenceIds, copyReferenceMap }) : { lines: [] };
  return {
    referenceId: ids[0] || "",
    referenceIds: actionReferenceIds,
    label: String(label || ids[0] || "").trim(),
    selected: ids.length > 0 && ids.every((id) => selectedIds.includes(id)),
    hidden: false,
    focused: false,
    actionCount: actionReferenceIds.length || 1,
    copyText: lines.join("\n"),
    zoomSelectionAvailable,
    showIsolate: false,
    showHideOther: false,
    showVisibility: false,
    showHideAll: false
  };
}
