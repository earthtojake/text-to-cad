import { createContext, useContext } from 'react';
import type { ViewScopeInstance } from '@core/primitives/view-scopes/browser';
import type { PaneStore } from './pane-store';

export interface PaneContextValue {
  paneId: string;
  pane: PaneStore;
  scopeInstance: ViewScopeInstance | undefined;
  /** True when this pane is the focused pane in the main region. */
  isFocusedPane: boolean;
}

export const PaneContext = createContext<PaneContextValue | null>(null);

/**
 * Returns the per-pane PaneStore and paneId for the enclosing pane.
 * Must be used inside a PaneProvider (i.e. within SplitPaneLayout).
 */
export function usePaneContext(): PaneContextValue {
  const ctx = useContext(PaneContext);
  if (!ctx) {
    throw new Error('usePaneContext must be used within a PaneProvider');
  }
  return ctx;
}
