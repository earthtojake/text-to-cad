import { observable, runInAction } from 'mobx';
import { useLayoutEffect, useRef, useState } from 'react';
import type { ListSource } from './core/types';

// ── Types ─────────────────────────────────────────────────────────────────────

/**
 * The slice of a query result the source needs. Structurally matches a React
 * Query `useQuery` result (v4 and v5 — `isLoading` means "first load in
 * flight", so background refetches keep showing stale rows instead of the
 * loading state).
 */
export interface QueryResultLike<TData> {
  data: TData | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}

export type ExternalListSource<T> = Extract<ListSource<T>, { kind: 'external' }>;

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Bridges a query result into an `external` list source for `createListView`.
 * The query owner (React Query) keeps owning fetch, cache, and invalidation;
 * the view mirrors its items and status, so `loadingSlot`/`errorSlot` route
 * from the view's own state with no per-surface wiring.
 *
 * The returned source is referentially stable — create the view once with it:
 *
 * ```tsx
 * const source = useQueryListSource(automationsQuery, (rows) => rows.map(toItem));
 * const [view] = useState(() => createListView({ getItemId, source, ... }));
 * ```
 *
 * The internal observable is seeded from the first render and updated before
 * paint, so a query that resolves synchronously from cache never flashes the
 * empty state. `buildItems` must be a pure mapping of `data`; it re-runs only
 * when the query snapshot changes.
 */
export function useQueryListSource<TData, T>(
  query: QueryResultLike<TData>,
  buildItems: (data: TData) => T[]
): ExternalListSource<T> {
  const buildItemsRef = useRef(buildItems);
  buildItemsRef.current = buildItems;

  const [{ box, source }] = useState(() => {
    const initial: QueryResultLike<TData> = {
      data: query.data,
      isLoading: query.isLoading,
      isError: query.isError,
      error: query.error,
    };
    const snapshotBox = observable.box<QueryResultLike<TData>>(initial, { deep: false });
    const externalSource: ExternalListSource<T> = {
      kind: 'external',
      items: () => {
        const { data } = snapshotBox.get();
        return data === undefined ? [] : buildItemsRef.current(data);
      },
      status: () => {
        const snapshot = snapshotBox.get();
        if (snapshot.isLoading) return 'loading';
        if (snapshot.isError) return 'error';
        return 'idle';
      },
      error: () => snapshotBox.get().error,
    };
    return { box: snapshotBox, source: externalSource };
  });

  // Before paint (not in an effect) so data arriving between renders never
  // flashes the empty state — same fix as the hand-rolled bridges this
  // replaces.
  useLayoutEffect(() => {
    const current = box.get();
    if (
      current.data === query.data &&
      current.isLoading === query.isLoading &&
      current.isError === query.isError &&
      current.error === query.error
    ) {
      return;
    }
    runInAction(() => {
      box.set({
        data: query.data,
        isLoading: query.isLoading,
        isError: query.isError,
        error: query.error,
      });
    });
  });

  return source;
}
