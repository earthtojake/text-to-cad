import {
  findAssemblyNode,
  flattenAssemblyNodes
} from "cadjs/lib/assembly/meshData.js";

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

export function selectableTreeNodeIdsForIsolation(root, isolatedNodeIds, rootId) {
  if (!root) {
    return [];
  }
  const rootNodeId = String(rootId || "").trim();
  const validNodeIds = (nodes) => flattenAssemblyNodes(nodes)
    .map((node) => String(node?.id || "").trim())
    .filter((nodeId) => nodeId && nodeId !== rootNodeId);
  const normalizedIsolatedNodeIds = minimalAssemblyIsolationNodeIds(root, isolatedNodeIds, {
    rootId
  });
  if (!normalizedIsolatedNodeIds.length) {
    return validNodeIds(root);
  }
  const selectable = new Set();
  for (const nodeId of normalizedIsolatedNodeIds) {
    const node = findAssemblyNode(root, nodeId);
    for (const selectableNodeId of validNodeIds(node)) {
      if (selectableNodeId === nodeId) {
        continue;
      }
      selectable.add(selectableNodeId);
    }
  }
  return [...selectable];
}
