import * as React from 'react';
import type { ItemContextValue } from '../core/types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ItemCtx = React.createContext<ItemContextValue<any> | null>(null);

export function ItemContextProvider<T>({
  value,
  children,
}: {
  value: ItemContextValue<T>;
  children: React.ReactNode;
}): React.ReactElement {
  return <ItemCtx.Provider value={value}>{children}</ItemCtx.Provider>;
}

/** Returns the current item, its id, and its flat index. */
export function useItemCtx<T>(): ItemContextValue<T> {
  const ctx = React.useContext(ItemCtx);
  if (!ctx) throw new Error('useItemCtx must be used inside a <Item>');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return ctx as ItemContextValue<T>;
}
