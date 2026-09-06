import { cx } from '@styles/utilities/cx';
import { observer } from 'mobx-react-lite';
import * as React from 'react';
import { EmptyState } from '../../components/empty-state/empty-state';
import { Spinner } from '../../primitives/spinner';
import { ListView } from '../list-view';
import type { ItemContextValue, ListProps, ListViewSnapshot, SelectionApi } from '../list-view';
import * as styles from './collection-view.css';

// ── Public types ──────────────────────────────────────────────────────────────

export type CollectionViewDensity = 'default' | 'compact';

/** One tabular column of a `columns`-mode CollectionView. */
export interface CollectionViewColumn<T> {
  /** Stable identifier, used as the React key for the cell. */
  id: string;
  /** CSS grid track size: '2.25rem', 'minmax(0, 1fr)', '9rem', etc. */
  width: string;
  /** Renders this column's cell for an item. */
  cell: (item: T, index: number) => React.ReactNode;
  /** Optional cross-axis alignment for this cell. */
  align?: 'start' | 'center' | 'end';
}

/**
 * The structural slice of a `createListView` instance that CollectionView
 * consumes in state mode. Every `createListView` return value satisfies it.
 */
export interface CollectionViewHandle<T> {
  List: React.ComponentType<ListProps<T>>;
  useListView(): ListViewSnapshot<T>;
  useItem(): ItemContextValue<T>;
  /** Present when the view spec declares selection; rows auto-derive `selected`. */
  useSelection?: () => SelectionApi;
}

export interface CollectionViewProps<T> {
  // ── Data (exactly one) ──────────────────────────────────────────────────
  /** State mode: a `createListView` instance; render inside its `Root`. */
  view?: CollectionViewHandle<T>;
  /** Shortcut mode: plain items, no state layer. */
  items?: readonly T[];
  /** Required in shortcut mode; state mode gets ids from the view's spec. */
  getItemKey?: (item: T, index: number) => string;

  // ── Row content (exactly one) ───────────────────────────────────────────
  /** Row style A: tabular grid cells. */
  columns?: readonly CollectionViewColumn<T>[];
  /** Row style B: freeform inner layout; the canonical row shell stays. */
  renderRow?: (item: T, index: number) => React.ReactNode;

  // ── Chrome slots ────────────────────────────────────────────────────────
  /** Sticky toolbar slot — a CollectionToolbar (unchanged API) or custom row. */
  toolbar?: React.ReactNode;
  /**
   * Floating overlay slot rendered inside the positioned root — bulk bars and
   * banners built on `ListPopoverCard` anchor themselves above the list bottom.
   */
  footer?: React.ReactNode;
  /**
   * Section-header override (state mode with sections). Default rendering is
   * the view's section header (`ListView.SectionHeader` label + count).
   * Needed for e.g. select-all headers.
   */
  renderSectionHeader?: (key: string, count: number) => React.ReactNode;

  // ── Behavior / appearance ───────────────────────────────────────────────
  density?: CollectionViewDensity;
  /** Override the density's row-height estimate when content is taller. */
  estimateSize?: number;
  onItemClick?: (item: T, index: number, event: React.MouseEvent<HTMLDivElement>) => void;
  /** Shown when the list is empty. Defaults to a generic `EmptyState`. */
  emptySlot?: React.ReactNode;
  /** State mode only: shown while the view's source is loading. Defaults to a `Spinner`. */
  loadingSlot?: React.ReactNode;
  /** State mode only: shown when the view's source errored. Defaults to an `EmptyState`. */
  errorSlot?: React.ReactNode;
  className?: string;
}

// ── Cell ──────────────────────────────────────────────────────────────────────

export interface CollectionViewCellProps extends React.HTMLAttributes<HTMLDivElement> {
  primary: React.ReactNode;
  secondary?: React.ReactNode;
}

/** Two-line (primary/secondary) truncating text cell for `columns` mode. */
export function CollectionViewCell({
  primary,
  secondary,
  className,
  ...props
}: CollectionViewCellProps) {
  return (
    <div className={cx(styles.cell, className)} {...props}>
      <div className={styles.cellPrimary}>{primary}</div>
      {secondary !== undefined && <div className={styles.cellSecondary}>{secondary}</div>}
    </div>
  );
}

// ── Internals ─────────────────────────────────────────────────────────────────
// The internal row components erase the item type: `observer()` cannot carry a
// generic component type through, and the public generic surface restores
// type safety at the CollectionView boundary.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyItem = any;

const DENSITY_ESTIMATE: Record<CollectionViewDensity, number> = { default: 60, compact: 36 };

// Default slots render `bare` because the card already paints its own surface.
const DEFAULT_EMPTY_SLOT = <EmptyState bare label="No items" />;
const DEFAULT_LOADING_SLOT = (
  <div className={styles.loading}>
    <Spinner />
  </div>
);

interface RowContentProps {
  item: AnyItem;
  index: number;
  columns?: readonly CollectionViewColumn<AnyItem>[];
  renderRow?: (item: AnyItem, index: number) => React.ReactNode;
  template: string;
  density: CollectionViewDensity;
}

/** Dispatches between the two row styles; both share the canonical shell. */
function RowContent({ item, index, columns, renderRow, template, density }: RowContentProps) {
  if (columns !== undefined) {
    return (
      <div
        className={styles.rowGrid}
        style={{ '--collection-view-template': template } as React.CSSProperties}
      >
        {columns.map((column) => (
          <div key={column.id} className={styles.bodyCell[density]} data-align={column.align}>
            {column.cell(item, index)}
          </div>
        ))}
      </div>
    );
  }
  return <div className={styles.freeform[density]}>{renderRow?.(item, index)}</div>;
}

interface ShellRowProps {
  selected?: boolean;
  isLast: boolean;
  interactive: boolean;
  onClick?: React.MouseEventHandler<HTMLDivElement>;
  children: React.ReactNode;
}

/** Enter/Space on a focused row re-dispatches through the click path. */
function handleRowKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  // Inner controls (menus, switches) own their keyboard handling.
  if (event.target !== event.currentTarget) return;
  event.preventDefault();
  event.currentTarget.click();
}

/** The canonical row shell shared by both data modes. */
function ShellRow({ selected = false, isLast, interactive, onClick, children }: ShellRowProps) {
  return (
    <ListView.Row
      bare
      divider="subtle"
      interactive={interactive}
      selected={selected}
      isLast={isLast}
      onClick={onClick}
      // Interactive rows are keyboard-operable buttons, not bare divs.
      {...(interactive ? { role: 'button', tabIndex: 0, onKeyDown: handleRowKeyDown } : {})}
    >
      {children}
    </ListView.Row>
  );
}

interface StateRowProps extends RowContentProps {
  view: CollectionViewHandle<AnyItem>;
  /** Id of the visually last item — suppresses the final divider. */
  lastId: string | undefined;
  onItemClick?: (item: AnyItem, index: number, event: React.MouseEvent<HTMLDivElement>) => void;
}

/**
 * State-mode row. When the view declares selection, `selected` auto-derives
 * and the universal selection mechanics apply: modifier-click toggles,
 * shift-click extends the range, and a plain click stays navigation.
 */
const StateRow = observer(function StateRow({
  view,
  item,
  index,
  lastId,
  columns,
  renderRow,
  template,
  density,
  onItemClick,
}: StateRowProps) {
  const { id } = view.useItem();
  const selection = view.useSelection?.();
  const selected = selection?.isSelected(id) ?? false;

  const handleClick =
    selection !== undefined || onItemClick !== undefined
      ? (event: React.MouseEvent<HTMLDivElement>) => {
          if (selection !== undefined && (event.metaKey || event.ctrlKey || event.shiftKey)) {
            event.preventDefault();
            selection.toggle(id, event);
            return;
          }
          onItemClick?.(item, index, event);
        }
      : undefined;

  return (
    <ShellRow
      interactive={handleClick !== undefined}
      selected={selected}
      isLast={id === lastId}
      onClick={handleClick}
    >
      <RowContent
        item={item}
        index={index}
        columns={columns}
        renderRow={renderRow}
        template={template}
        density={density}
      />
    </ShellRow>
  );
});

interface StateBodyProps {
  view: CollectionViewHandle<AnyItem>;
  columns?: readonly CollectionViewColumn<AnyItem>[];
  renderRow?: (item: AnyItem, index: number) => React.ReactNode;
  template: string;
  density: CollectionViewDensity;
  estimateSize: number;
  onItemClick?: (item: AnyItem, index: number, event: React.MouseEvent<HTMLDivElement>) => void;
  emptySlot?: React.ReactNode;
  loadingSlot?: React.ReactNode;
  errorSlot?: React.ReactNode;
  renderSectionHeader?: (key: string, count: number) => React.ReactNode;
}

const StateBody = observer(function StateBody({
  view,
  columns,
  renderRow,
  template,
  density,
  estimateSize,
  onItemClick,
  emptySlot,
  loadingSlot,
  errorSlot,
  renderSectionHeader,
}: StateBodyProps) {
  const { orderedIds, error } = view.useListView();
  const lastId = orderedIds[orderedIds.length - 1];
  const errorMessage =
    error instanceof Error ? error.message : typeof error === 'string' ? error : undefined;

  return (
    <view.List
      virtualization={{ estimateSize }}
      emptySlot={emptySlot ?? DEFAULT_EMPTY_SLOT}
      loadingSlot={loadingSlot ?? DEFAULT_LOADING_SLOT}
      errorSlot={
        errorSlot ?? <EmptyState bare label="Something went wrong" description={errorMessage} />
      }
      renderSection={renderSectionHeader}
      renderItem={(item, index) => (
        <StateRow
          view={view}
          item={item}
          index={index}
          lastId={lastId}
          columns={columns}
          renderRow={renderRow}
          template={template}
          density={density}
          onItemClick={onItemClick}
        />
      )}
    />
  );
});

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * CollectionView — the canonical page-level list surface.
 *
 * One rounded card shell (soft dividers, hover/selected states, always-on
 * virtualization) rendering either tabular `columns` or freeform `renderRow`
 * content, with an optional `createListView` state layer:
 *
 * ```tsx
 * <tasksView.Root>
 *   <CollectionView
 *     view={tasksView}                  // state mode… or `items` for plain data
 *     columns={TASK_COLUMNS}            // …or `renderRow` for freeform rows
 *     toolbar={<TasksToolbar />}        // sticky slot above the list
 *     footer={<TasksSelectionBar />}    // floating overlay (bulk bars)
 *     onItemClick={(t) => openTask(t)}
 *     emptySlot={<EmptyState bare label="No tasks" />}
 *   />
 * </tasksView.Root>
 * ```
 *
 * In state mode, selection (row `selected` state), sections, pagination, and
 * loading/error status auto-wire from the view. See the "Page-level lists"
 * section of the agents UI-kit conventions for the full pattern.
 */
export function CollectionView<T>(props: CollectionViewProps<T>) {
  const {
    view,
    items,
    getItemKey,
    columns,
    renderRow,
    toolbar,
    footer,
    renderSectionHeader,
    density = 'default',
    estimateSize,
    onItemClick,
    emptySlot,
    loadingSlot,
    errorSlot,
    className,
  } = props;

  const template = React.useMemo(
    () => (columns !== undefined ? columns.map((column) => column.width).join(' ') : ''),
    [columns]
  );
  const listItems = React.useMemo(() => (items !== undefined ? Array.from(items) : []), [items]);

  if ((view === undefined) === (items === undefined)) {
    throw new Error('CollectionView requires exactly one of `view` or `items`.');
  }
  if ((columns === undefined) === (renderRow === undefined)) {
    throw new Error('CollectionView requires exactly one of `columns` or `renderRow`.');
  }
  if (items !== undefined && getItemKey === undefined) {
    throw new Error('CollectionView with `items` requires `getItemKey`.');
  }

  const estimate = estimateSize ?? DENSITY_ESTIMATE[density];
  // ListViewRoot spreads onto its div; typed via Record because HTMLAttributes
  // does not model data-* props on components.
  const rootDataProps: Record<string, string> = { 'data-density': density };

  return (
    <ListView className={cx(styles.root, className)} {...rootDataProps}>
      {toolbar !== undefined && <ListView.Toolbar>{toolbar}</ListView.Toolbar>}
      <ListView.Body>
        {view !== undefined ? (
          <StateBody
            view={view}
            columns={columns}
            renderRow={renderRow}
            template={template}
            density={density}
            estimateSize={estimate}
            onItemClick={onItemClick}
            emptySlot={emptySlot}
            loadingSlot={loadingSlot}
            errorSlot={errorSlot}
            renderSectionHeader={renderSectionHeader}
          />
        ) : (
          <ListView.List
            items={listItems}
            getItemKey={getItemKey as (item: T, index: number) => string}
            estimateSize={estimate}
            emptySlot={emptySlot ?? DEFAULT_EMPTY_SLOT}
            renderItem={(item, index) => (
              <ShellRow
                interactive={onItemClick !== undefined}
                isLast={index === listItems.length - 1}
                onClick={
                  onItemClick !== undefined ? (event) => onItemClick(item, index, event) : undefined
                }
              >
                <RowContent
                  item={item}
                  index={index}
                  columns={columns}
                  renderRow={renderRow}
                  template={template}
                  density={density}
                />
              </ShellRow>
            )}
          />
        )}
      </ListView.Body>
      {footer}
    </ListView>
  );
}
