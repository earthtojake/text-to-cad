'use client';

import { useState } from 'react';
import { useDefaultLayout, type Layout } from 'react-resizable-panels';

/**
 * Storage adapter for panel-layout persistence. Fully synchronous:
 * `useDefaultLayout` reads `getItem` through `useSyncExternalStore` on every
 * render, so implementations must be fast and return value-stable strings for
 * unchanged values. The app injects its memento-backed facade here.
 */
export type LayoutStorage = Pick<Storage, 'getItem' | 'setItem'>;

export interface CollapsiblePanelBindingOptions {
  /** Unique persistence id for this group's layout. */
  storageKey: string;
  /** Storage adapter (the app passes its memento facade). */
  storage: LayoutStorage;
  /** All panel ids rendered when the collapsible panel is open, in order. */
  panelIds: string[];
  /** Id of the panel that opens/closes. */
  collapsiblePanelId: string;
  /** Semantic open flag from the state store. */
  open: boolean;
  /** Semantic close command; called when a drag settles below `closeThreshold`. */
  onCloseRequest: () => void;
  /** Size (percent of group, 0..100) below which a settled drag closes. Default 8. */
  closeThreshold?: number;
}

export interface CollapsiblePanelBinding {
  /** Spread onto the `Resizable.Group`. */
  groupProps: {
    defaultLayout: Layout | undefined;
    onLayoutChanged: (layout: Layout) => void;
  };
  /**
   * Spread onto the collapsible `Resizable.Panel` — including `id`, which the
   * binding owns (it is generation-suffixed after a threshold close; see the
   * guard comment inside the hook).
   */
  collapsiblePanelProps: {
    id: string;
    defaultSize: string | undefined;
  };
}

/**
 * Binds a semantic open/closed flag to a collapsible react-resizable-panels
 * panel under the "never program the panels" contract:
 *
 * 1. Visibility is store-driven conditional rendering — the consumer mounts
 *    the panel (and its handle) only while `open`; the hook makes no
 *    imperative collapse/expand/resize/setLayout calls.
 * 2. Pixel sizes belong to the library; persistence goes through the
 *    library's own `useDefaultLayout` with the injected storage adapter.
 * 3. The single semantic/pixel crossing point is drag-to-close: a layout that
 *    settles below `closeThreshold` issues `onCloseRequest` (which unmounts
 *    the panel). Sizes in, commands out — sizes are never stored in app state.
 *
 * The hook also encapsulates two non-obvious library traps (verified against
 * react-resizable-panels v4.11) so no call site rediscovers them; see the
 * generation-id and sliver guard comments below.
 */
export function useCollapsiblePanelBinding(
  options: CollapsiblePanelBindingOptions
): CollapsiblePanelBinding {
  const {
    storageKey,
    storage,
    panelIds,
    collapsiblePanelId,
    open,
    onCloseRequest,
    closeThreshold = 8,
  } = options;

  // GENERATION-ID GUARD ("poisoned panel memory"): when a panel unmounts and
  // later re-enters a still-mounted group under the SAME id, the library
  // restores it from its own in-memory registry for that id and IGNORES both
  // the group's `defaultLayout` (only read at group mount) and the panel's
  // `defaultSize`. After a drag-to-close, that memory holds the sub-threshold
  // sliver the drag settled at — a naive reopen re-enters at the sliver, the
  // first onLayoutChanged reports it, and the binding immediately closes
  // again (an infinite open/close trap). Fix, within the "never program the
  // panels" contract: bump a generation suffix on the panel id after every
  // threshold-close, so the re-entering panel is a brand-new identity to the
  // library and its `defaultSize` (the last persisted good size) is honored.
  // The suffix is stripped before persisting so storage keys stay stable.
  const [generation, setGeneration] = useState(0);
  const generationId =
    generation === 0 ? collapsiblePanelId : `${collapsiblePanelId}@${generation}`;

  // Always ask for the "open" combination: the read key is derived from
  // panelIds, and the closed layout (filler at 100%) carries no information
  // worth restoring.
  const { defaultLayout, onLayoutChanged: persist } = useDefaultLayout({
    id: storageKey,
    panelIds,
    storage,
  });

  const onLayoutChanged = (rawLayout: Layout) => {
    // Normalize the generation-suffixed id back to the canonical panel id so
    // storage never sees generation churn.
    const layout: Layout = {};
    for (const [id, size] of Object.entries(rawLayout)) {
      layout[id === generationId ? collapsiblePanelId : id] = size;
    }
    const size = layout[collapsiblePanelId];
    // SLIVER GUARD, part 1: onLayoutChanged also fires on mount and on panel
    // enter/leave reflows — a layout settling while closed is the unmount
    // reflow (only the filler panel remains). Persisting it would poison the
    // stored layout, so skip it entirely.
    if (!open || size === undefined) {
      return;
    }
    if (size < closeThreshold) {
      // THE one semantic/pixel crossing point: a user drag settled below the
      // close threshold. Issue the semantic command (unmounts the panel) and —
      // SLIVER GUARD, part 2 — deliberately do NOT persist the sub-threshold
      // size, otherwise the next open would restore a sliver. Bump the
      // generation so the next mount escapes the library's in-memory record
      // of that sliver (see the generation-id guard above).
      setGeneration((g) => g + 1);
      onCloseRequest();
      return;
    }
    persist(layout);
  };

  const restoredSize = defaultLayout?.[collapsiblePanelId];

  return {
    groupProps: { defaultLayout, onLayoutChanged },
    collapsiblePanelProps: {
      id: generationId,
      // Layout values are percentages; bare numbers mean pixels to the panel
      // prop parser, so serialize with an explicit '%'.
      defaultSize: restoredSize !== undefined ? `${restoredSize}%` : undefined,
    },
  };
}
