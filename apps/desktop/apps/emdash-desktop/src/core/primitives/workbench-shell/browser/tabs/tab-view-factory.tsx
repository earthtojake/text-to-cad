/**
 * Generic tab-view factory.
 *
 * `createTabView` wires a set of concrete providers into a fully typed surface:
 * a registry, a PaneLayoutStore constructor, typed React context hooks, and a
 * per-row selection hook. It has no knowledge of any specific feature; that
 * wiring lives in feature-specific modules (e.g. `tasks/task-tab-registry.tsx`).
 *
 * Usage:
 *
 *   const myView = createTabView([fooProvider, barProvider] as const);
 *
 *   const paneLayout = myView.createPaneLayoutStore(ctx, {
 *     snapshotMemento: myLayoutMementoHandle,
 *   });
 *   paneLayout.open('foo', { ... });   // typed ✓
 */

import { type ReactNode } from 'react';
import type { TabViewContext } from './core/tab-provider';
import {
  createTabRegistry,
  type AnyTabProvider,
  type KindOf,
  type OpenArgsOf,
  type TabOpenOptions,
  type TypedTabRegistry,
} from './core/tab-provider-registry';
import { PaneLayoutProvider, usePaneLayoutContext } from './pane-layout-context';
import { PaneLayoutStore } from './pane-layout-store';
import type { PaneLayoutSnapshotMemento } from './persistence';

export function createTabView<const P extends readonly AnyTabProvider[]>(providers: P) {
  type R = TypedTabRegistry<P>;

  const registry = createTabRegistry(providers);

  /** Creates a typed PaneLayoutStore suitable for threading into a MobX state tree. */
  function createPaneLayoutStore(
    ctx: TabViewContext,
    opts?: {
      /** Memento document to hydrate from and persist to. Absent means no persistence. */
      snapshotMemento?: PaneLayoutSnapshotMemento;
      onActiveTabChange?: (tabId: string | undefined) => void;
      /** Called when a pane group is destroyed; see PaneLayoutStore. */
      onPaneDestroyed?: (paneId: string) => void;
    }
  ): PaneLayoutStore<R> {
    return new PaneLayoutStore<R>(registry, ctx, opts?.snapshotMemento, opts);
  }

  /**
   * Typed wrapper around `usePaneLayoutContext()`.
   * Must be called inside a TabLayoutProvider.
   */
  function useTabLayout(): PaneLayoutStore<R> {
    return usePaneLayoutContext() as PaneLayoutStore<R>;
  }

  /**
   * Typed React context provider for the layout store.
   * Delegates to the generic `PaneLayoutProvider` so `usePaneLayoutContext()`
   * in the generic chrome (e.g. tab-drag-preview.tsx) continues to resolve.
   */
  function TabLayoutProvider({
    layout,
    children,
  }: {
    layout: PaneLayoutStore<R>;
    children: ReactNode;
  }): ReactNode {
    return <PaneLayoutProvider paneLayout={layout}>{children}</PaneLayoutProvider>;
  }

  /**
   * Per-row selection hook. Returns isOpen / isActive / isActiveAnyPane flags
   * and a typed open() for the given kind + resourceKey.
   * Must be called inside a TabLayoutProvider.
   */
  function useTabSelection<K extends KindOf<R>>(kind: K, resourceKey: string) {
    const layout = useTabLayout();
    return {
      isOpen: layout.isOpen(kind, resourceKey),
      isActive: layout.isActiveInFocusedPane(kind, resourceKey),
      isActiveAnyPane: layout.isActiveInAnyPane(kind, resourceKey),
      open: (args: OpenArgsOf<R, K>, config?: TabOpenOptions) => layout.open(kind, args, config),
    };
  }

  return { registry, createPaneLayoutStore, useTabLayout, useTabSelection, TabLayoutProvider };
}
