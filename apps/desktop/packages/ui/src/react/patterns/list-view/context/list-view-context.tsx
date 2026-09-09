import * as React from 'react';
import type { ListViewStore } from '../core/list-view-store';
import type { ListViewSpec } from '../core/types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ListViewCtx = React.createContext<ListViewStore<any, any> | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────────

/**
 * Provides a `ListViewStore` to descendant components.
 *
 * `Root` (created by `createListView`) calls this internally; consumers
 * should not render `ListViewContextProvider` directly.
 */
export function ListViewContextProvider<T, S extends ListViewSpec<T>>({
  store,
  children,
}: {
  store: ListViewStore<T, S>;
  children: React.ReactNode;
}): React.ReactElement {
  return <ListViewCtx.Provider value={store}>{children}</ListViewCtx.Provider>;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Returns the nearest `ListViewStore` from context.
 * Throws when called outside a `createListView.Root`.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useListViewCtx(): ListViewStore<any, any> {
  const store = React.useContext(ListViewCtx);
  if (!store) {
    throw new Error('useListViewCtx must be used inside a <createListView.Root>');
  }
  return store;
}
