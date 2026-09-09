import { useCallback, useLayoutEffect, type ReactNode } from 'react';
import { SettingsPage } from '@core/features/settings/browser/components/SettingsPage';
import { settingsScope } from '@core/features/settings/contributions/scopes';
import { settingsViewDef, type SettingsPageTab } from '@core/features/settings/contributions/views';
import { BorderlessTitlebar } from '@core/features/workbench/contributions/browser/BorderlessTitlebar';
import { useCurrentViewParams } from '@core/primitives/navigation/browser/navigation-hooks';
import { getNavigation } from '@core/primitives/navigation/browser/navigation-selectors';
import type { ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { scopes } from '@core/primitives/view-scopes/browser';
import { useViewScope, ViewScopeInstanceProvider } from '@core/primitives/view-scopes/react';
import { defineViewRuntime } from '@core/primitives/views/react';
import { SettingsTabProvider, useSettingsTab } from './settings-tab-context';

export function SettingsViewWrapper({
  children,
  tab = 'general',
  detail,
}: {
  children: ReactNode;
  tab?: SettingsPageTab;
  detail?: string[];
}) {
  const { setParams } = useCurrentViewParams(settingsViewDef);
  const handleTabChange = useCallback(
    (tab: SettingsPageTab) => {
      setParams({ tab, detail: undefined });
    },
    [setParams]
  );
  const openDetail = useCallback(
    (detailId: string) => {
      setParams((previous) => ({
        ...previous,
        detail: [...(previous.detail ?? []), detailId],
      }));
    },
    [setParams]
  );
  const closeDetail = useCallback(() => {
    setParams((previous) => {
      const parent = previous.detail?.slice(0, -1);
      return { ...previous, detail: parent && parent.length > 0 ? parent : undefined };
    });
  }, [setParams]);
  const setDetailPath = useCallback(
    (path: string[] | undefined) => {
      setParams((previous) => ({
        ...previous,
        detail: path && path.length > 0 ? path : undefined,
      }));
    },
    [setParams]
  );
  const implementation = {
    'settings.close': () => ({
      execute: () => getNavigation().toggleSettings(),
    }),
  } satisfies ViewScopeImpl<typeof settingsScope>;
  const { instance } = useViewScope(settingsScope(), implementation);

  useLayoutEffect(() => {
    if (instance) scopes.activate(instance);
  }, [instance]);

  if (!instance) return null;
  return (
    <ViewScopeInstanceProvider instance={instance}>
      <SettingsTabProvider
        value={{
          tab,
          detail,
          onTabChange: handleTabChange,
          openDetail,
          closeDetail,
          setDetailPath,
        }}
      >
        {children}
      </SettingsTabProvider>
    </ViewScopeInstanceProvider>
  );
}

export function SettingsMainPanel() {
  const { tab, detail, onTabChange, openDetail, closeDetail, setDetailPath } = useSettingsTab();
  return (
    <div className="relative z-10 flex min-h-0 flex-1 overflow-hidden bg-background">
      <BorderlessTitlebar />
      <SettingsPage
        tab={tab}
        detail={detail}
        onTabChange={onTabChange}
        openDetail={openDetail}
        closeDetail={closeDetail}
        setDetailPath={setDetailPath}
      />
    </div>
  );
}

export const settingsViewRuntime = defineViewRuntime(settingsViewDef, {
  slots: {
    wrap: SettingsViewWrapper,
    main: SettingsMainPanel,
  },
});
