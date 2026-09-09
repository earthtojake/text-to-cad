import { cx } from '@styles/utilities/cx';
import { useVirtualizer } from '@tanstack/react-virtual';
import * as React from 'react';
import * as styles from './virtual-list.css';

// ── Public types ──────────────────────────────────────────────────────────────

export interface ListViewSection<T> {
  /** Stable unique key for the section. */
  key: string;
  /** Optional header node (defaults to `ListView.SectionHeader` when a string is passed). */
  header?: React.ReactNode;
  items: T[];
}

export interface VirtualListProps<T> {
  /** Flat array of items. Provide either `items` or `sections`, not both. */
  items?: T[];
  /** Grouped sections. Provide either `items` or `sections`, not both. */
  sections?: ListViewSection<T>[];
  /** Stable string key for each item. */
  getItemKey: (item: T, index: number) => string;
  /** Render one list item. */
  renderItem: (item: T, index: number) => React.ReactNode;
  /** Override the section header render. Receives the section object. */
  renderSectionHeader?: (section: ListViewSection<T>) => React.ReactNode;

  /** Estimated row height in px (default 60). */
  estimateSize?: number;
  /** Estimated section header height in px (default 36). */
  estimateHeaderSize?: number;
  /** Number of off-screen rows to keep rendered (default 5). */
  overscan?: number;
  /** Measure actual row heights after render for variable-height rows (default true). */
  measure?: boolean;

  /** Called when the last item becomes visible — use for infinite-scroll pagination. */
  onEndReached?: () => void;
  /** When true a "Loading more…" indicator is appended below the list. */
  isFetchingMore?: boolean;

  /** When true and items are empty, shows `loadingSlot` instead of the list. */
  isLoading?: boolean;
  /** Rendered when `isLoading && itemCount === 0`. */
  loadingSlot?: React.ReactNode;
  /** Rendered when items are empty and not loading. */
  emptySlot?: React.ReactNode;
  /** Rendered when an error is present (pass `null` items to keep the slot visible). */
  errorSlot?: React.ReactNode;

  className?: string;
}

export interface VirtualListHandle {
  scrollToIndex(index: number, opts?: { align?: 'auto' | 'start' | 'center' | 'end' }): void;
}

// ── Internal flat row descriptor ──────────────────────────────────────────────

type FlatRow<T> =
  | { kind: 'item'; item: T; itemIndex: number; sectionKey?: string }
  | { kind: 'header'; section: ListViewSection<T> };

function getFlatRowKey<T>(
  row: FlatRow<T> | undefined,
  index: number,
  getItemKey: (item: T, index: number) => string
): string | number {
  if (!row) return index;
  return row.kind === 'header'
    ? `__section__${row.section.key}`
    : `__item__${getItemKey(row.item, row.itemIndex)}`;
}

function buildFlatRows<T>(
  items: T[] | undefined,
  sections: ListViewSection<T>[] | undefined
): FlatRow<T>[] {
  if (sections) {
    const rows: FlatRow<T>[] = [];
    for (const section of sections) {
      if (section.header !== undefined) {
        rows.push({ kind: 'header', section });
      }
      section.items.forEach((item, i) =>
        rows.push({ kind: 'item', item, itemIndex: i, sectionKey: section.key })
      );
    }
    return rows;
  }
  return (items ?? []).map((item, i) => ({ kind: 'item', item, itemIndex: i }));
}

// ── Component ─────────────────────────────────────────────────────────────────

function VirtualListInner<T>(
  {
    items,
    sections,
    getItemKey,
    renderItem,
    renderSectionHeader,
    estimateSize = 60,
    estimateHeaderSize = 36,
    overscan = 5,
    measure = true,
    onEndReached,
    isFetchingMore = false,
    isLoading = false,
    loadingSlot,
    emptySlot,
    errorSlot,
    className,
  }: VirtualListProps<T>,
  ref: React.ForwardedRef<VirtualListHandle>
) {
  const parentRef = React.useRef<HTMLDivElement>(null);

  const flatRows = React.useMemo(
    () => buildFlatRows(items, sections),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, sections]
  );

  const itemCount = flatRows.length;
  const getVirtualItemKey = React.useCallback(
    (index: number) => getFlatRowKey(flatRows[index], index, getItemKey),
    [flatRows, getItemKey]
  );

  const virtualizer = useVirtualizer({
    count: itemCount,
    getScrollElement: () => parentRef.current,
    getItemKey: getVirtualItemKey,
    estimateSize: (i) => (flatRows[i]?.kind === 'header' ? estimateHeaderSize : estimateSize),
    overscan,
    measureElement: measure ? (el) => el.getBoundingClientRect().height : undefined,
  });

  // Expose scrollToIndex imperatively.
  React.useImperativeHandle(ref, () => ({
    scrollToIndex(index, opts) {
      virtualizer.scrollToIndex(index, opts);
    },
  }));

  // Trigger onEndReached when the last virtual item is visible.
  const virtualItems = virtualizer.getVirtualItems();
  React.useEffect(() => {
    if (!onEndReached) return;
    const last = virtualItems[virtualItems.length - 1];
    if (!last) return;
    if (last.index >= itemCount - 1) {
      onEndReached();
    }
  }, [virtualItems, itemCount, onEndReached]);

  // ── State slots ─────────────────────────────────────────────────────────────

  if (isLoading && itemCount === 0) {
    return (
      <div className={cx(styles.scrollContainer, className)}>
        {loadingSlot ?? (
          <p className={styles.loadingMore} style={{ paddingTop: '1rem' }}>
            Loading…
          </p>
        )}
      </div>
    );
  }

  if (errorSlot && itemCount === 0) {
    return <div className={cx(styles.scrollContainer, className)}>{errorSlot}</div>;
  }

  if (itemCount === 0) {
    return <div className={cx(styles.scrollContainer, className)}>{emptySlot ?? null}</div>;
  }

  // ── Virtualized list ─────────────────────────────────────────────────────────

  return (
    <div ref={parentRef} className={cx(styles.scrollContainer, className)}>
      <div style={{ height: virtualizer.getTotalSize() }} className={styles.spacer}>
        {virtualItems.map((vItem) => {
          const row = flatRows[vItem.index];
          if (!row) return null;

          let content: React.ReactNode;

          if (row.kind === 'header') {
            content = renderSectionHeader
              ? renderSectionHeader(row.section)
              : (row.section.header ?? null);
          } else {
            content = renderItem(row.item, row.itemIndex);
          }

          return (
            <div
              key={getFlatRowKey(row, vItem.index, getItemKey)}
              data-index={vItem.index}
              ref={measure ? virtualizer.measureElement : undefined}
              className={styles.virtualRow}
              style={{ transform: `translateY(${vItem.start}px)` }}
            >
              {content}
            </div>
          );
        })}
      </div>
      {isFetchingMore && <p className={styles.loadingMore}>Loading more…</p>}
    </div>
  );
}

// TypeScript requires a named wrapper to preserve the generic signature through
// forwardRef (which erases the type parameter).
export const VirtualList = React.forwardRef(VirtualListInner) as <T>(
  props: VirtualListProps<T> & { ref?: React.Ref<VirtualListHandle> }
) => React.ReactElement;
