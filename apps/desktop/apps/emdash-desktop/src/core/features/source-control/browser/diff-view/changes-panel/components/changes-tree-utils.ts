import type { GitChange } from '@emdash/core/runtimes/git/api';
import {
  makeNode,
  normalizeFileTreePath,
  sortFileNodes,
  type NestedFileNode,
} from '@core/features/editor/api/browser/file-tree/tree-utils';

export interface ChangesTree {
  rootNodes: NestedFileNode[];
  changeByPath: Map<string, GitChange>;
  directoryPaths: Set<string>;
}

export function buildChangesTree(changes: GitChange[], rootPath?: string): ChangesTree {
  const nodesByPath = new Map<string, NestedFileNode>();
  const changeByPath = new Map<string, GitChange>();
  const directoryPaths = new Set<string>();
  const rootNodes: NestedFileNode[] = [];
  const normalizedRoot = rootPath ? normalizeFileTreePath(rootPath) : null;

  for (const change of changes) {
    const identityPath = normalizeFileTreePath(change.path);
    const displayPath = displayPathForChange(identityPath, normalizedRoot);
    changeByPath.set(displayPath, change);

    const parts = displayPath.split('/').filter(Boolean);
    if (parts.length === 0) continue;

    let prefix = displayPath.startsWith('/') ? '/' : '';
    let parentNode: NestedFileNode | null = null;
    for (let i = 0; i < parts.length; i++) {
      const segment = parts[i]!;
      prefix = prefix === '/' ? `/${segment}` : prefix ? `${prefix}/${segment}` : segment;
      const isLeaf = i === parts.length - 1;
      const type = isLeaf ? 'file' : 'directory';
      const key = `${type}:${prefix}`;

      let node = nodesByPath.get(key);
      if (!node) {
        node = makeNode(prefix, type);
        nodesByPath.set(key, node);
        if (!isLeaf) directoryPaths.add(prefix);
        if (parentNode) {
          parentNode.children.push(node);
        } else {
          rootNodes.push(node);
        }
      }
      parentNode = node;
    }
  }

  return {
    rootNodes: sortRecursively(rootNodes),
    changeByPath,
    directoryPaths,
  };
}

export function displayPathForChange(identityPath: string, rootPath?: string | null): string {
  const normalizedPath = normalizeFileTreePath(identityPath);
  if (!rootPath) return normalizedPath;
  const normalizedRoot = normalizeFileTreePath(rootPath);
  if (normalizedPath === normalizedRoot) return normalizedPath;
  const prefix = `${normalizedRoot}/`;
  return normalizedPath.startsWith(prefix) ? normalizedPath.slice(prefix.length) : normalizedPath;
}

function sortRecursively(nodes: NestedFileNode[]): NestedFileNode[] {
  const sorted = sortFileNodes(nodes);
  for (const node of sorted) {
    if (node.children.length > 0) {
      node.children = sortRecursively(node.children);
    }
  }
  return sorted;
}
