import type React from 'react';
import type { TabBarItemProps, TabContentProps } from './tab-host';

/**
 * Plain-data identity for a single open tab.
 * The engine stores these and serializes them as { kind, tabId, isPreview, ...state }.
 * Live view-model state lives in the domain resource returned by initialize().
 */
export interface TabEntry<S = unknown> {
  readonly kind: string;
  readonly tabId: string;
  /** Mutable so the engine can promote a preview to a stable tab (handle.pin()). */
  isPreview: boolean;
  /**
   * Reactive, serializable domain state for this tab.
   * Mutated in-place; the snapshot serializer reads it directly (no per-kind hook).
   * Replaces the old readonly `payload` + `getSerializablePayload` escape hatch.
   */
  state: S;
}

/**
 * Minimal shape every domain resource must satisfy.
 * Domain managers ref-count their internal state inside initialize/dispose.
 */
export interface TabResource {
  /** Called when the engine permanently removes the tab. Must be idempotent. */
  dispose(): void;
  /**
   * Called when the tab becomes the active tab in a visible pane.
   * Use for telemetry scope, mark-seen, lazy bootstrap, etc.
   */
  onActivate?(): void;
  /**
   * Called when the user hovers or focuses a tab — before it becomes active.
   * Use for optimistic prefetch so that tab switching feels instant.
   */
  onActivateIntent?(): void;
}

/**
 * Controls which pane a programmatic open targets.
 *   'active'           – focused pane (default)
 *   'right' | 'left'   – adjacent pane (split if needed)
 *   { paneId: string } – explicit pane by ID
 */
export type OpenTarget = 'active' | 'left' | 'right' | { paneId: string };

/**
 * Capability handle given to resources at initialize time.
 * Resources use this to drive pin-on-edit, programmatic close, and new-tab
 * opens — without holding a direct store reference.
 */
export interface TabHandle {
  readonly tabId: string;
  /** Flip isPreview = false. Call when the resource gains user-authored content. */
  pin(): void;
  /**
   * Close this tab. By default runs the onBeforeClose veto (user-style close).
   * Pass { force: true } to skip the veto (programmatic/auto-close).
   * Returns a promise that resolves to true if the tab was actually closed.
   */
  close(opts?: { force?: boolean }): Promise<boolean>;
  /**
   * Open a tab in the view that owns this handle.
   * `kind` selects the provider; `args` are the domain open-args (the "searchParams");
   * `config` carries engine routing flags (target pane, preview, overrideState).
   */
  open(
    kind: string,
    args: Record<string, unknown>,
    config?: { target?: OpenTarget; preview?: boolean; overrideState?: boolean }
  ): void;
}

/**
 * A named capability surfaced through the tab context menu and command palette.
 * Examples: `rename`, `export`, `duplicate`.
 *
 */
export interface CommandEntry<T> {
  label: string;
  /**
   * Execute the command.
   * For rename commands, `args[0]` is the new name string provided by the inline editor.
   */
  // oxlint-disable-next-line typescript/no-explicit-any
  exec(resource: T, ...args: any[]): void;
  isAvailable?(resource: T): boolean;
}

/**
 * Generic ambient context passed to all tab-kind method implementations.
 * The engine only requires a stable viewId; domain-specific fields
 * (projectId, workspaceId, taskId) live in TaskTabContext in
 * features/tasks and are accessed via a cast at the provider boundary.
 */
export interface TabViewContext {
  /** Stable identifier for the view that owns this pane (e.g. taskId). */
  viewId: string;
}

/**
 * The composed resolved tab: engine identity stamped with the injected domain resource.
 * Components receive this instead of raw entry data so they never need findEntry().
 */
export type ResolvedTab<T extends TabResource = TabResource> = {
  readonly tabId: string;
  readonly kind: string;
  readonly isPreview: boolean;
  readonly isActive: boolean;
  readonly resource: T;
};

// Re-export renderer-chrome types so provider files can import from one location.
export type { TabBarItemProps, TabContentProps } from './tab-host';

/**
 * The core contract for a tab kind.
 *
 * Generic parameters
 *   K        – literal string kind discriminant
 *   S        – serializable state stored per tab entry (snapshot key)
 *   T        – the domain resource returned by initialize()
 *   OpenArgs – argument bag for opening a tab of this kind
 *              (may differ from S when onBeforeOpen transforms/enriches args)
 */
export interface TabProvider<
  K extends string = string,
  S = unknown,
  T extends TabResource = TabResource,
  OpenArgs = S,
> {
  readonly kind: K;

  /**
   * Stable identity for a tab, derived from its serializable state.
   * Used by the engine for: in-pane dedup, single-mount cross-pane focus,
   * and list-selection queries (isOpen / isActive).
   * Must be pure and stable across state mutations that do not change identity.
   */
  resourceKey(state: S): string;

  /**
   * 'single': at most one tab per resourceKey across ALL panes in a view.
   *           The engine enforces this at the layout level.
   * 'multi':  multiple tabs with the same resourceKey may coexist (default).
   */
  mount?: 'single' | 'multi';

  /**
   * Normalize/validate open args, perform synchronous side-effects
   * (e.g. create a browser session), and return the initial serializable state.
   * Return null to abort the open.
   *
   * If absent, the engine strips `preview`, `overrideState`, and `target` from
   * args and uses the rest as the initial state.
   */
  onBeforeOpen?(args: OpenArgs, ctx: TabViewContext): S | null;

  /**
   * Acquire or create the domain resource. Domain managers ref-count here.
   * Returns the resource, which the engine stores keyed by tabId and injects
   * into ResolvedTab.resource for render components.
   */
  initialize(entry: TabEntry<S>, handle: TabHandle, ctx: TabViewContext): T;

  /**
   * Veto a user-initiated close (e.g. show unsaved-changes dialog).
   * Return false (or Promise<false>) to cancel; true or Promise<true> to confirm.
   * Not called for force closes (handle.close({ force: true }) / closeTab()).
   */
  onBeforeClose?(entry: TabEntry<S>, resource: T, ctx: TabViewContext): boolean | Promise<boolean>;

  /**
   * Release the domain resource. Domain managers decrement ref counts here.
   * Called when the engine permanently removes the tab from the view.
   */
  dispose(entry: TabEntry<S>, resource: T, ctx: TabViewContext): void;

  /** Named capabilities surfaced as context-menu items and keyboard commands. */
  commands?: Record<string, CommandEntry<T>>;

  /** Renders the tab's chip in the tab bar. */
  TabBarItem: React.ComponentType<TabBarItemProps<T>>;
  /** Renders the drag ghost for this tab kind. */
  TabBarItemDragPreview: React.ComponentType<{ tab: ResolvedTab<T> }>;

  /**
   * The pane body component for this kind.
   * Mounted unconditionally by PaneContent regardless of which kind is active.
   */
  TabContent: React.ComponentType<TabContentProps>;
}
