// Selection, copy-reference and expansion helpers over the STEP/assembly tree.
// Lifted verbatim out of CadWorkspace when the file surface moved into
// <CadFileView>; nothing here changed but its address.
import { canonicalCadRefCopyText, uniqueStringList } from "@/workbench/referenceSelection";
import { buildCadRefToken, isNativeCadSelector } from "cadgen-js/lib/cadRefs.js";
import { descendantLeafPartIds, findAssemblyNode } from "cadgen-js/lib/assembly/meshData";
import {
  collectStepTreeAncestorIds,
  flattenVisibleStepTreeRows,
  STEP_MODEL_ROOT_ID,
  STEP_TREE_TOPOLOGY_NODE_PREFIX,
  stepTreeNodeChildren
} from "cadgen-js/lib/step/stepTree";

export function stepTreeNodeIdForWorkspace(node) {
  return String(node?.id || node?.occurrenceId || "").trim();
}

export function nativeCadSelectorCandidate(value) {
  const selector = String(value || "").trim();
  return isNativeCadSelector(selector) ? selector : "";
}

export function selectorFromStepTreeInternalId(value) {
  const normalizedValue = String(value || "").trim();
  if (!normalizedValue.startsWith(STEP_TREE_TOPOLOGY_NODE_PREFIX)) {
    return "";
  }
  return nativeCadSelectorCandidate(normalizedValue.split(":").pop());
}

export function canonicalCopyTextForSelector(value, { allowOpaque = false } = {}) {
  const normalizedValue = String(value || "").trim();
  if (!normalizedValue) {
    return "";
  }
  if (normalizedValue.startsWith("#")) {
    return canonicalCadRefCopyText(normalizedValue);
  }
  const selector = selectorFromStepTreeInternalId(normalizedValue) || normalizedValue;
  if (!allowOpaque && !nativeCadSelectorCandidate(selector)) {
    return "";
  }
  return `#${selector}`;
}

export function canonicalCopyTextFromCandidates(candidates) {
  for (const candidate of Array.isArray(candidates) ? candidates : []) {
    const copyText = canonicalCopyTextForSelector(candidate?.value, {
      allowOpaque: candidate?.allowOpaque === true
    });
    if (copyText) {
      return copyText;
    }
  }
  return "";
}

export function stepTreeNodeSelectorIdForWorkspace(node) {
  return [
    node?.displaySelector,
    node?.occurrenceId,
    node?.sourceOccurrenceId,
    node?.sourceRootTargetOccurrenceId,
    node?.id
  ].map(nativeCadSelectorCandidate).find(Boolean) || "";
}

export function findStepTreeNodeForWorkspace(root, nodeId) {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!root || !normalizedNodeId) {
    return null;
  }
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    if (
      stepTreeNodeIdForWorkspace(node) === normalizedNodeId ||
      stepTreeNodeSelectorIdForWorkspace(node) === normalizedNodeId ||
      String(node?.name || "").trim() === normalizedNodeId ||
      String(node?.label || "").trim() === normalizedNodeId ||
      String(node?.displayName || "").trim() === normalizedNodeId
    ) {
      return node;
    }
    const children = stepTreeNodeChildren(node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return null;
}

export function collectStepTreeTopologyLoadableNodeIds(root) {
  const ids = [];
  const stack = root ? [root] : [];
  while (stack.length) {
    const node = stack.pop();
    const children = stepTreeNodeChildren(node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
    const nodeId = stepTreeNodeIdForWorkspace(node);
    if (
      nodeId &&
      String(node?.nodeType || "").trim() === "part" &&
      children.length === 0
    ) {
      ids.push(nodeId);
    }
  }
  return uniqueStringList(ids);
}

export function copyableStepTreeNodeForWorkspace({ assemblyPartMap, displayStepTreeRoot, stepTreeRoot, nodeId }) {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!normalizedNodeId) {
    return null;
  }
  return assemblyPartMap.get(normalizedNodeId) ||
    findStepTreeNodeForWorkspace(displayStepTreeRoot, normalizedNodeId) ||
    findStepTreeNodeForWorkspace(stepTreeRoot, normalizedNodeId) ||
    findAssemblyNode(displayStepTreeRoot, normalizedNodeId) ||
    findAssemblyNode(stepTreeRoot, normalizedNodeId) ||
    null;
}

export function copyableAssemblyPartForSelection(part, fallbackId) {
  const fallbackSelector = nativeCadSelectorCandidate(fallbackId);
  const selector = [
    fallbackSelector,
    part?.displaySelector,
    part?.occurrenceId,
    part?.sourceOccurrenceId,
    part?.sourceRootTargetOccurrenceId,
    part?.id
  ].map(nativeCadSelectorCandidate).find(Boolean) || "";
  if (!selector) {
    return null;
  }
  return {
    ...(part || {}),
    id: String(part?.id || selector).trim(),
    displaySelector: selector,
    occurrenceId: selector,
    name: String(part?.name || part?.label || part?.displayName || selector).trim()
  };
}

export function copyReferenceForAssemblyPartSelection(part, fallbackId) {
  const copyablePart = copyableAssemblyPartForSelection(part, fallbackId);
  const selector = String(copyablePart?.occurrenceId || copyablePart?.id || fallbackId || "").trim();
  if (!selector) {
    return null;
  }
  return {
    id: `assembly-part:${String(copyablePart?.id || selector).trim()}`,
    copyText: buildCadRefToken({ selector })
  };
}

export function copyReferenceForRawSelectorSelection(selector, idPrefix = "selector-ref") {
  const copyText = canonicalCopyTextForSelector(selector);
  if (!copyText) {
    return null;
  }
  const normalizedSelector = copyText.slice(1);
  return {
    id: `${idPrefix}:${normalizedSelector}`,
    copyText
  };
}

export function copyReferenceForStepTreeNodeSelection(node, fallbackId, idPrefix = "step-tree") {
  const nodeType = String(node?.nodeType || "").trim();
  const topologyNode = nodeType.startsWith("topology-");
  const copyText = canonicalCopyTextFromCandidates(topologyNode
    ? [
        { value: node?.displaySelector, allowOpaque: true },
        { value: node?.topologyReferenceId, allowOpaque: true },
        { value: fallbackId, allowOpaque: false },
        { value: node?.id, allowOpaque: false }
      ]
    : [
        { value: node?.displaySelector, allowOpaque: true },
        { value: node?.occurrenceId, allowOpaque: true },
        { value: node?.sourceOccurrenceId, allowOpaque: true },
        { value: node?.sourceRootTargetOccurrenceId, allowOpaque: true },
        { value: fallbackId, allowOpaque: false },
        { value: node?.id, allowOpaque: false }
      ]);
  if (!copyText) {
    return null;
  }
  const selector = copyText.slice(1);
  return {
    id: `${idPrefix}:${selector}`,
    copyText
  };
}

export function addStepTreeCopyReferenceMapEntry(map, key, reference) {
  const normalizedKey = String(key || "").trim();
  if (!normalizedKey || !reference || map.has(normalizedKey)) {
    return;
  }
  map.set(normalizedKey, reference);
}

export function buildStepTreeCopyReferenceMap(root) {
  const map = new Map();
  if (!root) {
    return map;
  }
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    const nodeId = stepTreeNodeIdForWorkspace(node);
    const reference = copyReferenceForStepTreeNodeSelection(node, nodeId);
    if (reference) {
      addStepTreeCopyReferenceMapEntry(map, nodeId, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.id, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.topologyReferenceId, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.displaySelector, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.occurrenceId, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.name, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.label, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.displayName, reference);
      addStepTreeCopyReferenceMapEntry(map, selectorFromStepTreeInternalId(node?.id), reference);
      addStepTreeCopyReferenceMapEntry(map, reference.copyText, reference);
      addStepTreeCopyReferenceMapEntry(map, reference.copyText.slice(1), reference);
    }
    const children = stepTreeNodeChildren(node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return map;
}

export function selectedCopyLinesFromIds(ids, copyReferenceMap) {
  const lines = [];
  const seen = new Set();
  for (const id of Array.isArray(ids) ? ids : []) {
    const normalizedId = String(id || "").trim();
    const copyText = canonicalCadRefCopyText(copyReferenceMap?.get(normalizedId)?.copyText) ||
      canonicalCopyTextForSelector(normalizedId);
    if (!copyText || seen.has(copyText)) {
      continue;
    }
    seen.add(copyText);
    lines.push(copyText);
  }
  return lines;
}

export function copyPayloadWithSelectedIdFallback(
  payload,
  {
    selectedReferenceIds = [],
    selectedPartIds = [],
    copyReferenceMap = null
  } = {}
) {
  const currentLines = Array.isArray(payload?.lines)
    ? payload.lines.map((line) => canonicalCadRefCopyText(line)).filter(Boolean)
    : [];
  if (currentLines.length) {
    return {
      ...(payload || {}),
      lines: uniqueStringList(currentLines),
      copiedCount: payload?.copiedCount || currentLines.length
    };
  }
  const fallbackLines = uniqueStringList([
    ...selectedCopyLinesFromIds(selectedReferenceIds, copyReferenceMap),
    ...selectedCopyLinesFromIds(selectedPartIds, copyReferenceMap)
  ]);
  return {
    ...(payload || {}),
    lines: fallbackLines,
    copiedCount: fallbackLines.length || payload?.copiedCount || 0
  };
}

export function addReferenceLookupKeys(map, reference) {
  if (!(map instanceof Map) || !reference) {
    return;
  }
  const keys = [
    reference?.id,
    reference?.normalizedSelector,
    reference?.displaySelector
  ].map((value) => String(value || "").trim()).filter(Boolean);
  const canonicalCopyText = canonicalCadRefCopyText(reference?.copyText);
  if (canonicalCopyText.startsWith("#")) {
    keys.push(canonicalCopyText);
    for (const selector of canonicalCopyText.slice(1).split(",")) {
      const normalizedSelector = String(selector || "").trim();
      if (normalizedSelector) {
        keys.push(normalizedSelector);
      }
    }
  }
  for (const key of keys) {
    if (!map.has(key)) {
      map.set(key, reference);
    }
  }
}

export function stepTreeRootRowIsElidedForWorkspace(root, isAssemblyView) {
  const children = stepTreeNodeChildren(root);
  return children.length > 0 && (
    isAssemblyView ||
    stepTreeNodeIdForWorkspace(root) === STEP_MODEL_ROOT_ID
  );
}

export function expandableStepTreeNodeIdsForWorkspace(root, {
  omitRoot = false,
  expandedTreeNodeIds = [],
  loadableTreeNodeIds = []
} = {}) {
  if (!root) {
    return [];
  }
  const ids = [];
  const seen = new Set();
  const loadableTreeNodeIdSet = new Set(
    (Array.isArray(loadableTreeNodeIds) ? loadableTreeNodeIds : [])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const visibleRows = flattenVisibleStepTreeRows(root, expandedTreeNodeIds, {
    omitRoot,
    showAllRootChildren: true
  });
  for (const row of visibleRows) {
    const node = row?.node || row;
    const nodeId = String(row?.id || "").trim() || stepTreeNodeIdForWorkspace(node);
    if (!nodeId || seen.has(nodeId)) {
      continue;
    }
    if (row?.hasChildren || stepTreeNodeChildren(node).length || loadableTreeNodeIdSet.has(nodeId)) {
      seen.add(nodeId);
      ids.push(nodeId);
    }
  }
  return ids;
}

export function buildStepTreeExpansionMenuState({
  root,
  isAssemblyView = false,
  expandedTreeNodeIds = [],
  loadableTreeNodeIds = [],
  actionNodeIds = []
} = {}) {
  const expandedTreeNodeIdSet = new Set(
    (Array.isArray(expandedTreeNodeIds) ? expandedTreeNodeIds : [])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const normalizedActionNodeIds = uniqueStringList(
    (Array.isArray(actionNodeIds) ? actionNodeIds : [])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const actionRows = normalizedActionNodeIds
    .map((nodeId) => findStepTreeNodeForWorkspace(root, nodeId))
    .filter(Boolean);
  const collapsedActionNodeIds = actionRows
    .filter((row) => (
      (
        stepTreeNodeChildren(row).length ||
        loadableTreeNodeIds.includes(stepTreeNodeIdForWorkspace(row))
      ) &&
      !expandedTreeNodeIdSet.has(stepTreeNodeIdForWorkspace(row))
    ))
    .map((row) => stepTreeNodeIdForWorkspace(row))
    .filter(Boolean);
  const expandedActionNodeIds = actionRows
    .filter((row) => (
      (
        stepTreeNodeChildren(row).length ||
        loadableTreeNodeIds.includes(stepTreeNodeIdForWorkspace(row))
      ) &&
      expandedTreeNodeIdSet.has(stepTreeNodeIdForWorkspace(row))
    ))
    .map((row) => stepTreeNodeIdForWorkspace(row))
    .filter(Boolean);
  const expandableTreeNodeIds = expandableStepTreeNodeIdsForWorkspace(root, {
    omitRoot: stepTreeRootRowIsElidedForWorkspace(root, isAssemblyView),
    expandedTreeNodeIds,
    loadableTreeNodeIds
  });
  const collapsedExpandableTreeNodeIds = expandableTreeNodeIds
    .filter((nodeId) => !expandedTreeNodeIdSet.has(nodeId));
  const expandedExpandableTreeNodeIds = expandableTreeNodeIds
    .filter((nodeId) => expandedTreeNodeIdSet.has(nodeId));
  return {
    collapsedActionNodeIds,
    expandedActionNodeIds,
    collapsedExpandableTreeNodeIds,
    expandedExpandableTreeNodeIds,
    showExpandCollapse: Boolean(
      actionRows.some((row) => stepTreeNodeChildren(row).length) ||
      expandableTreeNodeIds.length
    )
  };
}

export function visibleStepTreeTopologyReferenceIdsForWorkspace(root, expandedTreeNodeIds, {
  isAssemblyView = false
} = {}) {
  if (!root) {
    return [];
  }
  return uniqueStringList(
    flattenVisibleStepTreeRows(root, expandedTreeNodeIds, {
      omitRoot: stepTreeRootRowIsElidedForWorkspace(root, isAssemblyView),
      showAllRootChildren: true
    })
      .map((row) => String(row?.topologyReferenceId || "").trim())
      .filter(Boolean)
  );
}

export function findStepTreeTopologyNodeIdForReference(root, referenceId) {
  const normalizedReferenceId = String(referenceId || "").trim();
  if (!root || !normalizedReferenceId) {
    return "";
  }
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    if (String(node?.topologyReferenceId || "").trim() === normalizedReferenceId) {
      return stepTreeNodeIdForWorkspace(node);
    }
    const children = stepTreeNodeChildren(node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return "";
}

export function childAssemblyNodeIdForPickedLeaf(node, leafPartId) {
  const normalizedLeafPartId = String(leafPartId || "").trim();
  const children = Array.isArray(node?.children) ? node.children : [];
  if (!normalizedLeafPartId || !children.length) {
    return "";
  }
  for (const child of children) {
    const childId = String(child?.id || "").trim();
    if (!childId) {
      continue;
    }
    if (childId === normalizedLeafPartId) {
      return childId;
    }
    if (descendantLeafPartIds(child).includes(normalizedLeafPartId)) {
      return childId;
    }
  }
  return "";
}

export function collectTopologyWrapperExpansionIds(node) {
  const expansionIds = [];
  const stack = [...stepTreeNodeChildren(node)].reverse();
  while (stack.length) {
    const child = stack.pop();
    const childId = stepTreeNodeIdForWorkspace(child);
    const childType = String(child?.nodeType || "").trim();
    const children = stepTreeNodeChildren(child);
    if (childType.startsWith("topology-") && childId && children.length && child?.visualOnly !== true) {
      expansionIds.push(childId);
    }
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return expansionIds;
}

export function collectStepTreeRevealExpansionIds(root, nodeId, {
  expandSelf = false,
  includeVisualOnlyAncestors = true
} = {}) {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!root || !normalizedNodeId) {
    return [];
  }
  const node = findStepTreeNodeForWorkspace(root, normalizedNodeId);
  const expansionIds = collectStepTreeAncestorIds(root, normalizedNodeId)
    .filter((id) => {
      if (includeVisualOnlyAncestors) {
        return true;
      }
      const ancestor = findStepTreeNodeForWorkspace(root, id);
      return ancestor?.visualOnly !== true;
    });
  if (expandSelf && node && stepTreeNodeChildren(node).length) {
    expansionIds.push(normalizedNodeId, ...collectTopologyWrapperExpansionIds(node));
  }
  return [...new Set(expansionIds.filter(Boolean))];
}

export function collectStepTreeSubtreeIds(root, nodeId) {
  const normalizedNodeId = String(nodeId || "").trim();
  const node = findStepTreeNodeForWorkspace(root, normalizedNodeId);
  if (!node) {
    return normalizedNodeId ? [normalizedNodeId] : [];
  }
  const ids = [];
  const stack = [node];
  while (stack.length) {
    const current = stack.pop();
    const currentId = stepTreeNodeIdForWorkspace(current);
    if (currentId) {
      ids.push(currentId);
    }
    const children = stepTreeNodeChildren(current);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return ids;
}
