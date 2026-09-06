import { observer } from 'mobx-react-lite';
import * as React from 'react';
import { ItemContextProvider, useItemCtx } from '../context/item-context';
import { ListViewContextProvider, useListViewCtx } from '../context/list-view-context';
import { SectionContextProvider, useSectionCtx } from '../context/section-context';
import { SectionHeader } from '../list-row';
import { VirtualList, type VirtualListHandle, type VirtualListProps } from '../virtual-list';
import { ListViewStore } from './list-view-store';
import type {
  FilterApi,
  FilterModel,
  FilterModelOf,
  GetItemType,
  ItemContextValue,
  ListViewSnapshot,
  ListViewSpec,
  PaginationApi,
  RenameApi,
  ScrollApi,
  SearchApi,
  SectionContextValue,
  SelectionApi,
  SortApi,
  SortKeyOf,
} from './types';

// ── Component prop types ──────────────────────────────────────────────────────

export interface VirtualizationOptions {
  estimateSize?: number;
  estimateHeaderSize?: number;
  overscan?: number;
  measure?: boolean;
}

export interface ListProps<T> {
  renderItem: (item: T, index: number) => React.ReactNode;
  renderSection?: (key: string, count: number) => React.ReactNode;
  emptySlot?: React.ReactNode;
  loadingSlot?: React.ReactNode;
  errorSlot?: React.ReactNode;
  virtualization?: VirtualizationOptions;
  className?: string;
}

export interface StaticListProps<T> {
  renderItem: (item: T, index: number) => React.ReactNode;
  emptySlot?: React.ReactNode;
  loadingSlot?: React.ReactNode;
  className?: string;
}

// ── Base return type ──────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
interface ListViewBase<T, S extends ListViewSpec<any>> {
  /** The underlying MobX store — thread into your app's store tree or pass to `Root`. */
  store: ListViewStore<T, S>;

  /**
   * Creates a fresh `ListViewStore` for this spec.
   * Use when you need multiple independent instances of the same list type.
   */
  createStore(): ListViewStore<T, S>;

  /** Re-fetches the default store while preserving query state. */
  reload(): Promise<void>;

  // ── Components ─────────────────────────────────────────────────────────────

  /**
   * Context provider + lifecycle manager.
   *
   * Accepts an optional `store` prop; when omitted the factory's default store is used.
   * Creates a new store internally when `createStore` prop is `true`.
   */
  Root: React.ComponentType<{
    children: React.ReactNode;
    store?: ListViewStore<T, S>;
  }>;

  /**
   * Virtualized list — renders into `@emdash/ui` `ListView.List`.
   *
   * Automatically wires `isLoading`, `onEndReached`, and `isFetchingMore` from the store.
   * Must be rendered inside `Root`.
   */
  List: React.ComponentType<ListProps<T>>;

  /**
   * Non-virtualized list — plain `<div>` rows; suitable for popovers and tiny lists.
   * All contexts/hooks work identically to `List`.
   */
  StaticList: React.ComponentType<StaticListProps<T>>;

  /** Context provider wrapping a section; exposes `useSection()`. */
  Section: React.ComponentType<{ section: { key: string; items: T[] }; children: React.ReactNode }>;

  /** Context provider wrapping a single row; exposes `useItem()`. */
  Item: React.ComponentType<{ item: T; index: number; children: React.ReactNode }>;

  // ── Core hooks ─────────────────────────────────────────────────────────────

  /** Returns the store's current status, items, and orderedIds. */
  useListView(): ListViewSnapshot<T>;

  /** Returns the current item from context + its selection/rename state. */
  useItem(): ItemContextValue<T>;

  /** Returns the current section from context. */
  useSection(): SectionContextValue<T>;

  /** Imperatively scroll to an id or flat index. */
  useScroll(): ScrollApi;
}

// ── Conditional return type ───────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type ListViewApi<T, S extends ListViewSpec<any>> = ListViewBase<T, S> &
  (S['search'] extends object ? { useSearch(): SearchApi } : unknown) &
  (S['filter'] extends object ? { useFilter(): FilterApi<FilterModelOf<S>> } : unknown) &
  (S['sort'] extends object ? { useSort(): SortApi<SortKeyOf<S>> } : unknown) &
  (S['pagination'] extends object ? { usePagination(): PaginationApi } : unknown) &
  (S['selection'] extends object ? { useSelection(): SelectionApi } : unknown) &
  (S['rename'] extends object ? { useRename(): RenameApi<T> } : unknown);

// ── Factory ───────────────────────────────────────────────────────────────────

/**
 * Creates a fully typed, headless list state system.
 *
 * ```ts
 * const agentView = createListView({
 *   getItemId: (a: Agent) => a.id,
 *   source: { kind: 'sync', items: agents },
 *   search: { kind: 'sync', predicate: createTextMatcher((a) => a.name) },
 *   filter: { kind: 'sync', initial: { tab: 'all' }, apply: (a, f) => ... },
 *   selection: { kind: 'multi' },
 * });
 *
 * function AgentsList() {
 *   return (
 *     <agentView.Root>
 *       <agentView.List renderItem={(agent) => <AgentRow agent={agent} />} />
 *     </agentView.Root>
 *   );
 * }
 *
 * const AgentRow = observer(function AgentRow({ agent }) {
 *   const { isSelected, toggle } = agentView.useItem();
 *   return <ListView.Row selected={isSelected} onClick={toggle}>{agent.name}</ListView.Row>;
 * });
 * ```
 */
export function createListView<const S extends ListViewSpec<any>>(
  // eslint-disable-line @typescript-eslint/no-explicit-any
  spec: S
): ListViewApi<GetItemType<S>, S> {
  type T = GetItemType<S>;

  // Default store — shared unless the caller passes a custom one to Root.
  const defaultStore = new ListViewStore<T, S>(spec);
  const listRef = React.createRef<VirtualListHandle>();

  // ── createStore ────────────────────────────────────────────────────────────

  function createStore(): ListViewStore<T, S> {
    return new ListViewStore<T, S>(spec);
  }

  // ── Root ───────────────────────────────────────────────────────────────────

  function Root({
    children,
    store = defaultStore,
  }: {
    children: React.ReactNode;
    store?: ListViewStore<T, S>;
  }): React.ReactElement {
    React.useEffect(() => {
      store.initialize();
      return () => store.dispose();
    }, [store]);

    return <ListViewContextProvider store={store}>{children}</ListViewContextProvider>;
  }

  // ── List (virtualized) ─────────────────────────────────────────────────────

  const List = observer(function List({
    renderItem,
    renderSection,
    emptySlot,
    loadingSlot,
    errorSlot,
    virtualization,
    className,
  }: ListProps<T>): React.ReactElement {
    const store = useListViewCtx() as ListViewStore<T, S>;
    const { sections } = store;

    const renderSectionHeader: VirtualListProps<T>['renderSectionHeader'] = sections
      ? (section) => {
          const sectionVal: SectionContextValue<T> = {
            key: section.key,
            items: section.items,
            count: section.items.length,
          };
          const header = spec.sections?.header
            ? spec.sections.header(section.key, section.items.length)
            : (section.header ?? (
                <SectionHeader label={section.key} count={section.items.length} />
              ));
          return (
            <SectionContextProvider value={sectionVal}>
              {renderSection ? renderSection(section.key, section.items.length) : header}
            </SectionContextProvider>
          );
        }
      : undefined;

    return (
      <VirtualList<T>
        ref={(h) => {
          store.scroll.attachHandle(h);
          // also forward to listRef if callers need it
          (listRef as React.MutableRefObject<VirtualListHandle | null>).current = h;
        }}
        items={sections ? undefined : store.visibleItems}
        sections={
          sections
            ? sections.map((s) => ({
                key: s.key,
                items: s.items,
                header: spec.sections?.header ? (
                  spec.sections.header(s.key, s.items.length)
                ) : (
                  <SectionHeader label={s.key} count={s.items.length} />
                ),
              }))
            : undefined
        }
        getItemKey={(item) => spec.getItemId(item)}
        renderItem={(item, index) => (
          <ItemContextProvider value={{ item, id: spec.getItemId(item), index }}>
            {renderItem(item, index)}
          </ItemContextProvider>
        )}
        renderSectionHeader={renderSectionHeader}
        isLoading={store.status === 'loading'}
        loadingSlot={loadingSlot}
        emptySlot={emptySlot}
        errorSlot={store.status === 'error' ? (errorSlot ?? null) : undefined}
        onEndReached={store.pagination ? () => void store.pagination!.loadMore() : undefined}
        isFetchingMore={store.pagination?.isFetchingMore}
        estimateSize={virtualization?.estimateSize}
        estimateHeaderSize={virtualization?.estimateHeaderSize}
        overscan={virtualization?.overscan}
        measure={virtualization?.measure}
        className={className}
      />
    );
  });

  // ── StaticList (non-virtualized) ───────────────────────────────────────────

  const StaticList = observer(function StaticList({
    renderItem,
    emptySlot,
    loadingSlot,
    className,
  }: StaticListProps<T>): React.ReactElement {
    const store = useListViewCtx() as ListViewStore<T, S>;
    const { visibleItems, status } = store;

    if (status === 'loading' && visibleItems.length === 0) {
      return <div className={className}>{loadingSlot ?? null}</div>;
    }
    if (visibleItems.length === 0) {
      return <div className={className}>{emptySlot ?? null}</div>;
    }
    return (
      <div className={className}>
        {visibleItems.map((item, index) => (
          <ItemContextProvider
            key={spec.getItemId(item)}
            value={{ item, id: spec.getItemId(item), index }}
          >
            {renderItem(item, index)}
          </ItemContextProvider>
        ))}
      </div>
    );
  });

  // ── Section / Item ─────────────────────────────────────────────────────────

  function Section({
    section,
    children,
  }: {
    section: { key: string; items: T[] };
    children: React.ReactNode;
  }): React.ReactElement {
    return (
      <SectionContextProvider
        value={{ key: section.key, items: section.items, count: section.items.length }}
      >
        {children}
      </SectionContextProvider>
    );
  }

  function Item({
    item,
    index,
    children,
  }: {
    item: T;
    index: number;
    children: React.ReactNode;
  }): React.ReactElement {
    return (
      <ItemContextProvider value={{ item, id: spec.getItemId(item), index }}>
        {children}
      </ItemContextProvider>
    );
  }

  // ── Core hooks ─────────────────────────────────────────────────────────────

  function useListView(): ListViewSnapshot<T> {
    const store = useListViewCtx() as ListViewStore<T, S>;
    return {
      status: store.status,
      error: store.error,
      visibleItems: store.visibleItems,
      orderedIds: store.orderedIds,
      reload: () => store.reload(),
    };
  }

  function useItem(): ItemContextValue<T> {
    return useItemCtx<T>();
  }

  function useSection(): SectionContextValue<T> {
    return useSectionCtx<T>();
  }

  function useScroll(): ScrollApi {
    const store = useListViewCtx() as ListViewStore<T, S>;
    return {
      toId: (id, opts) => store.scroll.toId(id, store.orderedIds, opts),
      toIndex: (index, opts) => store.scroll.toIndex(index, opts),
    };
  }

  // ── Capability hooks ───────────────────────────────────────────────────────

  function useSearch(): SearchApi {
    const store = useListViewCtx() as ListViewStore<T, S>;
    const sl = store.search!;
    return {
      query: sl.query,
      setQuery: (q) => sl.setQuery(q),
      isSearching: sl.isPending || store.status === 'loading',
    };
  }

  function useFilter(): FilterApi<FilterModelOf<S>> {
    const store = useListViewCtx() as ListViewStore<T, S>;
    const sl = store.filter!;
    return {
      model: sl.model as FilterModelOf<S>,
      set: (patch) => sl.set(patch as FilterModel),
      reset: () => sl.reset(),
    };
  }

  function useSort(): SortApi<SortKeyOf<S>> {
    const store = useListViewCtx() as ListViewStore<T, S>;
    const sl = store.sort!;
    return {
      key: sl.key as SortKeyOf<S>,
      dir: sl.dir,
      setKey: (k) => sl.setKey(k as string),
      toggleDir: () => sl.toggleDir(),
      keys: spec.sort!.keys as SortApi<SortKeyOf<S>>['keys'],
    };
  }

  function usePagination(): PaginationApi {
    const store = useListViewCtx() as ListViewStore<T, S>;
    const sl = store.pagination!;
    return {
      loadMore: () => void sl.loadMore(),
      reload: () => void sl.reload(),
      isFetchingMore: sl.isFetchingMore,
      hasMore: sl.hasMore,
    };
  }

  function useSelection(): SelectionApi {
    const store = useListViewCtx() as ListViewStore<T, S>;

    // External store: delegate directly (must expose MobX observables).
    if (store.externalSelection) {
      const ext = store.externalSelection;
      return {
        selectedIds: ext.selectedIds,
        count: ext.count,
        isSelected: (id) => ext.isSelected(id),
        toggle: (id, e) => ext.toggle(id, e),
        selectRange: (from, to) => ext.selectRange(from, to, store.orderedIds),
        selectAll: () => ext.selectAll(store.orderedIds),
        clear: () => ext.clear(),
      };
    }

    // Built-in SelectionSlice.
    const sl = store.selectionSlice!;
    return {
      selectedIds: sl.selectedIds,
      count: sl.count,
      isSelected: (id) => sl.isSelected(id),
      toggle: (id, e) => sl.toggleWithRange(id, store.orderedIds, e),
      selectRange: (from, to) => sl.selectRange(from, to, store.orderedIds),
      selectAll: () => sl.selectAll(store.orderedIds),
      clear: () => sl.clear(),
    };
  }

  function useRename(): RenameApi<T> {
    const store = useListViewCtx() as ListViewStore<T, S>;
    const sl = store.rename!;
    return {
      editingId: sl.editingId,
      begin: (id) => sl.begin(id),
      commit: (name) => sl.commit(name),
      cancel: () => sl.cancel(),
      canRename: (item) => sl.canRename(item),
    };
  }

  // ── Assemble return object ─────────────────────────────────────────────────

  const base: ListViewBase<T, S> = {
    store: defaultStore,
    createStore,
    reload: () => defaultStore.reload(),
    Root,
    List,
    StaticList,
    Section,
    Item,
    useListView,
    useItem,
    useSection,
    useScroll,
  };

  const extended: Record<string, unknown> = { ...base };
  if (spec.search) extended['useSearch'] = useSearch;
  if (spec.filter) extended['useFilter'] = useFilter;
  if (spec.sort) extended['useSort'] = useSort;
  if (spec.pagination) extended['usePagination'] = usePagination;
  if (spec.selection) extended['useSelection'] = useSelection;
  if (spec.rename) extended['useRename'] = useRename;

  return extended as ListViewApi<GetItemType<S>, S>;
}
