import {
  findAssemblyNode
} from "@hardcore/core/lib/assembly/meshData.js";

export function assemblyPathToNode(root, nodeId) {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!root || !normalizedNodeId) {
    return [];
  }
  const rootId = String(root?.id || "").trim();
  if (normalizedNodeId === rootId || normalizedNodeId === "root") {
    return [root];
  }
  const stack = [{ node: root, path: [root] }];
  while (stack.length) {
    const { node, path } = stack.pop();
    if (String(node?.id || "").trim() === normalizedNodeId) {
      return path;
    }
    const children = Array.isArray(node?.children) ? node.children : [];
    for (let index = children.length - 1; index >= 0; index -= 1) {
      const child = children[index];
      stack.push({ node: child, path: [...path, child] });
    }
  }
  return [];
}

export function assemblyNodeContainsNode(root, ancestorNodeId, descendantNodeId) {
  const normalizedAncestorNodeId = String(ancestorNodeId || "").trim();
  const normalizedDescendantNodeId = String(descendantNodeId || "").trim();
  if (!root || !normalizedAncestorNodeId || !normalizedDescendantNodeId) {
    return false;
  }
  return assemblyPathToNode(root, normalizedDescendantNodeId)
    .some((node) => String(node?.id || "").trim() === normalizedAncestorNodeId);
}

export function minimalAssemblyIsolationNodeIds(root, nodeIds, { rootId = "" } = {}) {
  if (!root) {
    return [];
  }
  const normalizedRootId = String(rootId || root?.id || "").trim();
  const candidates = [];
  const seen = new Set();
  for (const nodeId of Array.isArray(nodeIds) ? nodeIds : [nodeIds]) {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId || normalizedNodeId === normalizedRootId || seen.has(normalizedNodeId)) {
      continue;
    }
    const node = findAssemblyNode(root, normalizedNodeId);
    if (!node) {
      continue;
    }
    seen.add(normalizedNodeId);
    candidates.push(normalizedNodeId);
  }

  const roots = [];
  for (const candidate of candidates) {
    if (roots.some((rootNodeId) => assemblyNodeContainsNode(root, rootNodeId, candidate))) {
      continue;
    }
    for (let index = roots.length - 1; index >= 0; index -= 1) {
      if (assemblyNodeContainsNode(root, candidate, roots[index])) {
        roots.splice(index, 1);
      }
    }
    roots.push(candidate);
  }
  return roots;
}

function assemblyChildNodeIds(node, rootId) {
  const normalizedRootId = String(rootId || "").trim();
  return (Array.isArray(node?.children) ? node.children : [])
    .map((child) => String(child?.id || "").trim())
    .filter((nodeId) => nodeId && nodeId !== normalizedRootId);
}

export function assemblyIsolationLayerNodeIds(root, isolatedNodeIds, rootId) {
  if (!root) {
    return [];
  }
  const normalizedIsolatedNodeIds = minimalAssemblyIsolationNodeIds(root, isolatedNodeIds, {
    rootId
  });
  if (!normalizedIsolatedNodeIds.length) {
    return assemblyChildNodeIds(root, rootId);
  }
  const selectable = new Set();
  for (const nodeId of normalizedIsolatedNodeIds) {
    const node = findAssemblyNode(root, nodeId);
    for (const selectableNodeId of assemblyChildNodeIds(node, rootId)) {
      selectable.add(selectableNodeId);
    }
  }
  return [...selectable];
}

export function selectableViewerNodeIdsForIsolation(root, isolatedNodeIds, rootId) {
  if (!root) {
    return [];
  }
  return assemblyIsolationLayerNodeIds(root, isolatedNodeIds, rootId);
}

export function selectedReferenceIdsOutsideFocusedAssemblyNodes(referenceIds, referenceMap, focusedNodeIds, {
  referencePartId = null
} = {}) {
  const focused = new Set(
    (Array.isArray(focusedNodeIds) ? focusedNodeIds : [focusedNodeIds])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  if (!focused.size) {
    return Array.isArray(referenceIds) ? referenceIds : [];
  }
  const readReferencePartId = typeof referencePartId === "function"
    ? referencePartId
    : (reference) => String(reference?.partId || "").trim();
  return (Array.isArray(referenceIds) ? referenceIds : [])
    .map((id) => String(id || "").trim())
    .filter((id) => {
      if (!id) {
        return false;
      }
      const reference = referenceMap?.get?.(id) || null;
      const selectorType = String(reference?.selectorType || "").trim();
      if (selectorType !== "shape" && selectorType !== "occurrence") {
        return true;
      }
      const partId = String(readReferencePartId(reference) || "").trim();
      return !partId || !focused.has(partId);
    });
}

export function selectableViewerNodeIdsForExpandedTree(root, expandedNodeIds, {
  rootId = "",
  isolatedNodeIds = []
} = {}) {
  if (!root) {
    return [];
  }
  const normalizedRootId = String(rootId || root?.id || "").trim();
  const expanded = new Set(
    (Array.isArray(expandedNodeIds) ? expandedNodeIds : [expandedNodeIds])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const isolationRoots = minimalAssemblyIsolationNodeIds(root, isolatedNodeIds, {
    rootId: normalizedRootId
  });
  const startNodes = isolationRoots.length
    ? isolationRoots.map((nodeId) => findAssemblyNode(root, nodeId)).filter(Boolean)
    : [root];
  const selectable = [];
  const seen = new Set();

  const addSelectable = (nodeId) => {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId || normalizedNodeId === normalizedRootId || seen.has(normalizedNodeId)) {
      return;
    }
    seen.add(normalizedNodeId);
    selectable.push(normalizedNodeId);
  };

  const visit = (node, { forceChildren = false } = {}) => {
    if (!node) {
      return;
    }
    const nodeId = String(node?.id || "").trim();
    const children = Array.isArray(node?.children) ? node.children : [];
    const expandedNode = nodeId && expanded.has(nodeId);
    if (children.length && (forceChildren || expandedNode || nodeId === normalizedRootId)) {
      for (const child of children) {
        visit(child);
      }
      return;
    }
    addSelectable(nodeId);
  };

  for (const node of startNodes) {
    visit(node, { forceChildren: !isolationRoots.length || expanded.has(String(node?.id || "").trim()) });
  }

  return selectable;
}
