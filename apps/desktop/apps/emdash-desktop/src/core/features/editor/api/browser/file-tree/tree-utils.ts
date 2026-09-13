import type { FileEntry, FileEntryKind, SymlinkTargetKind } from '@emdash/core/runtimes/files/api';

export type FileNodeId = string;

export interface RenderableFileNode {
  id: FileNodeId;
  path: string;
  name: string;
  parentId: FileNodeId | null;
  parentPath: string | null;
  depth: number;
  type: FileEntryKind;
  symlink?: {
    target: string | null;
    targetType: SymlinkTargetKind;
    broken: boolean;
  };
  childrenLoaded: boolean;
  isHidden: boolean;
  extension?: string;
}

export interface NestedFileNode {
  path: string;
  name: string;
  parentPath: string | null;
  depth: number;
  type: 'file' | 'directory';
  children: NestedFileNode[];
  isHidden: boolean;
  extension?: string;
}

export type VisibleFileNode = RenderableFileNode | NestedFileNode;
export type ChildrenById<T extends VisibleFileNode = RenderableFileNode> = Map<
  FileNodeId | null,
  readonly T[]
>;

export function normalizeFileTreePath(path: string): string {
  const normalized = path.replace(/\\/g, '/').replace(/\/+/g, '/');
  if (normalized === '/') return normalized;
  return normalized.endsWith('/') ? normalized.slice(0, -1) : normalized;
}

export function makeNode(filePath: string, type: 'file' | 'directory'): NestedFileNode {
  const path = normalizeFileTreePath(filePath);
  const parts = path.split('/').filter(Boolean);
  const name = parts[parts.length - 1] ?? path;
  return {
    path,
    name,
    parentPath: parentPathForNormalizedPath(path),
    depth: parts.length - 1,
    type,
    children: [],
    isHidden: name.startsWith('.'),
    extension: type === 'file' && name.includes('.') ? name.split('.').pop() : undefined,
  };
}

export function toRenderableFileNode(entry: FileEntry, workspacePath: string): RenderableFileNode {
  const absolutePath = joinPath(workspacePath, entry.path);
  const name = entry.name || absolutePath.split('/').pop() || absolutePath;
  return {
    id: entry.path,
    path: absolutePath,
    name,
    parentId: entry.parentPath === '' || entry.parentPath === null ? null : entry.parentPath,
    parentPath:
      entry.parentPath === null
        ? null
        : entry.parentPath === ''
          ? workspacePath
          : joinPath(workspacePath, entry.parentPath),
    depth: entry.path.split('/').filter(Boolean).length - 1,
    type: entry.kind,
    symlink:
      entry.kind === 'symlink'
        ? {
            target: entry.symlinkTarget ?? null,
            targetType: entry.symlinkTargetKind ?? 'other',
            broken: entry.symlinkTargetKind === 'missing',
          }
        : undefined,
    childrenLoaded: entry.childrenLoaded,
    isHidden: name.startsWith('.'),
    extension: entry.kind === 'file' && name.includes('.') ? name.split('.').pop() : undefined,
  };
}

export function sortFileNodes<T extends VisibleFileNode>(nodes: readonly T[]): T[] {
  return [...nodes].sort((left, right) => {
    const rank = Number(isExpandableFileTreeNode(right)) - Number(isExpandableFileTreeNode(left));
    return rank || left.name.localeCompare(right.name);
  });
}

export function isExpandableFileTreeNode(node: VisibleFileNode): boolean {
  return (
    node.type === 'directory' ||
    (node.type === 'symlink' && node.symlink?.targetType === 'directory' && !node.symlink.broken)
  );
}

export function isOpenableFileTreeNode(node: VisibleFileNode): boolean {
  return (
    node.type === 'file' ||
    (node.type === 'symlink' && node.symlink?.targetType === 'file' && !node.symlink.broken)
  );
}

export interface TreeRow<T extends VisibleFileNode = VisibleFileNode> {
  node: T;
  chain: T[];
  renderDepth: number;
}

export function isChainExpanded<T extends VisibleFileNode>(
  chain: readonly T[],
  expandedPaths: Set<string>
): boolean {
  return chain.some((segment) => expandedPaths.has(segment.path));
}

export function buildFileTreeVisibleRows(
  rootNodes: readonly RenderableFileNode[],
  expandedPaths: Set<string>,
  childrenById: ChildrenById<RenderableFileNode>,
  _loadedPaths: ReadonlySet<string>
): Array<TreeRow<RenderableFileNode>> {
  const rows: Array<TreeRow<RenderableFileNode>> = [];
  const walk = (nodes: readonly RenderableFileNode[], renderDepth: number) => {
    for (const node of nodes) {
      const chain = [node];
      rows.push({ node, chain, renderDepth });
      if (isExpandableFileTreeNode(node) && isChainExpanded(chain, expandedPaths)) {
        walk(childrenById.get(node.id) ?? [], renderDepth + 1);
      }
    }
  };
  walk(rootNodes, 0);
  return rows;
}

export function buildNestedVisibleRows(
  rootNodes: readonly NestedFileNode[],
  expandedPaths: Set<string>
): Array<TreeRow<NestedFileNode>> {
  const rows: Array<TreeRow<NestedFileNode>> = [];
  const walk = (nodes: readonly NestedFileNode[], renderDepth: number) => {
    for (const node of nodes) {
      const chain = extendNestedDirectoryChain(node);
      const terminus = chain[chain.length - 1]!;
      rows.push({ node: terminus, chain, renderDepth });
      if (isExpandableFileTreeNode(terminus) && isChainExpanded(chain, expandedPaths)) {
        walk(terminus.children, renderDepth + 1);
      }
    }
  };
  walk(rootNodes, 0);
  return rows;
}

function extendNestedDirectoryChain(node: NestedFileNode): NestedFileNode[] {
  const chain = [node];
  const visited = new Set([node.path]);
  let current = node;
  while (
    current.type === 'directory' &&
    current.children.length === 1 &&
    current.children[0]?.type === 'directory' &&
    !visited.has(current.children[0].path)
  ) {
    current = current.children[0];
    visited.add(current.path);
    chain.push(current);
  }
  return chain;
}

function parentPathForNormalizedPath(path: string): string | null {
  const index = path.lastIndexOf('/');
  if (index < 0) return null;
  if (index === 0) return '/';
  return path.slice(0, index);
}

function joinPath(root: string, relative: string): string {
  return relative ? normalizeFileTreePath(`${root}/${relative}`) : normalizeFileTreePath(root);
}
