import { cx } from '@styles/utilities/cx';
import { useVirtualizer } from '@tanstack/react-virtual';
import * as React from 'react';
import { buildVisibleTreeRows, type TreeNode, type TreeRow } from './tree-model';
import * as styles from './tree-view.css';

export interface TreeViewHandle {
  scrollToId(id: string, opts?: { align?: 'auto' | 'start' | 'center' | 'end' }): void;
}

export interface TreeViewProps<T> {
  nodes: readonly TreeNode<T>[];
  expandedIds: ReadonlySet<string>;
  onExpandedChange?: (ids: ReadonlySet<string>) => void;
  renderRow: (row: TreeRow<T>) => React.ReactNode;
  wrapRow?: (row: TreeRow<T>, element: React.ReactNode) => React.ReactNode;
  compactChains?: boolean;
  estimateSize?: number;
  gap?: number;
  overscan?: number;
  className?: string;
}

function TreeViewInner<T>(
  {
    nodes,
    expandedIds,
    renderRow,
    wrapRow,
    compactChains = false,
    estimateSize = 28,
    gap = 0,
    overscan = 5,
    className,
  }: TreeViewProps<T>,
  ref: React.ForwardedRef<TreeViewHandle>
) {
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const rows = React.useMemo(
    () => buildVisibleTreeRows(nodes, expandedIds, { compactChains }),
    [compactChains, expandedIds, nodes]
  );

  const getItemKey = React.useCallback((index: number) => treeRowKey(rows[index], index), [rows]);

  const virtualizer = useVirtualizer({
    count: rows.length,
    estimateSize: () => estimateSize,
    gap,
    getItemKey,
    getScrollElement: () => scrollRef.current,
    overscan,
  });

  React.useImperativeHandle(
    ref,
    () => ({
      scrollToId(id, opts) {
        const index = rows.findIndex(
          (row) => row.node.id === id || row.chain.some((segment) => segment.id === id)
        );
        if (index >= 0) virtualizer.scrollToIndex(index, opts);
      },
    }),
    [rows, virtualizer]
  );

  return (
    <div ref={scrollRef} className={cx(styles.scrollContainer, className)}>
      <div className={styles.spacer} style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map((virtualItem) => {
          const row = rows[virtualItem.index];
          if (!row) return null;
          const element = renderRow(row);
          return (
            <div
              key={treeRowKey(row, virtualItem.index)}
              className={styles.virtualRow}
              style={{
                height: virtualItem.size,
                transform: `translateY(${virtualItem.start}px)`,
              }}
            >
              {wrapRow ? wrapRow(row, element) : element}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function treeRowKey<T>(row: TreeRow<T> | undefined, index: number): string | number {
  if (!row) return index;
  return row.chain.map((segment) => segment.id).join('/');
}

export const TreeView = React.forwardRef(TreeViewInner) as <T>(
  props: TreeViewProps<T> & { ref?: React.Ref<TreeViewHandle> }
) => React.ReactElement;
