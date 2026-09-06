import { create } from "zustand";

import type { BrowserTab, ExplorerTab, ExplorerTabKind, FileTab, TerminalTab } from "@shared/types";

/**
 * The explorer's one tab strip. Four kinds, no bottom panel — the terminal is
 * a tab like every other secondary surface (plan §3).
 *
 * The strip belongs to the **project**, not to a thread: a person with a file,
 * a terminal and a review open is looking at a directory, and closing a thread
 * should not take those away. It is loaded from `explorer_tabs` when the
 * active project changes and written back, debounced, on every mutation.
 *
 * Every mutation therefore goes through `commit`, which is the only place that
 * renumbers `order` and schedules the save. A setter that wrote `tabs`
 * directly would produce a strip whose order in the database disagreed with
 * the order on screen after the next reload.
 */

/** How long a burst of changes is collected before it reaches sqlite. */
const SAVE_DEBOUNCE_MS = 400;

/** The file tree's geometry — a preference, not a per-tab property. */
const TREE_WIDTH_KEY = "hardcore.explorer.treeWidth";
const TREE_COLLAPSED_KEY = "hardcore.explorer.treeCollapsed";
export const TREE_MIN_WIDTH = 180;
export const TREE_MAX_WIDTH = 480;
export const TREE_DEFAULT_WIDTH = 248;

function readLocal<T>(key: string, fallback: T, parse: (raw: string) => T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : parse(raw);
  } catch {
    // A renderer with storage blocked is not a renderer that should fail to
    // draw a file tree.
    return fallback;
  }
}

function writeLocal(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* see readLocal */
  }
}

/** Initial state for a new tab of each kind. */
type TabInit = {
  file: Partial<Pick<FileTab, "path" | "viewSource">>;
  review: Record<string, never>;
  browser: Partial<Pick<BrowserTab, "url">>;
  terminal: Partial<Pick<TerminalTab, "cwd" | "readOnly">>;
};

type ExplorerState = {
  /** The project the strip belongs to; null before one is chosen. */
  projectId: string | null;
  tabs: ExplorerTab[];
  activeId: string | null;
  /** True once the strip has been loaded for `projectId`. */
  ready: boolean;
  /** Codex's expand affordance: the explorer takes the whole window. */
  expanded: boolean;
  /** The file tab's right-hand tree. */
  treeCollapsed: boolean;
  treeWidth: number;
  /**
   * Bumped on every `files.changed` batch. Views that read the filesystem
   * subscribe to it instead of each holding a watcher subscription.
   */
  fsRevision: number;
  /** Paths touched by the last batch, so an open editor knows it is stale. */
  changedPaths: string[];
  /**
   * A path an agent asked to have revealed (`reveal` through the Hardcore MCP
   * server): the tree expands to it and selects it without opening it.
   * Transient — cleared when a file is opened or the project changes.
   */
  reveal: { path: string; directory: boolean } | null;

  bindProject: (projectId: string | null) => Promise<void>;
  open: <K extends ExplorerTabKind>(kind: K, init?: TabInit[K]) => ExplorerTab | null;
  /** Open a file, reusing a tab already showing it. */
  openFile: (path: string) => ExplorerTab | null;
  close: (id: string) => void;
  closeActive: () => void;
  setActive: (id: string) => void;
  /** Select the nth tab, 1-based — Cmd/Ctrl+1..9. */
  selectIndex: (index: number) => void;
  /** Drag reorder: move the tab with `id` to `toIndex`. */
  move: (id: string, toIndex: number) => void;
  update: (id: string, patch: Partial<ExplorerTab>) => void;
  setExpanded: (expanded: boolean) => void;
  toggleExpanded: () => void;
  setTreeCollapsed: (collapsed: boolean) => void;
  setTreeWidth: (width: number) => void;
  receiveChanges: (projectId: string, paths: string[]) => void;
  setReveal: (reveal: { path: string; directory: boolean } | null) => void;
};

let sequence = 0;
const nextId = () => `tab-${Date.now().toString(36)}-${++sequence}`;

function blankTab(
  kind: ExplorerTabKind,
  projectId: string,
  order: number,
  init: Record<string, unknown> = {},
): ExplorerTab {
  const base = { id: nextId(), projectId, order };
  switch (kind) {
    case "file":
      return { ...base, kind: "file", path: null, viewSource: false, ...init } as FileTab;
    case "review":
      return { ...base, kind: "review", scope: "all" as const, ...init };
    case "browser":
      return { ...base, kind: "browser", url: null, ...init } as BrowserTab;
    case "terminal":
      return {
        ...base,
        kind: "terminal",
        ptyId: null,
        cwd: null,
        readOnly: false,
        ...init,
      } as TerminalTab;
  }
}

let saveTimer: ReturnType<typeof setTimeout> | null = null;

/** Renumber, publish, and schedule the write. The one mutation path. */
function commit(
  set: (partial: Partial<ExplorerState>) => void,
  projectId: string | null,
  tabs: ExplorerTab[],
  activeId: string | null,
) {
  const ordered = tabs.map((tab, order) => ({ ...tab, order }) as ExplorerTab);
  set({ tabs: ordered, activeId });
  if (!projectId) {
    return;
  }
  if (saveTimer) {
    clearTimeout(saveTimer);
  }
  saveTimer = setTimeout(() => {
    saveTimer = null;
    void window.hardcore.explorer.saveTabs({ projectId, tabs: ordered }).catch(() => {
      // Persistence is a convenience; a failed write must not take the strip
      // the person is looking at down with it.
    });
  }, SAVE_DEBOUNCE_MS);
}

export const useExplorer = create<ExplorerState>((set, get) => ({
  projectId: null,
  tabs: [],
  activeId: null,
  ready: false,
  expanded: false,
  treeCollapsed: readLocal(TREE_COLLAPSED_KEY, false, (raw) => raw === "true"),
  treeWidth: readLocal(TREE_WIDTH_KEY, TREE_DEFAULT_WIDTH, (raw) => Number(raw) || TREE_DEFAULT_WIDTH),
  fsRevision: 0,
  changedPaths: [],
  reveal: null,

  bindProject: async (projectId) => {
    if (get().projectId === projectId && get().ready) {
      return;
    }
    // A pending save belongs to the project being left, not the one arriving.
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    const previous = get().projectId;
    if (previous && previous !== projectId) {
      void window.hardcore.explorer.unwatch({ projectId: previous }).catch(() => {});
    }
    set({ projectId, tabs: [], activeId: null, ready: false, changedPaths: [], reveal: null });
    if (!projectId) {
      set({ ready: true });
      return;
    }
    const [tabs] = await Promise.all([
      window.hardcore.explorer.loadTabs({ projectId }).catch(() => [] as ExplorerTab[]),
      window.hardcore.explorer.watch({ projectId }).catch(() => undefined),
    ]);
    // A slower load for a project the user has already navigated away from
    // must not overwrite the one they are looking at.
    if (get().projectId !== projectId) {
      return;
    }
    set({ tabs, activeId: tabs[0]?.id ?? null, ready: true });
  },

  open: (kind, init) => {
    const { projectId, tabs } = get();
    if (!projectId) {
      return null;
    }
    const tab = blankTab(kind, projectId, tabs.length, init as Record<string, unknown>);
    commit(set, projectId, [...tabs, tab], tab.id);
    return tab;
  },

  openFile: (filePath) => {
    const { projectId, tabs } = get();
    if (!projectId) {
      return null;
    }
    // Opening is the stronger reveal; a stale one would keep two rows lit.
    set({ reveal: null });
    // Reuse rather than stack duplicates: clicking the same file in the tree
    // twice is one tab, the way every editor behaves.
    const existing = tabs.find((tab) => tab.kind === "file" && tab.path === filePath);
    if (existing) {
      set({ activeId: existing.id });
      return existing;
    }
    // An empty file tab is the slot the `+` button made; fill it instead of
    // leaving an "Untitled" behind.
    const blank = tabs.find((tab) => tab.kind === "file" && tab.path === null);
    if (blank) {
      const next = tabs.map((tab) =>
        tab.id === blank.id ? ({ ...tab, path: filePath } as ExplorerTab) : tab,
      );
      commit(set, projectId, next, blank.id);
      return next.find((tab) => tab.id === blank.id) ?? null;
    }
    return get().open("file", { path: filePath });
  },

  close: (id) => {
    const { projectId, tabs, activeId } = get();
    const index = tabs.findIndex((tab) => tab.id === id);
    if (index < 0) {
      return;
    }
    const closing = tabs[index];
    if (closing?.kind === "terminal" && closing.ptyId) {
      // The pty belongs to the tab. Closing the tab is closing the shell.
      void window.hardcore.terminal.kill({ id: closing.ptyId }).catch(() => {});
    }
    const remaining = tabs.filter((tab) => tab.id !== id);
    const nextActive =
      activeId === id ? (remaining[Math.min(index, remaining.length - 1)]?.id ?? null) : activeId;
    commit(set, projectId, remaining, nextActive);
  },

  closeActive: () => {
    const { activeId } = get();
    if (activeId) {
      get().close(activeId);
    }
  },

  setActive: (activeId) => set({ activeId }),

  selectIndex: (index) => {
    const tab = get().tabs[index - 1];
    if (tab) {
      set({ activeId: tab.id });
    }
  },

  move: (id, toIndex) => {
    const { projectId, tabs, activeId } = get();
    const from = tabs.findIndex((tab) => tab.id === id);
    const to = Math.max(0, Math.min(toIndex, tabs.length - 1));
    if (from < 0 || from === to) {
      return;
    }
    const next = [...tabs];
    const [moved] = next.splice(from, 1);
    if (moved) {
      next.splice(to, 0, moved);
    }
    commit(set, projectId, next, activeId);
  },

  update: (id, patch) => {
    const { projectId, tabs, activeId } = get();
    const next = tabs.map((tab) => (tab.id === id ? ({ ...tab, ...patch } as ExplorerTab) : tab));
    commit(set, projectId, next, activeId);
  },

  setExpanded: (expanded) => set({ expanded }),
  toggleExpanded: () => set((state) => ({ expanded: !state.expanded })),

  setTreeCollapsed: (treeCollapsed) => {
    writeLocal(TREE_COLLAPSED_KEY, String(treeCollapsed));
    set({ treeCollapsed });
  },

  setTreeWidth: (width) => {
    const treeWidth = Math.round(Math.max(TREE_MIN_WIDTH, Math.min(TREE_MAX_WIDTH, width)));
    writeLocal(TREE_WIDTH_KEY, String(treeWidth));
    set({ treeWidth });
  },

  setReveal: (reveal) => set({ reveal }),

  receiveChanges: (projectId, paths) => {
    if (get().projectId !== projectId) {
      return;
    }
    set((state) => ({ fsRevision: state.fsRevision + 1, changedPaths: paths }));
  },
}));

/** The active tab, or null. */
export function useActiveTab(): ExplorerTab | null {
  return useExplorer((state) => state.tabs.find((tab) => tab.id === state.activeId) ?? null);
}

/** A short label for a tab, used by the strip and the command palette. */
export function tabTitle(tab: ExplorerTab): string {
  switch (tab.kind) {
    case "file":
      return tab.path ? (tab.path.split("/").pop() ?? tab.path) : "Untitled";
    case "review":
      return "Review";
    case "browser":
      return tab.url ? hostOf(tab.url) : "New tab";
    case "terminal":
      return "Terminal";
  }
}

/** A browser tab is labelled by its host — a full URL never fits the strip. */
export function hostOf(url: string): string {
  try {
    return new URL(url).host || url;
  } catch {
    return url;
  }
}
