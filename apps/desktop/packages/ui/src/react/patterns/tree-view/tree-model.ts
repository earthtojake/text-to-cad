export interface TreeNode<T> {
  id: string;
  data: T;
  children?: readonly TreeNode<T>[];
}

export interface TreeRow<T> {
  node: TreeNode<T>;
  depth: number;
  chain: readonly TreeNode<T>[];
  isBranch: boolean;
  isExpanded: boolean;
}

export interface BuildVisibleTreeRowsOptions {
  compactChains?: boolean;
}

export function isTreeBranch<T>(node: TreeNode<T>): boolean {
  return node.children !== undefined;
}

export function isChainExpanded<T>(
  chain: readonly TreeNode<T>[],
  expandedIds: ReadonlySet<string>
): boolean {
  return chain.every((segment) => expandedIds.has(segment.id));
}

export function buildVisibleTreeRows<T>(
  nodes: readonly TreeNode<T>[],
  expandedIds: ReadonlySet<string>,
  options: BuildVisibleTreeRowsOptions = {}
): TreeRow<T>[] {
  const rows: TreeRow<T>[] = [];
  appendRows(rows, nodes, expandedIds, 0, options);
  return rows;
}

function appendRows<T>(
  rows: TreeRow<T>[],
  nodes: readonly TreeNode<T>[],
  expandedIds: ReadonlySet<string>,
  depth: number,
  options: BuildVisibleTreeRowsOptions
) {
  for (const node of nodes) {
    const chain = options.compactChains ? buildCompactChain(node) : [node];
    const rowNode = chain[chain.length - 1]!;
    const isBranch = isTreeBranch(rowNode);
    const isExpanded = isBranch && isChainExpanded(chain, expandedIds);

    rows.push({
      node: rowNode,
      depth,
      chain,
      isBranch,
      isExpanded,
    });

    if (isExpanded && rowNode.children) {
      appendRows(rows, rowNode.children, expandedIds, depth + 1, options);
    }
  }
}

function buildCompactChain<T>(node: TreeNode<T>): TreeNode<T>[] {
  const chain = [node];
  let current = node;

  while (isTreeBranch(current) && current.children?.length === 1) {
    const child = current.children[0]!;
    if (!isTreeBranch(child)) break;
    chain.push(child);
    current = child;
  }

  return chain;
}
