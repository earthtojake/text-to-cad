import * as React from 'react';
import type { SectionContextValue } from '../core/types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SectionCtx = React.createContext<SectionContextValue<any> | null>(null);

export function SectionContextProvider<T>({
  value,
  children,
}: {
  value: SectionContextValue<T>;
  children: React.ReactNode;
}): React.ReactElement {
  return <SectionCtx.Provider value={value}>{children}</SectionCtx.Provider>;
}

/** Returns the current section's key, items, and count. */
export function useSectionCtx<T>(): SectionContextValue<T> {
  const ctx = React.useContext(SectionCtx);
  if (!ctx) throw new Error('useSectionCtx must be used inside a <Section>');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return ctx as SectionContextValue<T>;
}
