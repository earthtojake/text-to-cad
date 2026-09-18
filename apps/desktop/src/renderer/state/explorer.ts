import { FILE_PANEL_TREE, PANEL_DEFAULT_WIDTH, clampPanelWidth } from "@hardcore/ui/navigation";
import { create } from "zustand";

import { reconcileFileTree, movedFilePath } from "@hardcore/ui/file-viewer";
import { deleteDrawingScene } from "@renderer/state/drawings";
import { viewerFileChange } from "@renderer/features/explorer/file-changes";
import type { DirEntry, FileChange } from "@shared/ipc/explorer";
import { PANE_LIMITS } from "@shared/types";
import type {
  BrowserTab,
  DrawingTab,
  PersistedExplorerTab,
  ExplorerRoot,
  ExplorerTab,
  ExplorerTabKind,
  FileTab,
  ReviewTab,
  TerminalTab,
} from "@shared/types";

/**
 * The explorer's one tab strip. No bottom panel — the terminal is
 * a tab like every other secondary surface (plan §3).
 *
 * The strip belongs to the **project**, not to a thread: a person with a file,
 * a terminal and a review open is looking at a directory, and closing a thread
 * should not take those away. It is loaded from `explorer_tabs` when the
 * active project changes and written back, debounced, on every mutation.
 * Scratch drawings stay in renderer memory across project switches and are
 * excluded from every persistence snapshot.
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
 * can be in it (the tree or the CAD Inspector), because
 * it is one column. A preference, not a per-tab property; WHICH panel is
 * open is per tab (`FileTabSchema.panel`).
 */
const PANEL_WIDTH_KEY = "hardcore.explorer.panelWidth";
/** Whether the pane itself is closed, per project id (see `collapsed`). */
const PANE_COLLAPSED_KEY = "hardcore.explorer.collapsed";
/** How wide it is when it is open, per project id (see `width`). */
const PANE_WIDTH_KEY = "hardcore.explorer.width";
/**
 * The column's range and its default are the shared shell's
 * (`FilePanelColumn.jsx`), which is the component that draws it — so the
 * standalone CAD Viewer's panel is the same size as this one rather than a
 * second opinion about how wide a panel should be.
 */

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
  drawing: Partial<Pick<DrawingTab, "root" | "title">>;
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
  changedEntries: FileChange[];
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
  cadSelection: { projectId: string; tabId: string; path: string; root: ExplorerRoot; selector: string; nonce: number } | null;
  /**
   * A request for a CAD tab to send its viewport to the composer — the
   * composer's `+` menu asking for the same picture the viewer's own camera
   * button takes. Nonce-keyed like `cadSelection`, so asking twice is two
   * captures, and consumed by `CadRenderer` as the viewer's `captureRequest`.
   */
  cadCapture: { projectId: string; tabId: string; path: string; root: ExplorerRoot; nonce: number } | null;

  bindProject: (projectId: string | null, root?: ExplorerRoot) => Promise<void>;
  /**
   * Change the root new tabs open in. The tree state of the root being
   * left is kept, so coming back to a thread finds its folders still open.
   */
  setRoot: (root: ExplorerRoot) => void;
  /** Dispose scratch drawings when their project is removed. */
  discardProjectDrawings: (projectId: string) => void;
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
  receiveChanges: (projectId: string, root: ExplorerRoot, changes: FileChange[]) => void;
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
  acknowledgeCadCommand: (kind: "selectReference" | "captureRequest", nonce: string | number) => void;
};

// A committed mutation is broadcast and also returned to its caller. Bound
// receipt deduplication so a delayed reply cannot apply the same rename twice.
const appliedMutations = new Set<string>();
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
    case "drawing":
      return { ...base, kind: "drawing", root: null, title: "Drawing", ...init } as DrawingTab;
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
let pendingSave: { projectId: string; tabs: PersistedExplorerTab[] } | null = null;
// Only scratch metadata is retained here; ordinary tabs still load from main.
const projectDrawings = new Map<string, { tabs: DrawingTab[]; activeId: string | null }>();
function rememberDrawings(projectId: string | null, tabs: ExplorerTab[], activeId: string | null): void {
  if (!projectId) return;
  const drawings = tabs.filter((tab): tab is DrawingTab => tab.kind === "drawing");
  if (drawings.length) projectDrawings.set(projectId, { tabs: drawings, activeId });
  else projectDrawings.delete(projectId);
}
function restoreDrawings(projectId: string, persisted: ExplorerTab[]): { tabs: ExplorerTab[]; activeId: string | null } {
  const snapshot = projectDrawings.get(projectId);
  // Even an old or compromised response must not resurrect a scratch tab.
  const tabs: ExplorerTab[] = persisted.filter(tab => tab.kind !== "drawing");
  for (const drawing of snapshot?.tabs ?? []) tabs.splice(Math.min(drawing.order, tabs.length), 0, drawing);
  return {
    tabs: tabs.map((tab, order) => ({ ...tab, order })),
    activeId: snapshot?.activeId && tabs.some(tab => tab.id === snapshot.activeId) ? snapshot.activeId : tabs[0]?.id ?? null,
  };
}
const savingProjects = new Map<string, Promise<void>>();
let bindingSequence = 0;
let cadCommandSequence = 0;

/** Flush the outgoing snapshot; another project's loading never waits for it. */
function flushTabSave(): void {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = null;
  const snapshot = pendingSave;
  pendingSave = null;
  if (!snapshot) return;
  const write = async () => { await window.hardcore.explorer.saveTabs(snapshot); };
  const previous = savingProjects.get(snapshot.projectId);
  const saving = (previous ? previous.then(write) : write()).catch(() => {
    // Persistence is a convenience; a failed write must not take the strip
    // down or prevent the next save/load for this project.
  });
  savingProjects.set(snapshot.projectId, saving);
  void saving.then(() => {
    if (savingProjects.get(snapshot.projectId) === saving) savingProjects.delete(snapshot.projectId);
  });
}

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
  const current = useExplorer.getState();
  const stillTargets = (command: ExplorerState["cadCapture"]) => command && command.projectId === projectId
    && command.tabId === unique.activeId && ordered.some(tab => tab.kind === "file"
      && tab.id === command.tabId && tab.path === command.path && tab.root === command.root);
  set({ tabs: ordered, activeId: unique.activeId,
    cadSelection: stillTargets(current.cadSelection) ? current.cadSelection : null,
    cadCapture: stillTargets(current.cadCapture) ? current.cadCapture : null });
  if (!projectId) {
    return;
  }
  if (saveTimer) {
    clearTimeout(saveTimer);
  }
  rememberDrawings(projectId, ordered, unique.activeId);
  pendingSave = { projectId, tabs: ordered.filter((tab): tab is PersistedExplorerTab => tab.kind !== "drawing")
    .map((tab, order) => ({ ...tab, order })) };
  saveTimer = setTimeout(flushTabSave, SAVE_DEBOUNCE_MS);
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
  changedEntries: [],
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
    // Keep the departing project's edits even when its debounce has not fired.
    if (get().ready) rememberDrawings(get().projectId, get().tabs, get().activeId);
    flushTabSave();
    const binding = ++bindingSequence;
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
      changedEntries: [],
      changedRoot: null,
      reveal: null,
      cadSelection: null,
      cadCapture: null,
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
    const loadTabs = async () => {
      const saving = savingProjects.get(projectId);
      if (saving) await saving;
      if (binding !== bindingSequence) return [] as ExplorerTab[];
      return window.hardcore.explorer.loadTabs({ projectId }).catch(() => [] as ExplorerTab[]);
    };
    const [tabs] = await Promise.all([
      loadTabs(),
      watch(projectId, root),
    ]);
    // A slower load for a project the user has already navigated away from
    // must not overwrite the one they are looking at.
    if (binding !== bindingSequence || get().projectId !== projectId) {
      return;
    }
    // A strip written by an older build may hold two tabs for one file.
    const merged = restoreDrawings(projectId, tabs);
    const restored = dedupeFileTabs(merged.tabs, merged.activeId);
    set({ tabs: restored.tabs, activeId: restored.activeId, ready: true });
  },

  discardProjectDrawings: (projectId) => {
    const snapshot = projectDrawings.get(projectId);
    const active = get().projectId === projectId;
    const drawings = [...(snapshot?.tabs ?? []), ...(active ? get().tabs.filter(tab => tab.kind === "drawing") : [])];
    for (const tab of drawings) deleteDrawingScene(tab.id);
    projectDrawings.delete(projectId);
    if (pendingSave?.projectId === projectId) {
      pendingSave = null;
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = null;
    }
    if (active) {
      const tabs = get().tabs.filter(tab => tab.kind !== "drawing").map((tab, order) => ({ ...tab, order }));
      set({ tabs, activeId: tabs.some(tab => tab.id === get().activeId) ? get().activeId : tabs[0]?.id ?? null });
    }
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
    // A partial strip cannot replace the pending persisted/temporary snapshot.
    // The tab menu is disabled until restore completes; shortcuts share this guard.
    if (!projectId || !get().ready) {
      return null;
    }
    // A tab nobody can see is not an open tab: every kind reveals the pane.
    get().show();
    // Files, drawings and terminals open in the active root unless told otherwise —
    // the worktree of the thread being talked to, or the project.
    const rooted: Record<string, unknown> =
      (kind === "file" || kind === "drawing")
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
    if (closing?.kind === "drawing") deleteDrawingScene(closing.id);
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

  setActive: (activeId) => set(state => ({ activeId,
    cadSelection: state.cadSelection?.tabId === activeId ? state.cadSelection : null,
    cadCapture: state.cadCapture?.tabId === activeId ? state.cadCapture : null })),

  selectIndex: (index) => {
    const tab = get().tabs[index - 1];
    if (tab) {
      get().setActive(tab.id);
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
    const { projectId, tabs, activeId, ready } = get();
    // Delayed tab callbacks cannot mutate a different or partially restored strip.
    if (!ready || !tabs.some(tab => tab.id === id)) return;
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
    const panelWidth = clampPanelWidth(width);
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

  selectCadReference: (tabId, selector) => set(state => {
    const tab = state.tabs.find(tab => tab.id === tabId);
    if (!state.projectId || state.activeId !== tabId || tab?.kind !== "file" || !tab.path) return state;
    return { cadSelection: { projectId: state.projectId, tabId, path: tab.path, root: tab.root, selector, nonce: ++cadCommandSequence } };
  }),

  captureCad: (tabId) => set(state => {
    const tab = state.tabs.find(tab => tab.id === tabId);
    if (!state.projectId || state.activeId !== tabId || tab?.kind !== "file" || !tab.path) return state;
    return { cadCapture: { projectId: state.projectId, tabId, path: tab.path, root: tab.root, nonce: ++cadCommandSequence } };
  }),

  acknowledgeCadCommand: (kind, nonce) => set(state => {
    if (kind === "selectReference") return state.cadSelection?.nonce === nonce ? { cadSelection: null } : state;
    return state.cadCapture?.nonce === nonce ? { cadCapture: null } : state;
  }),

  receiveChanges: (projectId, root, changes) => {
    if (get().projectId !== projectId) return;
    changes = changes.filter(change => {
      if (!change.mutationId) return true;
      const key = JSON.stringify([projectId, root, change.mutationId]);
      if (appliedMutations.has(key)) return false;
      appliedMutations.add(key);
      while (appliedMutations.size > 256) appliedMutations.delete(appliedMutations.values().next().value!);
      return true;
    });
    if (!changes.length) return;
    const paths = [...new Set(changes.flatMap(change => change.kind === "moved" ? [change.previousPath, change.path] : [change.path]))];
    // Publish identity changes before updating tab paths, so mounted documents
    // can carry an unsaved draft to the new name. Keep all cached descendants.
    set((state) => {
      const key = treeKey(root), tree = state.trees[key] ?? EMPTY_TREE;
      const next = reconcileFileTree(tree.listings, [...tree.open], changes.map(viewerFileChange));
      return { fsRevision: state.fsRevision + 1, changedPaths: paths, changedEntries: changes, changedRoot: root,
        trees: { ...state.trees, [key]: { open: new Set(next.expanded), listings: Object.fromEntries(Object.entries(next.listings).map(([directory, entries]) => [directory, [...entries]])) } } };
    });
    for (const change of changes) if (change.kind === "moved") {
      for (const tab of get().tabs) if (tab.kind === "file" && tab.root === root && tab.path !== null) {
        const moved = movedFilePath(tab.path, change.previousPath, change.path);
        if (moved !== tab.path) get().update(tab.id, { path: moved });
      }
    }
  },
}));

/** Inspect a scratch tab without selecting it or switching the active project. */
export function getDrawingTab(tabId: string, projectId: string): DrawingTab | null {
  const state = useExplorer.getState();
  const tab = (state.projectId === projectId ? state.tabs.find(tab => tab.id === tabId && tab.kind === "drawing") : null)
    ?? projectDrawings.get(projectId)?.tabs.find(tab => tab.id === tabId);
  return tab?.kind === "drawing" ? tab : null;
}

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
    case "drawing":
      return tab.title;
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
