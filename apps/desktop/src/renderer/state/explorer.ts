import { create } from "zustand";

import type { ExplorerTab, ExplorerTabKind } from "@shared/types";

/**
 * The explorer's one tab strip. Four kinds, no bottom panel — the terminal is
 * a tab like every other secondary surface (plan §3).
 *
 * P0 keeps the strip in memory and renders placeholders; P3 gives each kind a
 * real body and persists the strip through `explorer_tabs` (the table already
 * exists).
 */
type ExplorerState = {
  tabs: ExplorerTab[];
  activeId: string | null;

  open: (kind: ExplorerTabKind) => ExplorerTab;
  close: (id: string) => void;
  setActive: (id: string) => void;
};

let sequence = 0;
const nextId = () => `tab-${++sequence}`;

function blankTab(kind: ExplorerTabKind, order: number): ExplorerTab {
  const base = { id: nextId(), sessionId: "", order };
  switch (kind) {
    case "file":
      return { ...base, kind: "file", path: null, viewSource: false };
    case "review":
      return { ...base, kind: "review", scope: "last-turn" };
    case "browser":
      return { ...base, kind: "browser", url: null };
    case "terminal":
      return { ...base, kind: "terminal", ptyId: null, readOnly: false };
  }
}

export const useExplorer = create<ExplorerState>((set, get) => ({
  tabs: [],
  activeId: null,

  open: (kind) => {
    const tab = blankTab(kind, get().tabs.length);
    set((state) => ({ tabs: [...state.tabs, tab], activeId: tab.id }));
    return tab;
  },

  close: (id) =>
    set((state) => {
      const index = state.tabs.findIndex((tab) => tab.id === id);
      if (index < 0) {
        return state;
      }
      const tabs = state.tabs.filter((tab) => tab.id !== id).map((tab, order) => ({ ...tab, order }));
      // Closing the active tab selects its neighbour, the way every tabbed
      // editor does; closing an inactive one leaves the selection alone.
      const activeId =
        state.activeId === id ? (tabs[Math.min(index, tabs.length - 1)]?.id ?? null) : state.activeId;
      return { tabs, activeId };
    }),

  setActive: (activeId) => set({ activeId }),
}));

/** A short label for a tab, used by the strip and the command palette. */
export function tabTitle(tab: ExplorerTab): string {
  switch (tab.kind) {
    case "file":
      return tab.path ? (tab.path.split(/[\\/]/).pop() ?? tab.path) : "Untitled";
    case "review":
      return "Review";
    case "browser":
      return tab.url ?? "New tab";
    case "terminal":
      return "Terminal";
  }
}
