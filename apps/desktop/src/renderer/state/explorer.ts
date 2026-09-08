import { create } from "zustand";

import type { DirEntry } from "@shared/ipc/explorer";
import { FILE_PANEL_TREE, PANE_LIMITS } from "@shared/types";
import type {
  BrowserTab,
  ExplorerRoot,
  ExplorerTab,
  ExplorerTabKind,
  FileTab,
  ReviewTab,
  TerminalTab,
} from "@shared/types";

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
 *
 * The strip has a **root** as well as a project (plan §9, `ExplorerRoot` in
 * `@shared/types`): the directory new tabs open in and the tree lists. It is
 * the project directory until the active session runs in a worktree, and
 * then it is that worktree — `state/bridge.ts` derives it from the session
 * selection and calls `setRoot`. A tab keeps the root it was opened in, so
 * switching threads changes where the *next* file opens and which tree the
 * pane shows, not what an open tab is looking at. The tree's state is kept
 * per root, because a worktree and the checkout are different trees with
 * the same names in them.
 */

/** How long a burst of changes is collected before it reaches sqlite. */
const SAVE_DEBOUNCE_MS = 400;

/**
 * The file tab's panel column, in pixels — one width for every panel that
 * can be in it (the tree, the CAD theme editor, the CAD Inspector), because
 * it is one column. A preference, not a per-tab property; WHICH panel is
 * open is per tab (`FileTabSchema.panel`).
 */
const PANEL_WIDTH_KEY = "hardcore.explorer.panelWidth";
/** Whether the pane itself is closed, per project id (see `collapsed`). */
const PANE_COLLAPSED_KEY = "hardcore.explorer.collapsed";
/** How wide it is when it is open, per project id (see `width`). */
const PANE_WIDTH_KEY = "hardcore.explorer.width";
export const PANEL_MIN_WIDTH = 180;
export const PANEL_MAX_WIDTH = 480;
export const PANEL_DEFAULT_WIDTH = 248;

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

/** One of the per-project maps in localStorage, parsed defensively. */
function byProject<T>(key: string): Record<string, T> {
  return readLocal<Record<string, T>>(key, {}, (raw) => {
    try {
      const parsed: unknown = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? (parsed as Record<string, T>) : {};
    } catch {
      return {};
    }
  });
}

/**
 * The pane is closed until something opens it, and a person's own choice is
 * remembered for the project they made it in.
 *
 * Per project rather than per app, because whether the right-hand pane earns
 * its width is a fact about the work: a CAD project is looked at, a scratch
 * folder is talked to. Opening a file, a review, a browser or a terminal
 * shows the pane without writing anything — the preference is what the person
 * chose, not what an agent's tool call did.
 *
 * There is no entry for "no project": without one the explorer is not drawn
 * at all, so there is no choice to remember and nothing to remember it for.
 */
function collapsedFor(projectId: string): boolean {
  return byProject<boolean>(PANE_COLLAPSED_KEY)[projectId] ?? true;
}

/**
 * The pane's width for a project, in pixels. Its pair with `collapsed` is the
 * explorer's whole state: a collapse keeps the width, so the toggle brings
 * the pane back the size it was rather than at its floor.
 */
function widthFor(projectId: string): number {
  const stored = byProject<number>(PANE_WIDTH_KEY)[projectId];
  return typeof stored === "number" && stored > 0 ? stored : PANE_LIMITS.explorer.default;
}

/** The open folders and the listings of one root's tree. */
export type TreeState = {
  open: ReadonlySet<string>;
  listings: Record<string, DirEntry[]>;
};

/** The key a root's tree is filed under. */
export function treeKey(root: ExplorerRoot): string {
  return root ?? "";
}

// The root is always open; there is no row for it to be shut by.
const EMPTY_TREE: TreeState = { open: new Set([""]), listings: {} };

/** Initial state for a new tab of each kind. */
type TabInit = {
  file: Partial<Pick<FileTab, "path" | "root" | "panel">>;
  review: Partial<Pick<ReviewTab, "scope" | "sessionId">>;
  browser: Partial<Pick<BrowserTab, "url">>;
  terminal: Partial<Pick<TerminalTab, "cwd" | "readOnly">>;
};

type ExplorerState = {
  /** The project the strip belongs to; null before one is chosen. */
  projectId: string | null;
  /**
   * Where new tabs open and what the tree lists: null for the project
   * directory, else the active session's worktree (see the note above).
   */
  root: ExplorerRoot;
  tabs: ExplorerTab[];
  activeId: string | null;
  /** True once the strip has been loaded for `projectId`. */
  ready: boolean;
  /**
   * The pane's own state: closed until something opens it, and remembered for
   * the project once the person says otherwise. The session column fills the
   * window while it is closed, and with no project bound the pane is not
   * rendered at all (`Shell`).
   */
  collapsed: boolean;
  /**
   * How wide the pane is when it is open, in pixels — the other half of the
   * pair. A drag writes it, a collapse keeps it, and the toggle brings the
   * pane back at it. Per project, like `collapsed`.
   */
  width: number;
  /** How wide the file tab's panel column is, whichever panel is in it. */
  panelWidth: number;
  /**
   * Which folders each root's tree has open, and the listing behind each one,
   * keyed by `treeKey(root)`.
   *
   * Here rather than in the component because the file tab is unmounted every
   * time another tab is selected — and *opening a file makes a tab*, so the
   * tree that the person had just expanded three levels into was thrown away
   * by the click that used it. The tree belongs to the root, like the tab;
   * the listings ride along so coming back does not re-read every open
   * folder.
   */
  trees: Record<string, TreeState>;
  /**
   * Bumped on every `files.changed` batch. Views that read the filesystem
   * subscribe to it instead of each holding a watcher subscription.
   */
  fsRevision: number;
  /** Paths touched by the last batch, and the root they are under, so an open editor knows it is stale. */
  changedPaths: string[];
  changedRoot: ExplorerRoot;
  /**
   * A path an agent asked to have revealed (`reveal` through the Hardcore MCP
   * server): the tree expands to it and selects it without opening it.
   * Transient — cleared when a file is opened or the project changes.
   */
  reveal: { path: string; directory: boolean; root: ExplorerRoot } | null;
  /**
   * A reference a CAD tab should select once its model is up: a link in the
   * transcript said `bracket.step#o1.2`. The nonce makes clicking the same
   * link twice a second selection. Consumed by `CadRenderer`, which hands it
   * to the viewer's `selectReference` prop.
   */
  cadSelection: { tabId: string; selector: string; nonce: number } | null;
  /**
   * A request for a CAD tab to send its viewport to the composer — the
   * composer's `+` menu asking for the same picture the viewer's own camera
   * button takes. Nonce-keyed like `cadSelection`, so asking twice is two
   * captures, and consumed by `CadRenderer` as the viewer's `captureRequest`.
   */
  cadCapture: { tabId: string; nonce: number } | null;

  bindProject: (projectId: string | null, root?: ExplorerRoot) => Promise<void>;
  /**
   * Change the root new tabs open in. The tree state of the root being
   * left is kept, so coming back to a thread finds its folders still open.
   */
  setRoot: (root: ExplorerRoot) => void;
  open: <K extends ExplorerTabKind>(kind: K, init?: TabInit[K]) => ExplorerTab | null;
  /**
   * Open a file, reusing a tab already showing it. `root` defaults to the
   * active one; an agent's `open_file` names the session's.
   */
  openFile: (path: string, root?: ExplorerRoot) => ExplorerTab | null;
  close: (id: string) => void;
  closeActive: () => void;
  setActive: (id: string) => void;
  /** Select the nth tab, 1-based — Cmd/Ctrl+1..9. */
  selectIndex: (index: number) => void;
  /** Drag reorder: move the tab with `id` to `toIndex`. */
  move: (id: string, toIndex: number) => void;
  update: (id: string, patch: Partial<ExplorerTab>) => void;
  /** A person's choice, remembered for the project they made it in. */
  setCollapsed: (collapsed: boolean) => void;
  toggleCollapsed: () => void;
  /** A drag's result, remembered for the project it was made in. */
  setWidth: (width: number) => void;
  /** Something opened: show the pane, leaving the stored preference alone. */
  show: () => void;
  /** A drag of the panel column's handle; it clamps. */
  setPanelWidth: (width: number) => void;
  /** Open or shut folders in a root's tree. The updater sees the current set. */
  setTreeOpen: (root: ExplorerRoot, next: (current: ReadonlySet<string>) => ReadonlySet<string>) => void;
  /** File one directory's listing in a root's tree. */
  setTreeListing: (root: ExplorerRoot, directory: string, entries: DirEntry[]) => void;
  receiveChanges: (projectId: string, root: ExplorerRoot, paths: string[]) => void;
  setReveal: (reveal: { path: string; directory: boolean; root: ExplorerRoot } | null) => void;
  /**
   * Expand the tree to `path` and select it without opening it — an agent's
   * `reveal`, a folder link in the transcript. The tree lives in a file tab
   * of the same root, so one is brought forward or opened first.
   */
  revealPath: (path: string, directory: boolean, root: ExplorerRoot) => void;
  selectCadReference: (tabId: string, selector: string) => void;
  /** Ask a CAD tab for a capture of what it is showing. */
  captureCad: (tabId: string) => void;
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
      return { ...base, kind: "file", path: null, root: null, panel: null, ...init } as FileTab;
    case "review":
      return { ...base, kind: "review", scope: "all" as const, sessionId: null, ...init };
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

/**
 * One tab per file per root. Whatever produced the list — an open, a
 * restore, a drag — a second tab for a path already in it is dropped, and a
 * selection that pointed at the dropped one moves to the survivor, so the
 * strip can never show two tabs for one file. Blank file tabs (`path`
 * null) are slots, not files, and are left alone.
 */
export function dedupeFileTabs(
  tabs: ExplorerTab[],
  activeId: string | null,
): { tabs: ExplorerTab[]; activeId: string | null } {
  const seen = new Map<string, string>();
  const dropped = new Map<string, string>();
  const kept = tabs.filter((tab) => {
    if (tab.kind !== "file" || tab.path === null) {
      return true;
    }
    const key = `${tab.root ?? ""}\u0000${tab.path}`;
    const survivor = seen.get(key);
    if (survivor) {
      dropped.set(tab.id, survivor);
      return false;
    }
    seen.set(key, tab.id);
    return true;
  });
  return { tabs: kept, activeId: activeId && dropped.has(activeId) ? (dropped.get(activeId) ?? null) : activeId };
}

/** Renumber, publish, and schedule the write. The one mutation path. */
function commit(
  set: (partial: Partial<ExplorerState>) => void,
  projectId: string | null,
  tabs: ExplorerTab[],
  activeId: string | null,
) {
  const unique = dedupeFileTabs(tabs, activeId);
  const ordered = unique.tabs.map((tab, order) => ({ ...tab, order }) as ExplorerTab);
  set({ tabs: ordered, activeId: unique.activeId });
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

/** The watcher for one root, started and stopped with the binding. */
function watch(projectId: string, root: ExplorerRoot): Promise<void> {
  return window.hardcore.explorer.watch({ projectId, ...(root ? { root } : {}) }).catch(() => undefined);
}

function unwatch(projectId: string, root: ExplorerRoot): void {
  void window.hardcore.explorer.unwatch({ projectId, ...(root ? { root } : {}) }).catch(() => {});
}

export const useExplorer = create<ExplorerState>((set, get) => ({
  projectId: null,
  root: null,
  tabs: [],
  activeId: null,
  ready: false,
  collapsed: true,
  width: PANE_LIMITS.explorer.default,
  panelWidth: readLocal(PANEL_WIDTH_KEY, PANEL_DEFAULT_WIDTH, (raw) => Number(raw) || PANEL_DEFAULT_WIDTH),
  trees: {},
  fsRevision: 0,
  changedPaths: [],
  changedRoot: null,
  reveal: null,
  cadSelection: null,
  cadCapture: null,

  bindProject: async (projectId, root = null) => {
    if (get().projectId === projectId && get().ready) {
      if (get().root !== root) {
        get().setRoot(root);
      }
      return;
    }
    // A pending save belongs to the project being left, not the one arriving.
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    const previous = get().projectId;
    if (previous && previous !== projectId) {
      unwatch(previous, get().root);
    }
    set({
      projectId,
      root,
      tabs: [],
      activeId: null,
      ready: false,
      changedPaths: [],
      changedRoot: null,
      reveal: null,
      cadSelection: null,
      // Each project keeps its own answer to "is the pane worth the width".
      // Without a project there is no pane at all (`Shell`), and closed is
      // the state it comes back to when one arrives.
      collapsed: projectId ? collapsedFor(projectId) : true,
      width: projectId ? widthFor(projectId) : PANE_LIMITS.explorer.default,
      // A different project is a different set of trees, with nothing to carry over.
      trees: {},
    });
    if (!projectId) {
      set({ ready: true });
      return;
    }
    // The project's CAD runtime starts now — the probe, the viewer for this
    // root, the build daemon — so the first CAD file finds them up
    // (src/main/cad/index.ts, `warmCad`). Nothing waits on it.
    void window.hardcore.cad.warm({ projectId, ...(root ? { root } : {}) }).catch(() => {});
    const [tabs] = await Promise.all([
      window.hardcore.explorer.loadTabs({ projectId }).catch(() => [] as ExplorerTab[]),
      watch(projectId, root),
    ]);
    // A slower load for a project the user has already navigated away from
    // must not overwrite the one they are looking at.
    if (get().projectId !== projectId) {
      return;
    }
    // A strip written by an older build may hold two tabs for one file.
    const restored = dedupeFileTabs(tabs, tabs[0]?.id ?? null);
    set({ tabs: restored.tabs, activeId: restored.activeId, ready: true });
  },

  setRoot: (root) => {
    const { projectId, root: previous } = get();
    if (previous === root) {
      return;
    }
    if (projectId) {
      unwatch(projectId, previous);
      void watch(projectId, root);
    }
    // A reveal points into one tree; it means nothing in the next one.
    set({ root, reveal: null });
  },

  open: (kind, init) => {
    const { projectId, root, tabs } = get();
    if (!projectId) {
      return null;
    }
    // A tab nobody can see is not an open tab: every kind reveals the pane.
    get().show();
    // A file or a terminal opens in the active root unless told otherwise —
    // the worktree of the thread being talked to, or the project.
    const rooted: Record<string, unknown> =
      kind === "file"
        ? { root, ...(init as Record<string, unknown> | undefined) }
        : kind === "terminal"
          ? { cwd: root, ...(init as Record<string, unknown> | undefined) }
          : { ...(init as Record<string, unknown> | undefined) };
    // A file that is already open is that tab, whichever door was used.
    if (kind === "file" && typeof rooted.path === "string") {
      const existing = tabs.find(
        (tab) => tab.kind === "file" && tab.path === rooted.path && tab.root === (rooted.root ?? null),
      );
      if (existing) {
        set({ activeId: existing.id });
        return existing;
      }
    }
    const tab = blankTab(kind, projectId, tabs.length, rooted);
    commit(set, projectId, [...tabs, tab], tab.id);
    return tab;
  },

  openFile: (filePath, root) => {
    const { projectId, tabs } = get();
    if (!projectId) {
      return null;
    }
    const target = root === undefined ? get().root : root;
    // Opening is the stronger reveal; a stale one would keep two rows lit.
    set({ reveal: null });
    get().show();
    // Reuse rather than stack duplicates: clicking the same file in the tree
    // twice is one tab, the way every editor behaves. The same path in two
    // roots is two files — the checkout's and the worktree's — and two tabs.
    const existing = tabs.find((tab) => tab.kind === "file" && tab.path === filePath && tab.root === target);
    if (existing) {
      set({ activeId: existing.id });
      return existing;
    }
    // An empty file tab is the slot the `+` button made; fill it instead of
    // leaving an "Untitled" behind.
    const blank = tabs.find((tab) => tab.kind === "file" && tab.path === null);
    if (blank) {
      const next = tabs.map((tab) =>
        tab.id === blank.id ? ({ ...tab, path: filePath, root: target } as ExplorerTab) : tab,
      );
      commit(set, projectId, next, blank.id);
      return next.find((tab) => tab.id === blank.id) ?? null;
    }
    return get().open("file", { path: filePath, root: target });
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

  setCollapsed: (collapsed) => {
    const { projectId } = get();
    // No project, no explorer: there is nothing for a preference to be about.
    if (!projectId) {
      return;
    }
    writeLocal(PANE_COLLAPSED_KEY, JSON.stringify({ ...byProject<boolean>(PANE_COLLAPSED_KEY), [projectId]: collapsed }));
    set({ collapsed });
  },

  toggleCollapsed: () => get().setCollapsed(!get().collapsed),

  setWidth: (width) => {
    const { projectId } = get();
    const rounded = Math.round(width);
    if (!projectId || rounded <= 0) {
      return;
    }
    writeLocal(PANE_WIDTH_KEY, JSON.stringify({ ...byProject<number>(PANE_WIDTH_KEY), [projectId]: rounded }));
    set({ width: rounded });
  },

  show: () => {
    if (get().collapsed) {
      set({ collapsed: false });
    }
  },

  setPanelWidth: (width) => {
    const panelWidth = Math.round(Math.max(PANEL_MIN_WIDTH, Math.min(PANEL_MAX_WIDTH, width)));
    writeLocal(PANEL_WIDTH_KEY, String(panelWidth));
    set({ panelWidth });
  },

  setTreeOpen: (root, next) =>
    set((state) => {
      const key = treeKey(root);
      const tree = state.trees[key] ?? EMPTY_TREE;
      const open = next(tree.open);
      // An updater that changes nothing — a reveal of a path already open —
      // returns the same set, and zustand's subscribers stay put.
      return open === tree.open ? state : { trees: { ...state.trees, [key]: { ...tree, open } } };
    }),

  setTreeListing: (root, directory, entries) =>
    set((state) => {
      const key = treeKey(root);
      const tree = state.trees[key] ?? EMPTY_TREE;
      return { trees: { ...state.trees, [key]: { ...tree, listings: { ...tree.listings, [directory]: entries } } } };
    }),

  setReveal: (reveal) => set({ reveal }),

  revealPath: (path, directory, root) => {
    const explorer = get();
    if (!explorer.projectId) {
      return;
    }
    explorer.show();
    const fileTab =
      explorer.tabs.find((tab) => tab.id === explorer.activeId && tab.kind === "file" && tab.root === root) ??
      explorer.tabs.find((tab) => tab.kind === "file" && tab.root === root);
    if (fileTab) {
      set({ activeId: fileTab.id });
    } else {
      explorer.open("file", { root });
    }
    // The tree is the panel that can show a path, so revealing one opens it
    // — over whatever else that tab had open, because one panel is open at a
    // time (`FileTabSchema.panel`).
    if (fileTab) {
      explorer.update(fileTab.id, { panel: FILE_PANEL_TREE });
    }
    set({ reveal: { path, directory, root } });
  },

  selectCadReference: (tabId, selector) =>
    set((state) => ({ cadSelection: { tabId, selector, nonce: (state.cadSelection?.nonce ?? 0) + 1 } })),

  captureCad: (tabId) =>
    set((state) => ({ cadCapture: { tabId, nonce: (state.cadCapture?.nonce ?? 0) + 1 } })),

  receiveChanges: (projectId, root, paths) => {
    if (get().projectId !== projectId) {
      return;
    }
    set((state) => ({ fsRevision: state.fsRevision + 1, changedPaths: paths, changedRoot: root }));
  },
}));

/** One root's tree: its open folders and listings, or the empty tree. */
export function useTree(root: ExplorerRoot): TreeState {
  return useExplorer((state) => state.trees[treeKey(root)] ?? EMPTY_TREE);
}

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
