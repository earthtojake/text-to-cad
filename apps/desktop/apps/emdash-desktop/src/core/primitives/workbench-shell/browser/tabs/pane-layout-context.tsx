import { createContext, useContext, type ReactNode } from 'react';
import type { PaneLayoutStore } from './pane-layout-store';

const PaneLayoutContext = createContext<PaneLayoutStore | null>(null);

/**
 * Provides the PaneLayoutStore to descendants.
 *
 * Rendered by task-main-column.tsx around SplitPaneLayout so that generic
 * tab chrome (e.g. tab-drag-preview.tsx) can access the layout store without
 * importing from a domain feature.
 */
export function PaneLayoutProvider({
  paneLayout,
  children,
}: {
  paneLayout: PaneLayoutStore;
  children: ReactNode;
}) {
  return <PaneLayoutContext.Provider value={paneLayout}>{children}</PaneLayoutContext.Provider>;
}

export function usePaneLayoutContext(): PaneLayoutStore {
  const ctx = useContext(PaneLayoutContext);
  if (!ctx) throw new Error('usePaneLayoutContext must be used within a PaneLayoutProvider');
  return ctx;
}
