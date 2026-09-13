import type * as React from 'react';
import type { Comparator } from '../comparators';
import type { VirtualListHandle } from '../virtual-list';

// ── Source ────────────────────────────────────────────────────────────────────

/**
 * Where list items come from.
 *
 * - `sync`: plain array or a reactive getter (e.g. `() => Array.from(store.items.values())`).
 *   If a getter is supplied and it reads MobX observables, `visibleItems` re-derives automatically.
 * - `async`: async loader called on mount (and on explicit `reload()`).
 * - `external`: items *and* status/error mirror an externally owned fetcher (e.g. a
 *   React Query result via `useQueryListSource`). The view never fetches; the owner
 *   handles refetching, so `reload()` is a no-op. All getters are reactive reads —
 *   back them with MobX observables. Status uses the store's own vocabulary:
 *   `loading` only while there is no data yet (background refetches should stay
 *   `idle` so stale rows keep showing), `error` routes to `errorSlot` when the
 *   list is empty.
 */
export type ListSource<T> =
  | { kind: 'sync'; items: T[] | (() => T[]) }
  | { kind: 'async'; load: (signal: AbortSignal) => Promise<T[]> }
  | {
      kind: 'external';
      items: () => T[];
      status: () => 'idle' | 'loading' | 'error';
      error?: () => unknown;
    };

// ── Search ────────────────────────────────────────────────────────────────────

/**
 * Search capability.
 *
 * - `sync`:  filters `rawItems` locally using `predicate`.
 * - `async`: sends `query` to the server; returned items *replace* raw items for this pipeline run.
 */
export type SearchSpec<T> =
  | { kind: 'sync'; predicate: (item: T, query: string) => boolean; debounceMs?: number }
  | {
      kind: 'async';
      search: (query: string, signal: AbortSignal) => Promise<T[]>;
      debounceMs?: number;
    };

// ── Filter ────────────────────────────────────────────────────────────────────

/**
 * Filter model — a plain record of filter criteria; e.g. `{ status: 'open'; author: string[] }`.
 */
export type FilterModel = Record<string, unknown>;

/**
 * Filter capability.
 *
 * - `sync`:  filters `rawItems` locally using `apply`.
 * - `async`: sends the whole filter model to the server; returned items replace local filtering.
 */
export type FilterSpec<T, F extends FilterModel = FilterModel> =
  | { kind: 'sync'; initial: F; apply: (item: T, model: F) => boolean }
  | { kind: 'async'; initial: F; apply: (model: F, signal: AbortSignal) => Promise<T[]> };

// ── Sort ──────────────────────────────────────────────────────────────────────

/**
 * Sort capability.
 *
 * `keys` is a keyed record of sort options; `compare` drives client-side sorting.
 * If `remote` is provided, it fetches server-sorted items and overrides local sorting.
 */
export type SortSpec<T, K extends string = string> = {
  keys: Record<K, { label: string; compare?: Comparator<T> }>;
  initial: { key: K; dir: 'asc' | 'desc' };
  remote?: (key: K, dir: 'asc' | 'desc', signal: AbortSignal) => Promise<T[]>;
};

// ── Sections ──────────────────────────────────────────────────────────────────

/**
 * Groups `visibleItems` into named sections after search/filter/sort.
 *
 * `order` sets the display order of known section keys; unknown keys are appended.
 * `header` overrides the default `ListView.SectionHeader` for each group.
 */
export type SectionsSpec<T> = {
  by: (item: T) => string;
  order?: string[];
  header?: (key: string, count: number) => React.ReactNode;
};

// ── Pagination ────────────────────────────────────────────────────────────────

/**
 * Infinite-scroll pagination.
 *
 * `loadMore` is called when the virtualizer reaches the end of the list.
 * Results are appended to the existing list.
 * Pass `null` as `cursor` for the first page.
 */
export type PaginationSpec<T> = {
  kind: 'infinite';
  loadMore: (
    cursor: string | null,
    signal: AbortSignal
  ) => Promise<{ items: T[]; nextCursor: string | null }>;
};

// ── Selection ─────────────────────────────────────────────────────────────────

/**
 * External selection store adapter.
 *
 * Implement this interface when you want to delegate selection to an existing
 * MobX store in your app (e.g. a `TaskViewStore`).  The `selectedIds` and `count`
 * properties must be MobX observables so that `observer`-wrapped rows react to changes.
 */
export interface ExternalSelectionStore {
  readonly selectedIds: ReadonlySet<string>;
  readonly count: number;
  isSelected(id: string): boolean;
  toggle(id: string, e?: React.MouseEvent | React.KeyboardEvent): void;
  selectRange(fromId: string, toId: string, orderedIds: string[]): void;
  selectAll(orderedIds: string[]): void;
  clear(): void;
}

/** Selection capability. */
export type SelectionSpec =
  | { kind: 'single' }
  | { kind: 'multi' }
  | { kind: 'external'; store: ExternalSelectionStore };

// ── Rename ────────────────────────────────────────────────────────────────────

/** Inline rename capability. */
export type RenameSpec<T> = {
  canRename?: (item: T) => boolean;
  commit: (item: T, name: string) => void | Promise<void>;
};

// ── Full spec ─────────────────────────────────────────────────────────────────

/**
 * The complete specification passed to `createListView`.
 *
 * All capability fields are optional; only the returned object includes the
 * corresponding hook when the capability is present.
 */
export interface ListViewSpec<T> {
  /** Stable unique identifier for each item — used for selection, rename, virtual keys. */
  getItemId: (item: T) => string;
  source: ListSource<T>;
  search?: SearchSpec<T>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  filter?: FilterSpec<T, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  sort?: SortSpec<T, any>;
  sections?: SectionsSpec<T>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  pagination?: PaginationSpec<any>;
  selection?: SelectionSpec;
  rename?: RenameSpec<T>;
}

// ── Capability API surfaces ───────────────────────────────────────────────────

export interface SearchApi {
  /** Raw (immediate) query value — bind to the input. */
  query: string;
  setQuery: (query: string) => void;
  /** True while a debounce timer is pending or an async search is in-flight. */
  isSearching: boolean;
}

export interface FilterApi<F extends FilterModel> {
  model: F;
  set: (patch: Partial<F>) => void;
  reset: () => void;
}

export interface SortApi<K extends string> {
  key: K;
  dir: 'asc' | 'desc';
  setKey: (key: K) => void;
  toggleDir: () => void;
  keys: Record<K, { label: string }>;
}

export interface PaginationApi {
  loadMore: () => void;
  reload: () => void;
  isFetchingMore: boolean;
  hasMore: boolean;
}

export interface SelectionApi {
  selectedIds: ReadonlySet<string>;
  count: number;
  isSelected: (id: string) => boolean;
  toggle: (id: string, e?: React.MouseEvent | React.KeyboardEvent) => void;
  selectRange: (fromId: string, toId: string) => void;
  selectAll: () => void;
  clear: () => void;
}

export interface RenameApi<T> {
  editingId: string | null;
  begin: (id: string) => void;
  commit: (name: string) => Promise<void>;
  cancel: () => void;
  canRename: (item: T) => boolean;
}

export interface ScrollApi {
  toId: (id: string, opts?: { align?: 'auto' | 'start' | 'center' | 'end' }) => void;
  toIndex: (index: number, opts?: { align?: 'auto' | 'start' | 'center' | 'end' }) => void;
}

// ── Store snapshot (for useListView) ─────────────────────────────────────────

export interface ListViewSnapshot<T> {
  status: 'idle' | 'loading' | 'error';
  error?: unknown;
  visibleItems: T[];
  orderedIds: string[];
  reload: () => Promise<void>;
}

// ── Context value types ───────────────────────────────────────────────────────

export interface ItemContextValue<T> {
  item: T;
  id: string;
  index: number;
}

export interface SectionContextValue<T> {
  key: string;
  items: T[];
  count: number;
}

// ── Conditional return type helpers ───────────────────────────────────────────

/** Extracts the item type T from a spec via `getItemId`'s parameter. */
export type GetItemType<S> = S extends { getItemId: (item: infer T) => string } ? T : never;

/**
 * Extract the filter model type from a spec.
 * Uses `any` to avoid variance errors when S extends ListViewSpec<T>.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type FilterModelOf<S extends ListViewSpec<any>> =
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  S['filter'] extends FilterSpec<any, infer F> ? F : FilterModel;

/**
 * Extract the sort key union from a spec.
 * Uses `any` to avoid variance errors when S extends ListViewSpec<T>.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type SortKeyOf<S extends ListViewSpec<any>> =
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  S['sort'] extends SortSpec<any, infer K> ? K : string;

/** VirtualListHandle forwarded out of the list component. */
export type { VirtualListHandle };
