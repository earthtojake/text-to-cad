export type SidebarTab = 'conversations' | 'changes' | 'files' | 'analysis';

export type VisibleSidebarTab = Exclude<SidebarTab, 'analysis'>;

/** Keep old persisted Analysis sidebars useful after Analysis became an artifact, not a mode. */
export function visibleSidebarTab(tab: SidebarTab): VisibleSidebarTab {
  return tab === 'analysis' ? 'files' : tab;
}
