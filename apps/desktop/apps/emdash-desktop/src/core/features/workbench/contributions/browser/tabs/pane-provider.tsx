import { observer } from 'mobx-react-lite';
import type { ReactNode } from 'react';
import { usePaneScope } from '@core/features/workbench/api/browser/tabs/use-pane-scope';
import { ViewScopeInstanceProvider } from '@core/primitives/view-scopes/react';
import {
  PaneContext,
  type PaneContextValue,
} from '@core/primitives/workbench-shell/browser/tabs/pane-context';
import type { Pane } from '@core/primitives/workbench-shell/browser/tabs/pane-layout-store';

interface PaneProviderProps {
  group: Pane;
  canSplit: boolean;
  splitPane: () => void;
  children: ReactNode;
}

export const PaneProvider = observer(function PaneProvider({
  group,
  canSplit,
  splitPane,
  children,
}: PaneProviderProps) {
  const { attachRef, instance, isFocused } = usePaneScope(group.paneId, group.pane, {
    canSplit,
    splitPane,
  });
  const value: PaneContextValue = {
    paneId: group.paneId,
    pane: group.pane,
    scopeInstance: instance,
    isFocusedPane: isFocused,
  };

  return (
    <PaneContext.Provider value={value}>
      <ViewScopeInstanceProvider instance={instance}>
        <div
          ref={attachRef}
          tabIndex={-1}
          className="h-full min-w-0 outline-none"
          onPointerDownCapture={(event) => event.currentTarget.focus({ preventScroll: true })}
        >
          {children}
        </div>
      </ViewScopeInstanceProvider>
    </PaneContext.Provider>
  );
});
