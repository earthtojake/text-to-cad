/**
 * ViewState — Solid signal-based replacement for MobX ViewStateStore.
 *
 * Uses a Solid store (Record<string, boolean>) for fine-grained per-key
 * reactivity: when isCollapsed(id) is called inside a reactive context
 * (createMemo, createEffect, JSX), only computations reading that specific
 * key re-run when it toggles.
 *
 * ViewState now lives in ChatState (not per-mount ChatRoot) so that collapse
 * state persists across view dispose/recreate (e.g. tab switches).
 *
 * Note: the stored boolean flag uses inverted semantics inherited from the
 * original store — `collapsed[id] === true` means "expanded". This is
 * intentionally preserved to avoid a large rename in this change; a future
 * rename to `isExpanded` is planned as Phase 3.
 */

import { createStore, produce } from 'solid-js/store';

export type ViewState = ReturnType<typeof createViewState>;

export function createViewState() {
  const [collapsed, setCollapsed] = createStore<Record<string, boolean>>({});

  return {
    isCollapsed: (id: string): boolean => collapsed[id] ?? false,

    toggleCollapsed: (id: string): void => {
      setCollapsed(id, !collapsed[id]);
    },

    setCollapsed: (id: string, value: boolean): void => {
      if (!value) {
        setCollapsed(
          produce((s) => {
            delete s[id];
          })
        );
      } else {
        setCollapsed(id, true);
      }
    },

    expandAll: (): void => {
      setCollapsed(
        produce((s) => {
          for (const key of Object.keys(s)) {
            delete s[key];
          }
        })
      );
    },

    /**
     * Returns a plain-object snapshot of all currently-set entries.
     * Used by ChatRoot onCleanup to persist state before dispose.
     */
    snapshot(): Record<string, boolean> {
      return { ...collapsed };
    },

    /**
     * Bulk-restore from a snapshot (e.g. after a view is recreated).
     * Replaces the entire store to match the provided entries.
     */
    restore(snap: Record<string, boolean>): void {
      setCollapsed(
        produce((s) => {
          for (const key of Object.keys(s)) {
            delete s[key];
          }
          for (const [k, v] of Object.entries(snap)) {
            if (v) s[k] = true;
          }
        })
      );
    },
  };
}
