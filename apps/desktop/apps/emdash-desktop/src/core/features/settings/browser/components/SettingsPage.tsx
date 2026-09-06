import {
  PageLayout,
  type PageNavItem,
  type PageNavSection,
  type PageSidebarMenuItem,
} from '@emdash/ui/react/patterns';
import { Breadcrumbs, Icon, Kbd, SearchInput } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  matchedTabsForQuery,
  searchSettings,
} from '@core/features/settings/browser/search/settings-search';
import { SettingsSearchProvider } from '@core/features/settings/browser/search/settings-search-context';
import type { SettingsPageTab } from '@core/features/settings/contributions/views';
import { settingsPageContributions } from '@core/manifests/browser/settings-page-contributions';
import { openExternal } from '@core/primitives/desktop-host/browser/host-client';
import { chord, detectPlatformContext } from '@core/primitives/keybindings/api';
import {
  isTextInputFocusTarget,
  keyboardLayoutService,
  useChordKeydown,
} from '@core/primitives/keybindings/browser';
import { resolveDetailLevels, type ResolvedDetailLevel } from './settings-detail-path';

const LOCAL_SECTION: PageNavSection = { kind: 'section', id: 'local', label: 'Local' };
const REMOTE_SECTION: PageNavSection = { kind: 'section', id: 'remote', label: 'Remote' };
const SETTINGS_SEARCH_HOTKEY = chord('Mod+F');

const SIDEBAR_ITEMS: PageSidebarMenuItem[] = [
  navItemFor('general'),
  navItemFor('interface'),
  navItemFor('browser'),
  navItemFor('repository'),
  navItemFor('prompts'),
  LOCAL_SECTION,
  navItemFor('system'),
  navItemFor('workspaces-local'),
  navItemFor('conversations'),
  navItemFor('clis-models'),
  navItemFor('mcp'),
  navItemFor('skills'),
  REMOTE_SECTION,
  navItemFor('connections'),
];

function navItemFor(id: Exclude<SettingsPageTab, 'docs'>): PageNavItem {
  const page = settingsPageContributions.find((contribution) => contribution.id === id);
  if (!page) throw new Error(`Unknown settings page: ${id}`);
  return toNavItem(page);
}

function toNavItem({ id, label, icon }: PageNavItem): PageNavItem {
  return { id, label, icon };
}

export const SettingsPage = observer(function SettingsPage({
  tab: activeTab,
  detail,
  onTabChange,
  openDetail,
  closeDetail,
  setDetailPath,
}: {
  tab: SettingsPageTab;
  detail?: string[];
  onTabChange: (tab: SettingsPageTab) => void;
  openDetail: (detailId: string) => void;
  closeDetail: () => void;
  setDetailPath: (path: string[] | undefined) => void;
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);
  const query = searchQuery.trim();
  const isSearching = query.length > 0;
  const activePage = settingsPageContributions.find(({ id }) => id === activeTab);
  const PageComponent = activePage?.component;
  const detailLevels =
    detail && activePage ? resolveDetailLevels(activePage, detail) : ([] as ResolvedDetailLevel[]);
  const deepestLevel = detailLevels.at(-1);

  const visiblePages = useMemo(() => {
    if (!isSearching) return [...settingsPageContributions];
    const matchedTabs = new Set(matchedTabsForQuery(query));
    return settingsPageContributions.filter((page) => matchedTabs.has(page.id));
  }, [isSearching, query]);

  const visibleItems = useMemo<PageSidebarMenuItem[]>(() => {
    if (!isSearching) return SIDEBAR_ITEMS;
    const matchCountByTab = new Map<string, number>();
    for (const entry of searchSettings(query)) {
      matchCountByTab.set(entry.tab, (matchCountByTab.get(entry.tab) ?? 0) + 1);
    }
    return visiblePages.map((page) => ({
      ...toNavItem(page),
      badge: String(matchCountByTab.get(page.id) ?? 0),
    }));
  }, [isSearching, query, visiblePages]);

  useEffect(() => {
    if (!isSearching || visiblePages.length === 0) return;
    if (!visiblePages.some((page) => page.id === activeTab)) {
      onTabChange(visiblePages[0]!.id);
    }
  }, [activeTab, isSearching, onTabChange, visiblePages]);

  // Invalid segments truncate to the longest valid prefix rather than closing
  // the whole detail stack.
  const validPath = deepestLevel?.path;
  useEffect(() => {
    if (detail && detail.length !== (validPath?.length ?? 0)) {
      setDetailPath(validPath);
    }
  }, [detail, setDetailPath, validPath]);

  const deepestSegment = deepestLevel?.path.at(-1);
  const detailView =
    deepestLevel && deepestSegment !== undefined && activePage
      ? {
          Component: deepestLevel.contribution.component,
          path: deepestLevel.path,
          detailId: deepestSegment,
          label: deepestLevel.label,
          pageId: activePage.id,
          pageLabel: activePage.label,
        }
      : null;

  const focusSearchInput = useCallback(() => {
    searchInputRef.current?.focus();
  }, []);

  useChordKeydown(
    'Mod+F',
    (event) => {
      event.preventDefault();
      focusSearchInput();
    },
    { enabled: true }
  );

  useChordKeydown(
    '/',
    (event) => {
      if (isTextInputFocusTarget(event.target)) return;
      event.preventDefault();
      focusSearchInput();
    },
    { enabled: true }
  );

  return (
    <SettingsSearchProvider query={searchQuery} setQuery={setSearchQuery}>
      <PageLayout
        sidebar={
          <PageLayout.SidebarMenu
            items={visibleItems}
            activeId={activeTab}
            draggable
            header={
              <SearchInput
                ref={searchInputRef}
                placeholder="Search settings"
                aria-label="Search settings"
                aria-keyshortcuts="Meta+F Control+F /"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onClear={() => setSearchQuery('')}
                shortcut={<SettingsSearchShortcut />}
              />
            }
            emptyMessage={isSearching ? 'No settings found' : undefined}
            footer={
              <button
                type="button"
                className="flex h-8 w-full items-center gap-2 rounded-md px-3 text-sm font-normal text-foreground-muted transition-colors hover:bg-background-1 hover:text-foreground"
                onClick={() => void openExternal('https://github.com/amywork777/hardcore')}
              >
                <Icon name="external-link" size="sm" />
                <span>View Docs</span>
              </button>
            }
            onSelect={(item) => {
              const page = settingsPageContributions.find(({ id }) => id === item.id);
              if (page) onTabChange(page.id);
            }}
          />
        }
      >
        {detailView ? (
          <PageLayout.Content>
            <div className="sticky top-0 z-10 bg-background pt-10 pb-4">
              <Breadcrumbs
                items={[
                  {
                    id: detailView.pageId,
                    label: detailView.pageLabel,
                    onSelect: () => setDetailPath(undefined),
                  },
                  ...detailLevels.map((level, index) => ({
                    id: level.path.join('/'),
                    label: level.label,
                    ...(index < detailLevels.length - 1
                      ? { onSelect: () => setDetailPath(level.path) }
                      : {}),
                  })),
                ]}
              />
            </div>
            <detailView.Component
              path={detailView.path}
              detailId={detailView.detailId}
              openDetail={openDetail}
              closeDetail={closeDetail}
            />
          </PageLayout.Content>
        ) : PageComponent ? (
          <PageLayout.Content>
            <PageComponent openDetail={openDetail} />
          </PageLayout.Content>
        ) : null}
      </PageLayout>
    </SettingsSearchProvider>
  );
});

function SettingsSearchShortcut() {
  const [, setLayoutVersion] = useState(0);

  useEffect(
    () => keyboardLayoutService.onDidChangeLayout(() => setLayoutVersion((version) => version + 1)),
    []
  );

  const keys = keyboardLayoutService.displayLabel(SETTINGS_SEARCH_HOTKEY, detectPlatformContext());

  return (
    <span aria-hidden="true" className="inline-flex items-center gap-0.5">
      {keys.map((key, index) => (
        <Kbd key={`${key}-${index}`}>{key}</Kbd>
      ))}
    </span>
  );
}
