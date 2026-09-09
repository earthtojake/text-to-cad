import { Globe, Loader2 } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import type { BrowserTabResource } from '@core/features/browser/api/browser/browser-tab-resource';
import type { BrowserSessionSnapshot } from '@core/primitives/browser/api';
import type {
  TabBarItemProps,
  ResolvedTab,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import {
  GenericTabDragPreview,
  GenericTabItem,
} from '@core/primitives/workbench-shell/browser/tabs/tab-bar/generic-tab-item';

function browserTabLabel(session: BrowserSessionSnapshot | undefined): string {
  if (!session) return 'Browser';
  if (session.title.trim()) return session.title.trim();
  if (session.currentUrl === 'about:blank') return 'Browser';
  try {
    return new URL(session.currentUrl).host;
  } catch {
    return 'Browser';
  }
}

export const BrowserTabBarItem = observer(function BrowserTabBarItem({
  tab,
  host,
  ctx,
}: TabBarItemProps<BrowserTabResource>) {
  const session = tab.resource.session;
  const label = browserTabLabel(session);

  return (
    <GenericTabItem
      tab={tab}
      host={host}
      ctx={ctx}
      label={label}
      preSlot={
        <span className="shrink-0 text-foreground-muted [&>svg]:h-3 [&>svg]:w-3">
          {session?.isLoading ? <Loader2 className="animate-spin" /> : <Globe />}
        </span>
      }
      hasError={!!session?.loadError}
    />
  );
});

export function BrowserTabBarItemDragPreview({ tab }: { tab: ResolvedTab<BrowserTabResource> }) {
  const label = browserTabLabel(tab.resource.session);
  return (
    <GenericTabDragPreview
      preSlot={<Globe className="size-3 shrink-0 text-foreground-muted" />}
      label={label}
    />
  );
}
