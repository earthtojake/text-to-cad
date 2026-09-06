import type { TreeNode } from '../../patterns/tree-view';

export type FileTreeNodeType = 'file' | 'directory' | 'symlink';
export type FileTreeSymlinkTargetKind = 'file' | 'directory' | 'other' | 'missing' | 'outside-root';

export interface FileTreeNode {
  id: string;
  path: string;
  name: string;
  parentId: string | null;
  parentPath: string | null;
  depth: number;
  type: FileTreeNodeType;
  symlink?: boolean;
  symlinkTargetKind?: FileTreeSymlinkTargetKind;
  childrenLoaded?: boolean;
  isHidden?: boolean;
  extension?: string;
}

export type ChildrenById = ReadonlyMap<string | null, readonly FileTreeNode[]>;

export interface FileTreeFlatRow {
  node: FileTreeNode;
  directory: string;
}

export interface FileTreeDropTarget {
  targetDir: FileTreeNode | null;
  targetDirPath: string;
}

export function buildFileTreeNodes(
  rootNodes: readonly FileTreeNode[],
  childrenById: ChildrenById
): TreeNode<FileTreeNode>[] {
  return sortFileNodes(rootNodes).map((node) => toTreeNode(node, childrenById));
}

export function buildFlatFileRows(
  rootNodes: readonly FileTreeNode[],
  childrenById: ChildrenById
): FileTreeFlatRow[] {
  const rows: FileTreeFlatRow[] = [];
  appendFlatRows(rows, sortFileNodes(rootNodes), childrenById);
  return rows;
}

export function sortFileNodes(nodes: readonly FileTreeNode[]): FileTreeNode[] {
  return [...nodes].sort((a, b) => {
    const aDir = isExpandableFileTreeNode(a);
    const bDir = isExpandableFileTreeNode(b);
    if (aDir !== bDir) return aDir ? -1 : 1;
    return a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true });
  });
}

export function isExpandableFileTreeNode(node: FileTreeNode): boolean {
  return (
    node.type === 'directory' || (node.type === 'symlink' && node.symlinkTargetKind === 'directory')
  );
}

export function isOpenableFileTreeNode(node: FileTreeNode): boolean {
  return (
    node.type === 'file' || (node.type === 'symlink' && node.symlinkTargetKind !== 'directory')
  );
}

export function normalizeFileTreePath(path: string): string {
  const normalized = path.replaceAll('\\', '/').replace(/\/+/g, '/');
  if (normalized === '.') return '';
  if (normalized.length > 1 && normalized.endsWith('/')) return normalized.slice(0, -1);
  return normalized;
}

export function joinFileTreePath(parentPath: string, name: string): string {
  const parent = normalizeFileTreePath(parentPath);
  const child = normalizeFileTreePath(name);
  if (!parent || parent === '/') return parent === '/' ? `/${child}` : child;
  return `${parent}/${child}`;
}

export function parentPathFor(path: string, rootPath = ''): string {
  const normalized = normalizeFileTreePath(path);
  const root = normalizeFileTreePath(rootPath);
  if (!normalized || normalized === root) return root;
  const slash = normalized.lastIndexOf('/');
  if (slash < 0) return root;
  if (slash === 0) return '/';
  return normalized.slice(0, slash);
}

/**
 * Ancestor directory paths between `rootPath` (exclusive) and `path` (exclusive),
 * ordered outermost first. Compacted rows need every chained segment expanded, and
 * a visible row's only collapsed ancestors are the segments merged into that row.
 */
export function ancestorPathsFor(path: string, rootPath = ''): string[] {
  const root = normalizeFileTreePath(rootPath);
  const ancestors: string[] = [];
  let current = parentPathFor(path, rootPath);

  while (current && current !== root) {
    ancestors.push(current);
    const next = parentPathFor(current, rootPath);
    if (next === current) break;
    current = next;
  }

  return ancestors.reverse();
}

export function creationTargetPath(
  selectedNode: FileTreeNode | null | undefined,
  rootPath: string
): string {
  const root = normalizeFileTreePath(rootPath);
  if (!selectedNode) return root;
  if (isExpandableFileTreeNode(selectedNode)) return normalizeFileTreePath(selectedNode.path);
  return normalizeFileTreePath(selectedNode.parentPath ?? root);
}

export function resolveDropTargetDir(
  targetNode: FileTreeNode | null | undefined,
  nodesByPath: ReadonlyMap<string, FileTreeNode>,
  rootPath: string
): FileTreeDropTarget {
  const root = normalizeFileTreePath(rootPath);
  if (!targetNode) return { targetDir: null, targetDirPath: root };
  if (isExpandableFileTreeNode(targetNode)) {
    return { targetDir: targetNode, targetDirPath: normalizeFileTreePath(targetNode.path) };
  }
  const parentPath = normalizeFileTreePath(targetNode.parentPath ?? root);
  return { targetDir: nodesByPath.get(parentPath) ?? null, targetDirPath: parentPath };
}

export function canMoveNode(sourcePath: string, targetDirPath: string, rootPath = ''): boolean {
  const source = normalizeFileTreePath(sourcePath);
  const target = normalizeFileTreePath(targetDirPath);
  if (!source) return false;
  if (source === target) return false;
  if (parentPathFor(source, rootPath) === target) return false;
  return !isDescendantPath(target, source);
}

export function isDescendantPath(candidatePath: string, ancestorPath: string): boolean {
  const candidate = normalizeFileTreePath(candidatePath);
  const ancestor = normalizeFileTreePath(ancestorPath);
  if (!candidate || !ancestor || candidate === ancestor) return false;
  const prefix = ancestor.endsWith('/') ? ancestor : `${ancestor}/`;
  return candidate.startsWith(prefix);
}

export function selectionRange(
  visiblePaths: readonly string[],
  anchorPath: string | null | undefined,
  targetPath: string
): string[] {
  const target = normalizeFileTreePath(targetPath);
  const anchor = anchorPath ? normalizeFileTreePath(anchorPath) : target;
  const targetIndex = visiblePaths.findIndex((path) => normalizeFileTreePath(path) === target);
  const anchorIndex = visiblePaths.findIndex((path) => normalizeFileTreePath(path) === anchor);
  if (targetIndex < 0) return [target];
  if (anchorIndex < 0) return [target];
  const start = Math.min(anchorIndex, targetIndex);
  const end = Math.max(anchorIndex, targetIndex);
  return visiblePaths.slice(start, end + 1).map(normalizeFileTreePath);
}

export function dedupeDescendantPaths(paths: readonly string[]): string[] {
  const sorted = [...new Set(paths.map(normalizeFileTreePath))]
    .filter(Boolean)
    .sort((left, right) => left.length - right.length || left.localeCompare(right));
  const deduped: string[] = [];
  for (const path of sorted) {
    if (deduped.some((ancestor) => path === ancestor || isDescendantPath(path, ancestor))) continue;
    deduped.push(path);
  }
  return deduped;
}

function toTreeNode(node: FileTreeNode, childrenById: ChildrenById): TreeNode<FileTreeNode> {
  if (!isExpandableFileTreeNode(node)) return { id: node.id, data: node };
  const children = sortFileNodes(childrenById.get(node.id) ?? []).map((child) =>
    toTreeNode(child, childrenById)
  );
  return { id: node.id, data: node, children };
}

function appendFlatRows(
  rows: FileTreeFlatRow[],
  nodes: readonly FileTreeNode[],
  childrenById: ChildrenById
) {
  for (const node of nodes) {
    if (isOpenableFileTreeNode(node)) {
      rows.push({ node, directory: directoryLabel(node) });
      continue;
    }
    appendFlatRows(rows, sortFileNodes(childrenById.get(node.id) ?? []), childrenById);
  }
}

function directoryLabel(node: FileTreeNode): string {
  const parentPath = node.parentPath ? normalizeFileTreePath(node.parentPath) : '';
  return parentPath;
}
