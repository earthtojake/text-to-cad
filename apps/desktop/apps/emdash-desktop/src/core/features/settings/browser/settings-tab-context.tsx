import { createContext, useContext, type ReactNode } from 'react';
import type { SettingsPageTab } from '@core/features/settings/contributions/views';

export interface SettingsTabContextValue {
  tab: SettingsPageTab;
  detail?: string[];
  onTabChange: (tab: SettingsPageTab) => void;
  /** Appends one segment to the detail path. */
  openDetail: (detailId: string) => void;
  /** Pops one level off the detail path. */
  closeDetail: () => void;
  /** Jumps to an explicit path prefix; undefined or empty clears the detail. */
  setDetailPath: (path: string[] | undefined) => void;
}

const SettingsTabContext = createContext<SettingsTabContextValue | null>(null);

export function SettingsTabProvider({
  value,
  children,
}: {
  value: SettingsTabContextValue;
  children: ReactNode;
}) {
  return <SettingsTabContext.Provider value={value}>{children}</SettingsTabContext.Provider>;
}

export function useSettingsTab(): SettingsTabContextValue {
  const context = useContext(SettingsTabContext);
  if (!context) throw new Error('useSettingsTab must be used within a SettingsTabProvider');
  return context;
}
