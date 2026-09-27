import { STEP_MODEL_ROOT_ID } from "@hardcore/core/lib/step/stepTree.js";
import { buildSelectionCopyPayload, buildWholeStepEntryCopyReference, copyTextLines } from "../workbench/referenceSelection.js";
import {
  copyPayloadWithSelectedIdFallback,
  copyReferenceForAssemblyPartSelection,
  copyReferenceForRawSelectorSelection,
  copyReferenceForStepTreeNodeSelection,
  copyableStepTreeNodeForWorkspace
} from "./stepTreeSelection.js";

// What a STEP copies: the references a selection, or one tree node, resolves to, as the text
// Copy Reference puts on the clipboard. Pure: the surface hands in what its references are
// resolved through, as it stands.

/**
 * @typedef {{ entry: object, isAssemblyView: boolean, copyReferenceMap: Map<string, object>,
 *   referenceMap: Map<string, object>, assemblyPartMap: Map<string, object>, displayRoot: object | null,
 *   root: object | null }} StepCopyContext
 */

const topologyReference = (context, id) => context.copyReferenceMap.get(id) || context.referenceMap.get(id) ||
  copyReferenceForRawSelectorSelection(id, "topology");
const treeNode = (context, id) => copyableStepTreeNodeForWorkspace({
  assemblyPartMap: context.assemblyPartMap, displayStepTreeRoot: context.displayRoot, stepTreeRoot: context.root, nodeId: id
});

/**
 * The copy payload for a selection: its faces and edges, then its parts (a part's own selector,
 * else its tree node's), with the whole file standing for a single part's root.
 *
 * @param {StepCopyContext} context
 * @param {{ referenceIds: string[], partIds: string[] }} selection
 */
export function selectionCopyPayload(context, { referenceIds, partIds }) {
  const references = referenceIds.map((id) => topologyReference(context, id)).filter(Boolean);
  if (!context.isAssemblyView && partIds.includes(STEP_MODEL_ROOT_ID)) {
    const whole = buildWholeStepEntryCopyReference(context.entry);
    if (whole) references.push(whole);
  }
  const parts = partIds.map((id) => copyReferenceForRawSelectorSelection(id, "assembly-part") ||
    context.copyReferenceMap.get(id) ||
    copyReferenceForStepTreeNodeSelection(treeNode(context, id), id, "assembly-part")).filter(Boolean);
  return copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({ references: [...references, ...parts], parts: [], entry: context.entry }), {
    selectedReferenceIds: referenceIds, selectedPartIds: partIds, copyReferenceMap: context.copyReferenceMap
  });
}

/**
 * What one node copies — a Features row or a picked face, edge or part — shaped the one way
 * copied text is (`copyTextLines`): canonical, carrying the file's prefix. "" when it has none.
 *
 * @param {StepCopyContext} context
 * @param {string} id
 * @param {{ topology?: boolean }} [options]  `topology`: the id is a face or edge reference.
 */
export function nodeCopyText(context, id, { topology = false } = {}) {
  const normalizedId = String(id || "").trim();
  if (!normalizedId) return "";
  const whole = !topology && !context.isAssemblyView && normalizedId === STEP_MODEL_ROOT_ID
    ? buildWholeStepEntryCopyReference(context.entry) : null;
  const reference = topology ? topologyReference(context, normalizedId) || null : null;
  const part = !topology && !whole
    ? context.copyReferenceMap.get(normalizedId) ||
      copyReferenceForStepTreeNodeSelection(treeNode(context, normalizedId), normalizedId, "assembly-part") ||
      copyReferenceForAssemblyPartSelection(treeNode(context, normalizedId), normalizedId) ||
      copyReferenceForRawSelectorSelection(normalizedId, "assembly-part")
    : null;
  const { lines } = copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
    references: [whole, reference, part].filter(Boolean), parts: [], entry: context.entry
  }), {
    selectedReferenceIds: topology ? [normalizedId] : [],
    selectedPartIds: topology ? [] : [normalizedId],
    copyReferenceMap: context.copyReferenceMap
  });
  return copyTextLines(lines.slice(0, 1), context.entry?.fileRefPrefix)[0] || "";
}
