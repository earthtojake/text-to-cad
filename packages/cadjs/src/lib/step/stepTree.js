export const STEP_MODEL_ROOT_ID = "__step_model__";
export const STEP_MODEL_RENDER_PART_ID = "__model__";
export const STEP_TREE_TOPOLOGY_NODE_PREFIX = "step-topology:";

const STEP_TREE_TOPOLOGY_SELECTOR_TYPES = new Set(["occurrence", "shape", "face", "edge"]);

function normalizeString(value, fallback = "") {
  return String(value ?? fallback).trim();
}

function normalizePositiveInteger(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue) || numericValue < 1) {
    return null;
  }
  return Math.floor(numericValue);
}

function basename(value) {
  const normalized = normalizeString(value);
  if (!normalized) {
    return "";
  }
  return normalized.split(/[\\/]/).filter(Boolean).pop() || normalized;
}

export function stepTreeNodeId(node) {
  return normalizeString(node?.id || node?.occurrenceId);
}

export function stepTreeNodeLabel(node) {
  return normalizeString(
    node?.displayName ||
    node?.name ||
    node?.label ||
    node?.sourcePath && basename(node.sourcePath) ||
    node?.partSourcePath && basename(node.partSourcePath) ||
    node?.id,
    "STEP"
  );
}

export function stepTreeNodeDetail(node) {
  return normalizeString(node?.detail || node?.summary || node?.shortSummary);
}

export function stepTreeNodeChildren(node) {
  return Array.isArray(node?.children) ? node.children : [];
}

export function stepTreeNodeTopologyType(node) {
  const nodeType = normalizeString(node?.nodeType);
  if (!nodeType.startsWith("topology-")) {
    return "";
  }
  return nodeType.slice("topology-".length);
}

export function stepTreeNodeIsTopology(node) {
  return Boolean(stepTreeNodeTopologyType(node));
}

export function stepTreeNodeHasChildren(node) {
  return stepTreeNodeChildren(node).length > 0;
}

export function stepTreeNodeLeafPartIds(node) {
  const declaredLeafPartIds = Array.isArray(node?.leafPartIds)
    ? node.leafPartIds.map((id) => normalizeString(id)).filter(Boolean)
    : [];
  if (declaredLeafPartIds.length) {
    return [...new Set(declaredLeafPartIds)];
  }
  const nodeType = normalizeString(node?.nodeType);
  const nodeId = stepTreeNodeId(node);
  if (nodeType === "part" && nodeId) {
    return [nodeId];
  }
  const leafPartIds = [];
  const stack = [...stepTreeNodeChildren(node)].reverse();
  while (stack.length) {
    const child = stack.pop();
    const childNodeType = normalizeString(child?.nodeType);
    const children = stepTreeNodeChildren(child);
    if (children.length) {
      for (let index = children.length - 1; index >= 0; index -= 1) {
        stack.push(children[index]);
      }
      continue;
    }
    if (childNodeType === "part") {
      const childId = stepTreeNodeId(child);
      if (childId) {
        leafPartIds.push(childId);
      }
    }
  }
  return [...new Set(leafPartIds)];
}

export function buildStepPartRoot({ selectedEntry = null, meshData = null } = {}) {
  const label = normalizeString(
    selectedEntry?.file && basename(selectedEntry.file) ||
    "STEP part"
  );
  return {
    id: STEP_MODEL_ROOT_ID,
    occurrenceId: "",
    nodeType: "part",
    displayName: label,
    name: label,
    sourceKind: "entry",
    leafPartIds: [STEP_MODEL_RENDER_PART_ID],
    bbox: meshData?.bounds || null,
    children: []
  };
}

export function buildStepTreeRoot({ selectedEntry = null, assemblyRoot = null, meshData = null } = {}) {
  if (assemblyRoot && typeof assemblyRoot === "object") {
    return assemblyRoot;
  }
  if (!meshData) {
    return null;
  }
  return buildStepPartRoot({ selectedEntry, meshData });
}

function nodeMatchesQuery(node, query) {
  if (!query) {
    return true;
  }
  const normalizedQuery = normalizeString(query).toLowerCase();
  if (!normalizedQuery) {
    return true;
  }
  const haystack = [
    stepTreeNodeLabel(node),
    stepTreeNodeDetail(node),
    stepTreeNodeId(node),
    node?.occurrenceId,
    node?.topologyReferenceId,
    node?.displaySelector,
    node?.sourcePath,
    node?.partSourcePath
  ].map((value) => normalizeString(value).toLowerCase()).join(" ");
  return haystack.includes(normalizedQuery);
}

function topologyReferenceSelector(reference) {
  return normalizeString(reference?.displaySelector || reference?.normalizedSelector || reference?.id);
}

function topologySelectorToken(selector) {
  const normalizedSelector = normalizeString(selector);
  if (!normalizedSelector) {
    return "";
  }
  return normalizedSelector.split(".").filter(Boolean).pop() || normalizedSelector;
}

function topologyOccurrenceIdFromSelector(selector) {
  const normalizedSelector = normalizeString(selector);
  if (!normalizedSelector) {
    return "";
  }
  const match = normalizedSelector.match(/^(.*)\.[sfe]\d+$/i);
  return match ? match[1] : normalizedSelector;
}

function topologyReferenceOccurrenceId(reference) {
  const selectorType = normalizeString(reference?.selectorType);
  if (selectorType === "occurrence") {
    return topologyReferenceSelector(reference);
  }
  return normalizeString(reference?.occurrenceId) ||
    topologyOccurrenceIdFromSelector(topologyReferenceSelector(reference));
}

function topologyReferenceName(reference) {
  const pickData = reference?.pickData && typeof reference.pickData === "object"
    ? reference.pickData
    : {};
  return normalizeString(
    reference?.name ||
    reference?.sourceName ||
    pickData.name ||
    pickData.sourceName
  );
}

function topologyReferenceLabel(reference) {
  const selectorType = normalizeString(reference?.selectorType);
  const selector = topologyReferenceSelector(reference);
  const selectorToken = topologySelectorToken(selector);
  const name = topologyReferenceName(reference);
  const summary = normalizeString(reference?.summary || reference?.shortSummary);

  if (selectorType === "occurrence") {
    return summary || name || selector || "Occurrence";
  }
  if (selectorType === "shape") {
    return name || (selectorToken ? `Shape ${selectorToken}` : "Shape");
  }
  if (selectorType === "face") {
    return selectorToken ? `Face ${selectorToken}` : "Face";
  }
  if (selectorType === "edge") {
    return selectorToken ? `Edge ${selectorToken}` : "Edge";
  }
  return summary || selector || "Topology";
}

function topologyReferenceDetail(reference) {
  const selectorType = normalizeString(reference?.selectorType);
  const selector = topologyReferenceSelector(reference);
  const label = topologyReferenceLabel(reference);
  const summary = normalizeString(reference?.summary || reference?.shortSummary);
  if (selectorType === "occurrence") {
    return summary && summary !== selector && summary !== label ? selector : "";
  }
  if (selectorType === "shape") {
    return summary && summary !== label ? summary : selector;
  }
  return summary;
}

function topologyNodeId(partId, selectorType, selector) {
  return `${STEP_TREE_TOPOLOGY_NODE_PREFIX}${partId || "part"}:${selectorType}:${selector || "item"}`;
}

function compareTopologyReferences(a, b) {
  const aRowIndex = Number(a?.rowIndex);
  const bRowIndex = Number(b?.rowIndex);
  if (Number.isFinite(aRowIndex) && Number.isFinite(bRowIndex) && aRowIndex !== bRowIndex) {
    return aRowIndex - bRowIndex;
  }
  if (Number.isFinite(aRowIndex)) {
    return -1;
  }
  if (Number.isFinite(bRowIndex)) {
    return 1;
  }
  return topologyReferenceSelector(a).localeCompare(topologyReferenceSelector(b));
}

function buildTopologyReferenceNode({ reference, selectorType, partId, occurrenceId }) {
  const selector = topologyReferenceSelector(reference);
  return {
    id: topologyNodeId(partId, selectorType, selector || normalizeString(reference?.id)),
    nodeType: `topology-${selectorType}`,
    displayName: topologyReferenceLabel(reference),
    detail: topologyReferenceDetail(reference),
    topologyReferenceId: normalizeString(reference?.id),
    displaySelector: selector,
    partId,
    occurrenceId,
    shapeId: normalizeString(reference?.shapeId),
    children: []
  };
}

function buildSyntheticOccurrenceNode({ partId, occurrenceId, children }) {
  const id = topologyNodeId(partId, "occurrence", occurrenceId);
  return {
    id,
    nodeType: "topology-occurrence",
    displayName: occurrenceId || "Occurrence",
    detail: "",
    topologyReferenceId: id,
    displaySelector: occurrenceId,
    partId,
    occurrenceId,
    children
  };
}

function topologySelectorAliases(value) {
  const normalizedValue = normalizeString(value);
  if (!normalizedValue) {
    return [];
  }
  const aliases = [normalizedValue];
  if (normalizedValue.startsWith("#")) {
    aliases.push(normalizedValue.slice(1));
  }
  if (normalizedValue.startsWith(STEP_TREE_TOPOLOGY_NODE_PREFIX)) {
    const internalSelector = normalizeString(normalizedValue.split(":").pop());
    if (internalSelector) {
      aliases.push(internalSelector);
    }
  }
  return [...new Set(aliases.filter(Boolean))];
}

function topologyOccurrenceNodeIsRedundantForPart(partNode, occurrenceNode, siblingCount) {
  if (normalizeString(occurrenceNode?.nodeType) !== "topology-occurrence") {
    return false;
  }
  if (siblingCount === 1) {
    return true;
  }
  return topologyOccurrenceNodeDuplicatesPart(partNode, occurrenceNode);
}

function topologyOccurrenceNodeDuplicatesPart(partNode, occurrenceNode) {
  if (normalizeString(occurrenceNode?.nodeType) !== "topology-occurrence") {
    return false;
  }
  const occurrenceId = normalizeString(occurrenceNode?.occurrenceId || occurrenceNode?.displaySelector);
  if (!occurrenceId) {
    return false;
  }
  const partSelectors = [
    stepTreeNodeId(partNode),
    partNode?.occurrenceId,
    partNode?.sourceOccurrenceId,
    partNode?.sourceRootTargetOccurrenceId,
    partNode?.topologyReferenceId,
    partNode?.displaySelector,
    partNode?.displayName,
    partNode?.name,
    partNode?.label
  ].flatMap(topologySelectorAliases);
  const occurrenceSelectors = [
    occurrenceId,
    stepTreeNodeId(occurrenceNode),
    occurrenceNode?.topologyReferenceId,
    occurrenceNode?.displaySelector,
    occurrenceNode?.displayName,
    occurrenceNode?.name,
    occurrenceNode?.label
  ].flatMap(topologySelectorAliases);
  return occurrenceSelectors.some((selector) => partSelectors.includes(selector));
}

function flattenRedundantTopologyOccurrenceNodes(partNode, topologyChildren) {
  const children = Array.isArray(topologyChildren) ? topologyChildren : [];
  return children.flatMap((child) => (
    topologyOccurrenceNodeIsRedundantForPart(partNode, child, children.length)
      ? stepTreeNodeChildren(child)
      : [child]
  ));
}

function topologyReferencePartId(reference, fallbackPartId) {
  return normalizeString(reference?.partId) || normalizeString(fallbackPartId);
}

function addStepTreeTopologyPartTarget(targets, seenTargets, partId, occurrenceId) {
  const normalizedPartId = normalizeString(partId);
  const normalizedOccurrenceId = normalizeString(occurrenceId);
  if (!normalizedPartId || !normalizedOccurrenceId) {
    return;
  }
  const key = `${normalizedPartId}\0${normalizedOccurrenceId}`;
  if (seenTargets.has(key)) {
    return;
  }
  seenTargets.add(key);
  targets.push({
    partId: normalizedPartId,
    occurrenceId: normalizedOccurrenceId
  });
}

function collectStepTreeTopologyPartTargets(root) {
  const targets = [];
  const seenTargets = new Set();
  const stack = root ? [root] : [];

  while (stack.length) {
    const node = stack.pop();
    const children = stepTreeNodeChildren(node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }

    if (normalizeString(node?.nodeType) !== "part") {
      continue;
    }

    const partId = stepTreeNodeId(node);
    if (!partId) {
      continue;
    }

    addStepTreeTopologyPartTarget(targets, seenTargets, partId, partId);
    addStepTreeTopologyPartTarget(targets, seenTargets, partId, node?.occurrenceId);
    addStepTreeTopologyPartTarget(targets, seenTargets, partId, node?.sourceOccurrenceId);
    addStepTreeTopologyPartTarget(targets, seenTargets, partId, node?.sourceRootTargetOccurrenceId);
    for (const leafPartId of stepTreeNodeLeafPartIds(node)) {
      addStepTreeTopologyPartTarget(targets, seenTargets, partId, leafPartId);
    }
  }

  return targets.sort((a, b) => b.occurrenceId.length - a.occurrenceId.length);
}

function occurrenceMatchesStepTreePartTarget(occurrenceId, targetOccurrenceId) {
  const normalizedOccurrenceId = normalizeString(occurrenceId);
  const normalizedTargetOccurrenceId = normalizeString(targetOccurrenceId);
  return Boolean(
    normalizedOccurrenceId &&
    normalizedTargetOccurrenceId &&
    (
      normalizedOccurrenceId === normalizedTargetOccurrenceId ||
      normalizedOccurrenceId.startsWith(`${normalizedTargetOccurrenceId}.`)
    )
  );
}

export function assignStepTreeTopologyReferencePartIds(root = null, references = []) {
  const normalizedReferences = Array.isArray(references) ? references : [];
  const targets = collectStepTreeTopologyPartTargets(root);
  if (!normalizedReferences.length || !targets.length) {
    return normalizedReferences;
  }

  let changed = false;
  const assignedReferences = normalizedReferences.map((reference) => {
    if (!reference || typeof reference !== "object" || normalizeString(reference.partId)) {
      return reference;
    }
    const occurrenceId = topologyReferenceOccurrenceId(reference);
    const target = targets.find((candidate) => (
      occurrenceMatchesStepTreePartTarget(occurrenceId, candidate.occurrenceId)
    ));
    if (!target) {
      return reference;
    }
    changed = true;
    return {
      ...reference,
      partId: target.partId
    };
  });

  return changed ? assignedReferences : normalizedReferences;
}

function buildTopologyChildrenByPart(references, fallbackPartId) {
  const byPart = new Map();
  for (const reference of Array.isArray(references) ? references : []) {
    const selectorType = normalizeString(reference?.selectorType);
    if (!STEP_TREE_TOPOLOGY_SELECTOR_TYPES.has(selectorType)) {
      continue;
    }
    const partId = topologyReferencePartId(reference, fallbackPartId);
    const occurrenceId = topologyReferenceOccurrenceId(reference);
    if (!partId || !occurrenceId) {
      continue;
    }
    let partGroup = byPart.get(partId);
    if (!partGroup) {
      partGroup = new Map();
      byPart.set(partId, partGroup);
    }
    let occurrenceGroup = partGroup.get(occurrenceId);
    if (!occurrenceGroup) {
      occurrenceGroup = {
        occurrence: null,
        shapes: [],
        faces: [],
        edges: []
      };
      partGroup.set(occurrenceId, occurrenceGroup);
    }
    if (selectorType === "occurrence") {
      occurrenceGroup.occurrence = reference;
    } else if (selectorType === "shape") {
      occurrenceGroup.shapes.push(reference);
    } else if (selectorType === "face") {
      occurrenceGroup.faces.push(reference);
    } else if (selectorType === "edge") {
      occurrenceGroup.edges.push(reference);
    }
  }

  return new Map([...byPart.entries()].map(([partId, occurrenceGroups]) => {
    const occurrenceNodes = [...occurrenceGroups.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([occurrenceId, group]) => {
        const children = [
          ...group.shapes.sort(compareTopologyReferences).map((reference) => buildTopologyReferenceNode({
            reference,
            selectorType: "shape",
            partId,
            occurrenceId
          })),
          ...group.faces.sort(compareTopologyReferences).map((reference) => buildTopologyReferenceNode({
            reference,
            selectorType: "face",
            partId,
            occurrenceId
          })),
          ...group.edges.sort(compareTopologyReferences).map((reference) => buildTopologyReferenceNode({
            reference,
            selectorType: "edge",
            partId,
            occurrenceId
          }))
        ];
        if (group.occurrence) {
          return {
            ...buildTopologyReferenceNode({
              reference: group.occurrence,
              selectorType: "occurrence",
              partId,
              occurrenceId
            }),
            children
          };
        }
        return buildSyntheticOccurrenceNode({ partId, occurrenceId, children });
      });
    return [partId, occurrenceNodes];
  }));
}

export function buildStepTreeRootWithTopology({ root = null, references = [], fallbackPartId = "" } = {}) {
  if (!root || typeof root !== "object") {
    return root;
  }
  const topologyChildrenByPart = buildTopologyChildrenByPart(references, fallbackPartId || stepTreeNodeId(root));
  if (!topologyChildrenByPart.size) {
    return root;
  }

  function cloneWithTopology(node) {
    const id = stepTreeNodeId(node);
    const children = stepTreeNodeChildren(node).map((child) => cloneWithTopology(child));
    const topologyChildren = normalizeString(node?.nodeType) === "part"
      ? flattenRedundantTopologyOccurrenceNodes(node, topologyChildrenByPart.get(id) || [])
      : [];
    if (!children.length && !topologyChildren.length) {
      return node;
    }
    return {
      ...node,
      children: [...children, ...topologyChildren]
    };
  }

  return cloneWithTopology(root);
}

function subtreeMatchesQuery(node, query) {
  if (!query || nodeMatchesQuery(node, query)) {
    return true;
  }
  return stepTreeNodeChildren(node).some((child) => subtreeMatchesQuery(child, query));
}

function subtreeContainsNodeId(node, nodeId) {
  const normalizedNodeId = normalizeString(nodeId);
  if (!node || !normalizedNodeId) {
    return false;
  }
  if (stepTreeNodeId(node) === normalizedNodeId) {
    return true;
  }
  return stepTreeNodeChildren(node).some((child) => subtreeContainsNodeId(child, normalizedNodeId));
}

export function stepTreeRootChildIndexForNode(root, nodeId) {
  const normalizedNodeId = normalizeString(nodeId);
  if (!root || !normalizedNodeId) {
    return -1;
  }
  const children = stepTreeNodeChildren(root);
  for (let index = 0; index < children.length; index += 1) {
    if (subtreeContainsNodeId(children[index], normalizedNodeId)) {
      return index;
    }
  }
  return -1;
}

export function flattenVisibleStepTreeRows(root, expandedNodeIds = [], {
  query = "",
  omitRoot = false,
  rootChildLimit = null,
  showAllRootChildren = true
} = {}) {
  if (!root) {
    return [];
  }
  const expanded = new Set(
    (Array.isArray(expandedNodeIds) ? expandedNodeIds : [])
      .map((id) => normalizeString(id))
      .filter(Boolean)
  );
  const normalizedQuery = normalizeString(query).toLowerCase();
  const normalizedRootChildLimit = normalizePositiveInteger(rootChildLimit);
  const limitRootChildren = Boolean(
    normalizedRootChildLimit &&
    showAllRootChildren !== true &&
    !normalizedQuery
  );
  const rows = [];

  function rootChildrenForVisit(children) {
    return limitRootChildren
      ? children.slice(0, normalizedRootChildLimit)
      : children;
  }

  function visit(node, depth, options = {}, parentNode = null) {
    if (normalizedQuery && !subtreeMatchesQuery(node, normalizedQuery)) {
      return;
    }
    const id = stepTreeNodeId(node);
    const children = stepTreeNodeChildren(node);
    const hasChildren = children.length > 0;
    const expandedByQuery = Boolean(normalizedQuery && hasChildren);
    const isExpanded = expandedByQuery || expanded.has(id);
    const elideRedundantTopologyOccurrence = parentNode &&
      topologyOccurrenceNodeDuplicatesPart(parentNode, node);
    if (!elideRedundantTopologyOccurrence) {
      rows.push({
        id,
        node,
        label: stepTreeNodeLabel(node),
        detail: stepTreeNodeDetail(node),
        nodeType: normalizeString(node?.nodeType),
        topologyType: stepTreeNodeTopologyType(node),
        topologyReferenceId: normalizeString(node?.topologyReferenceId),
        depth,
        hasChildren,
        expanded: isExpanded,
        leafPartIds: stepTreeNodeLeafPartIds(node)
      });
    }
    if (!hasChildren || (!isExpanded && !elideRedundantTopologyOccurrence)) {
      return;
    }
    const childRows = options.isRoot ? rootChildrenForVisit(children) : children;
    for (const child of childRows) {
      visit(child, elideRedundantTopologyOccurrence ? depth : depth + 1, {}, node);
    }
  }

  if (omitRoot) {
    for (const child of rootChildrenForVisit(stepTreeNodeChildren(root))) {
      visit(child, 0, {}, root);
    }
  } else {
    visit(root, 0, { isRoot: true });
  }
  return rows;
}

export function collectStepTreeAncestorIds(root, nodeId) {
  const normalizedNodeId = normalizeString(nodeId);
  if (!root || !normalizedNodeId) {
    return [];
  }
  const path = [];
  function visit(node) {
    const id = stepTreeNodeId(node);
    path.push(id);
    if (id === normalizedNodeId) {
      return true;
    }
    for (const child of stepTreeNodeChildren(node)) {
      if (visit(child)) {
        return true;
      }
    }
    path.pop();
    return false;
  }
  return visit(root) ? path.slice(0, -1).filter(Boolean) : [];
}
