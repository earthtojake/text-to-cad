import { useLayoutEffect, useRef } from 'react';
import { paneScope } from '@core/features/workbench/contributions/scopes';
import { disabled, enabled, hidden, type ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { focusScope, scopes, type ViewScopeInstance } from '@core/primitives/view-scopes/browser';
import { useViewScope } from '@core/primitives/view-scopes/react';
import type { TabNavigationProvider } from '@core/primitives/workbench-shell/browser/tabs/tab-navigation-provider';

export interface PaneScopeOptions {
  readonly canSplit?: boolean;
  readonly splitPane?: () => void;
}

export function usePaneScope(
  paneId: string,
  provider: TabNavigationProvider,
  options: PaneScopeOptions = {}
) {
  const instanceRef = useRef<ViewScopeInstance | undefined>(undefined);
  const focusContent = () => {
    if (provider.focusActiveContent) focusScope(instanceRef.current);
  };
  const selectIndex = (index: number) => {
    provider.setTabActiveIndex(index);
    focusContent();
  };
  const implementation = {
    'workbench.tabNext': () => ({
      execute: () => {
        provider.setNextTabActive();
        focusContent();
      },
    }),
    'workbench.tabPrev': () => ({
      execute: () => {
        provider.setPreviousTabActive();
        focusContent();
      },
    }),
    'workbench.tabClose': () => ({
      execute: () => {
        provider.closeActiveTab();
        focusContent();
      },
    }),
    'workbench.tabReopen': () => ({
      availability: () => (provider.reopenClosedTab ? enabled : hidden),
      execute: () => {
        provider.reopenClosedTab?.();
        focusContent();
      },
    }),
    'workbench.tabRename': () => ({
      availability: () =>
        provider.renameActiveTab && provider.canRenameActiveTab?.() ? enabled : hidden,
      execute: () => provider.renameActiveTab?.(),
    }),
    'workbench.splitPane': () => ({
      availability: () =>
        options.splitPane
          ? options.canSplit
            ? enabled
            : disabled('Open at least two tabs to split this pane')
          : hidden,
      execute: () => options.splitPane?.(),
    }),
    'workbench.tabCycleNext': () => ({
      execute: () => {
        provider.setNextTabActive();
        focusContent();
      },
    }),
    'workbench.tabCyclePrev': () => ({
      execute: () => {
        provider.setPreviousTabActive();
        focusContent();
      },
    }),
    'workbench.tab1': () => ({ execute: () => selectIndex(0) }),
    'workbench.tab2': () => ({ execute: () => selectIndex(1) }),
    'workbench.tab3': () => ({ execute: () => selectIndex(2) }),
    'workbench.tab4': () => ({ execute: () => selectIndex(3) }),
    'workbench.tab5': () => ({ execute: () => selectIndex(4) }),
    'workbench.tab6': () => ({ execute: () => selectIndex(5) }),
    'workbench.tab7': () => ({ execute: () => selectIndex(6) }),
    'workbench.tab8': () => ({ execute: () => selectIndex(7) }),
    'workbench.tab9': () => ({ execute: () => selectIndex(8) }),
  } satisfies ViewScopeImpl<typeof paneScope>;
  const result = useViewScope<typeof paneScope>(paneScope({ paneId }), implementation);
  instanceRef.current = result.instance;
  useLayoutEffect(() => {
    if (!result.instance) return;
    result.instance.setFocusDelegate(
      provider.focusActiveContent ? () => provider.focusActiveContent?.() : undefined
    );
    return () => result.instance?.setFocusDelegate(undefined);
  }, [provider, result.instance]);

  return {
    ...result,
    isFocused: result.instance ? scopes.isWithinActivePath(result.instance) : false,
  };
}
