import type { ResolvedTab, TabResource, TabViewContext } from './tab-provider';

/**
 * Narrow host interface that PaneStore implements.
 * UI components (tab bar, content panels) receive this instead of the full
 * store so they cannot reach into internal engine state directly.
 */
export interface TabHost {
  readonly resolvedTabs: ReadonlyArray<ResolvedTab>;
  readonly resolvedActiveTabId: string | undefined;
  /** The ambient context for this pane (viewId + any domain-specific fields). */
  readonly ctx: TabViewContext;

  /** Opens a tab of any registered kind. Untyped for use from resources/handles. */
  openKind(kind: string, args: unknown): void;

  setActiveTab(tabId: string): void;
  /** Sets isPreview = false (no-op when already stable). */
  pin(tabId: string): void;
  /** Force-close — no confirmation dialog, calls dispose, removes entry. */
  closeTab(tabId: string): void;
  /**
   * User-initiated close — awaits onBeforeClose veto, then closes if confirmed.
   */
  requestCloseTab(tabId: string): void;
  /** Closes every open tab except the given one. */
  closeOthers(tabId: string): void;
  /**
   * Signal hover/focus intent for a tab — fires resource.onActivateIntent().
   * No-op if the resource has no intent handler.
   */
  signalActivateIntent(tabId: string): void;

  readonly renameRequest: { tabId: string; nonce: number } | null;
  requestRename(tabId: string): void;
  clearRenameRequest(): void;
  /** Delegates to the active tab's commands.rename entry. */
  commitRename(tabId: string, name: string): void;
}

/** Props for a kind's TabBarItem component (rendered in the tab bar). */
export interface TabBarItemProps<T extends TabResource> {
  tab: ResolvedTab<T>;
  host: TabHost;
  ctx: TabViewContext;
}

/**
 * Props for a kind's Content component (the pane body area).
 *
 * PaneContent mounts every registered Content unconditionally — the
 * component decides visibility, keepalive, and async loading internally.
 */
export interface TabContentProps {
  host: TabHost;
  ctx: TabViewContext;
}
