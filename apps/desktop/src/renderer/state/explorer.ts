import { FILE_PANEL_TREE, PANEL_DEFAULT_WIDTH, clampPanelWidth } from "@hardcore/ui/navigation";
import { create } from "zustand";
import { toast } from "sonner";
import { hasDirtyDocument, releaseDocumentTab, discardDocumentTab } from "./live-documents";
import { releaseCadTab } from "./live-cad";
import { forgetViewState } from "@renderer/features/explorer/adapters/viewStateStore";

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
 * Every session owns its own strip and pane state. Directory/root identity is
 * only for filesystem access, never for deciding which agent owns a tab.
 * Inactive strips remain in memory (including ephemeral drawings and drafts).
 * Agent commands mutate their owner's strip without selecting another session.
 */

/** How long a burst of changes is collected before it reaches sqlite. */
const SAVE_DEBOUNCE_MS = 400;

/**
 * The file tab's panel column, in pixels — one width for every panel that
 * can be in it (the tree or a viewer file's panels), because
 * it is one column. A preference, not a per-tab property; WHICH panel is
 * open is per tab (`FileTabSchema.panel`).
 */
const PANEL_WIDTH_KEY = "hardcore.explorer.panelWidth";
/** Whether the pane itself is closed, per session id (see `collapsed`). */
const PANE_COLLAPSED_KEY = "hardcore.explorer.session.collapsed";
/** How wide it is when it is open, per session id (see `width`). */
const PANE_WIDTH_KEY = "hardcore.explorer.session.width";
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

/** One of the per-session maps in localStorage, parsed defensively. */
function bySession<T>(key: string): Record<string, T> {
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
 * remembered for the session they made it in.
 *
 * Per session rather than per app, because whether the right-hand pane earns
 * its width is a fact about the work: a CAD project is looked at, a scratch
 * folder is talked to. Opening a file, a review, a browser or a terminal
 * shows the pane without writing anything — the preference is what the person
 * chose, not what an agent's tool call did.
 *
 * There is no entry for "no session": without one the explorer is not drawn
 * at all, so there is no choice to remember and nothing to remember it for.
 */
function collapsedFor(sessionId: string): boolean {
  return bySession<boolean>(PANE_COLLAPSED_KEY)[sessionId] ?? true;
}

/**
 * The pane's width for a session, in pixels. Its pair with `collapsed` is the
 * explorer's whole state: a collapse keeps the width, so the toggle brings
 * the pane back the size it was rather than at its floor.
 */
function widthFor(sessionId: string): number {
  const stored = bySession<number>(PANE_WIDTH_KEY)[sessionId];
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
  review: Partial<Pick<ReviewTab, "scope">>;
  browser: Partial<Pick<BrowserTab, "url" | "root">>;
  terminal: Partial<Pick<TerminalTab, "cwd" | "readOnly" | "ptyId">>;
  drawing: Partial<Pick<DrawingTab, "root" | "title">>;
};

type ExplorerState = {
  sessionId: string | null;
  /** The session’s directory identity for filesystem operations. */
  projectId: string | null;
  /**
   * Where new tabs open and what the tree lists: null for the session
   * directory, else the active session's worktree (see the note above).
   */
  root: ExplorerRoot;
  tabs: ExplorerTab[];
  activeId: string | null;
  /** True once the strip has been loaded for `sessionId`. */
  ready: boolean;
  loadError: string | null;
  /**
   * The pane's own state: closed until something opens it, and remembered for
   * the session once the person says otherwise. The session column fills the
   * window while it is closed, and with no session bound the pane is not
   * rendered at all (`Shell`).
   */
  collapsed: boolean;
  /**
   * How wide the pane is when it is open, in pixels — the other half of the
   * pair. A drag writes it, a collapse keeps it, and the toggle brings the
   * pane back at it. Per session, like `collapsed`.
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
   * Transient — cleared when a file is opened or the session changes.
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
  /** An annotation the chat box asked a CAD tab to open (its entry there was pressed). Nonce-keyed like `cadSelection`. */
  cadAnnotation: { projectId: string; tabId: string; path: string; root: ExplorerRoot; id: string; nonce: number } | null;

  bindSession: (sessionId: string | null, projectId: string | null, root?: ExplorerRoot) => Promise<void>;
  /**
   * Change the root new tabs open in. The tree state of the root being
   * left is kept, so coming back to a thread finds its folders still open.
   */
  setRoot: (root: ExplorerRoot) => void;
  /** Release retained resources when their session is archived or deleted. */
  discardSessionResources: (sessionId: string, options?: { preserveTabs?: boolean }) => void;
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
  /** A person's choice, remembered for the session they made it in. */
  setCollapsed: (collapsed: boolean) => void;
  toggleCollapsed: () => void;
  /** A drag's result, remembered for the session it was made in. */
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
  /** Ask a CAD tab to open one of its annotations and select its geometry. */
  openCadAnnotation: (tabId: string, id: string) => void;
  acknowledgeCadCommand: (kind: "selectReference" | "captureRequest" | "openAnnotation", nonce: string | number) => void;
};

// A committed mutation is broadcast and also returned to its caller. Bound
// receipt deduplication so a delayed reply cannot apply the same rename twice.
const appliedMutations = new Set<string>();
let sequence = 0;
const nextId = () => `tab-${Date.now().toString(36)}-${++sequence}`;

function blankTab(
  kind: ExplorerTabKind,
  projectId: string,
  sessionId: string,
  order: number,
  init: Record<string, unknown> = {},
): ExplorerTab {
  const base = { id: nextId(), projectId, sessionId, order };
  switch (kind) {
    case "file":
      return { ...base, kind: "file", path: null, root: null, panel: null, ...init } as FileTab;
    case "review":
      return { ...base, kind: "review", scope: "all" as const, ...init };
    case "browser":
      return { ...base, kind: "browser", url: null, root: null, ...init } as BrowserTab;
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

type Strip = { collapsed?: boolean; width?: number; tabs: ExplorerTab[]; activeId: string | null; trees?: ExplorerState["trees"]; reveal?: ExplorerState["reveal"] };
const retainedStrips = new Map<string, Strip>();
const archivedDocumentTabs = new Map<string, ExplorerTab[]>();
const tabSubscribers = new Set<(tabs: readonly ExplorerTab[]) => void>();
function notifySessionTabs(): void {
  const tabs = [...new Map([...retainedStrips.values()].flatMap(strip => strip.tabs).map(tab => [tab.id, tab])).values()];
  for (const listener of tabSubscribers) listener(tabs);
}
/** Resource caches follow every retained session, independent of the selected pane. */
export function subscribeSessionTabs(listener: (tabs: readonly ExplorerTab[]) => void): () => void {
  tabSubscribers.add(listener); notifySessionTabs();
  return () => { tabSubscribers.delete(listener); };
}
const loadingStrips = new Map<string, Promise<Strip>>();
const discardedSessions = new Set<string>();
const sessionGenerations = new Map<string, number>();
const saveTimers = new Map<string, ReturnType<typeof setTimeout>>();
const pendingSaves = new Map<string, PersistedExplorerTab[]>();
const savingSessions = new Map<string, Promise<void>>();
let bindingSequence = 0;
let cadCommandSequence = 0;

/** Serialize writes for each session; another session never blocks on them. */
function flushTabSave(sessionId: string): void {
  clearTimeout(saveTimers.get(sessionId));
  saveTimers.delete(sessionId);
  const tabs = pendingSaves.get(sessionId);
  pendingSaves.delete(sessionId);
  if (!tabs || discardedSessions.has(sessionId)) return;
  const write = async () => {
    if (!discardedSessions.has(sessionId)) await window.hardcore.explorer.saveTabs({ sessionId, tabs });
  };
  const saving = (savingSessions.get(sessionId) ?? Promise.resolve()).then(write).catch(() => {});
  savingSessions.set(sessionId, saving);
  void saving.then(() => { if (savingSessions.get(sessionId) === saving) savingSessions.delete(sessionId); });
}

function saveStrip(sessionId: string, strip: Strip): void {
  retainedStrips.set(sessionId, strip);
  notifySessionTabs();
  pendingSaves.set(sessionId, strip.tabs.filter((tab): tab is PersistedExplorerTab => tab.kind !== "drawing")
    .map((tab, order) => ({ ...tab, order })));
  clearTimeout(saveTimers.get(sessionId));
  saveTimers.set(sessionId, setTimeout(() => flushTabSave(sessionId), SAVE_DEBOUNCE_MS));
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
  sessionId: string | null,
  tabs: ExplorerTab[],
  activeId: string | null,
) {
  const unique = dedupeFileTabs(tabs, activeId);
  const ordered = unique.tabs.map((tab, order) => ({ ...tab, order }) as ExplorerTab);
  const current = useExplorer.getState();
  const stillTargets = (command: ExplorerState["cadCapture"]) => command && command.projectId === current.projectId
    && command.tabId === unique.activeId && ordered.some(tab => tab.kind === "file"
      && tab.id === command.tabId && tab.path === command.path && tab.root === command.root);
  set({ tabs: ordered, activeId: unique.activeId,
    cadSelection: stillTargets(current.cadSelection) ? current.cadSelection : null,
    cadCapture: stillTargets(current.cadCapture) ? current.cadCapture : null,
    cadAnnotation: stillTargets(current.cadAnnotation) ? current.cadAnnotation : null });
  if (sessionId) saveStrip(sessionId, { tabs: ordered, activeId: unique.activeId,
    trees: current.trees, reveal: current.reveal, collapsed: current.collapsed, width: current.width });
}

/** The watcher for one root, started and stopped with the binding. */
function watch(projectId: string, root: ExplorerRoot): Promise<void> {
  return window.hardcore.explorer.watch({ projectId, ...(root ? { root } : {}) }).catch(() => undefined);
}

function unwatch(projectId: string, root: ExplorerRoot): void {
  void window.hardcore.explorer.unwatch({ projectId, ...(root ? { root } : {}) }).catch(() => {});
}

export const useExplorer = create<ExplorerState>((set, get) => ({
  sessionId: null,
  projectId: null,
  root: null,
  tabs: [],
  activeId: null,
  ready: false,
  loadError: null,
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
  cadAnnotation: null,

  bindSession: async (sessionId, projectId, root = null) => {
    if (get().sessionId === sessionId && get().ready) {
      if (get().root !== root) get().setRoot(root);
      return;
    }
    const previous = get();
    if (previous.sessionId && previous.ready) {
      retainedStrips.set(previous.sessionId, { tabs: previous.tabs, activeId: previous.activeId,
        trees: previous.trees, reveal: previous.reveal, collapsed: previous.collapsed, width: previous.width });
      flushTabSave(previous.sessionId);
    }
    const binding = ++bindingSequence;
    if (previous.projectId) unwatch(previous.projectId, previous.root);
    set({ sessionId, projectId: sessionId ? projectId : null, root, tabs: [], activeId: null, ready: false, loadError: null,
      changedPaths: [], changedEntries: [], changedRoot: null, reveal: null, cadSelection: null, cadCapture: null, cadAnnotation: null,
      collapsed: sessionId ? collapsedFor(sessionId) : true,
      width: sessionId ? widthFor(sessionId) : PANE_LIMITS.explorer.default, trees: {} });
    if (!sessionId || !projectId) { set({ ready: true }); return; }
    discardedSessions.delete(sessionId);
    void window.hardcore.cad.warm({ projectId, ...(root ? { root } : {}) }).catch(() => {});
    try {
      const [strip] = await Promise.all([readSessionStrip(sessionId), watch(projectId, root)]);
      if (binding !== bindingSequence || get().sessionId !== sessionId) return;
      // A background command can update the retained strip while watch startup
      // is pending. Publish its latest state, never the earlier read snapshot.
      const latest = currentStrip(sessionId) ?? strip;
      const restored = dedupeFileTabs(latest.tabs, latest.activeId);
      set({ ...restored, trees: latest.trees ?? {}, reveal: latest.reveal ?? null,
        collapsed: latest.collapsed ?? collapsedFor(sessionId), width: latest.width ?? widthFor(sessionId), ready: true });
    } catch (error) {
      if (binding !== bindingSequence || get().sessionId !== sessionId) return;
      // Failed reads must never masquerade as an empty strip and overwrite saved tabs.
      set({ loadError: error instanceof Error ? error.message : String(error), ready: false, collapsed: false });
    }
  },

  discardSessionResources: (sessionId, options) => {
    if (options?.preserveTabs) void flushSessionTabs(sessionId).catch(error => console.error("[explorer] final save failed", error));
    discardedSessions.add(sessionId);
    sessionGenerations.set(sessionId, (sessionGenerations.get(sessionId) ?? 0) + 1);
    const active = get().sessionId === sessionId;
    const tabs = new Map([...(archivedDocumentTabs.get(sessionId) ?? []), ...(retainedStrips.get(sessionId)?.tabs ?? []), ...(active ? get().tabs : [])].map(tab => [tab.id, tab]));
    if (options?.preserveTabs) archivedDocumentTabs.set(sessionId, [...tabs.values()].filter(tab => tab.kind === "file"));
    else archivedDocumentTabs.delete(sessionId);
    for (const tab of tabs.values()) disposeTab(tab, true, options?.preserveTabs);
    pendingSaves.delete(sessionId);
    clearTimeout(saveTimers.get(sessionId)); saveTimers.delete(sessionId);
    retainedStrips.delete(sessionId); loadingStrips.delete(sessionId); notifySessionTabs();
    if (active) { if (get().projectId) unwatch(get().projectId!, get().root); ++bindingSequence; set({ sessionId: null, projectId: null, tabs: [], activeId: null, ready: true }); }
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
    const { projectId, sessionId, root, tabs } = get();
    // A partial strip cannot replace the pending persisted/temporary snapshot.
    // The tab menu is disabled until restore completes; shortcuts share this guard.
    if (!projectId || !sessionId || !get().ready) {
      return null;
    }
    // A tab nobody can see is not an open tab: every kind reveals the pane.
    get().show();
    // Files, drawings and terminals open in the active root unless told otherwise —
    // the worktree of the thread being talked to, or the project.
    const rooted: Record<string, unknown> =
      (kind === "file" || kind === "drawing" || kind === "browser")
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
    const tab = blankTab(kind, projectId, sessionId, tabs.length, rooted);
    commit(set, get().sessionId, [...tabs, tab], tab.id);
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
      commit(set, get().sessionId, next, blank.id);
      return next.find((tab) => tab.id === blank.id) ?? null;
    }
    return get().open("file", { path: filePath, root: target });
  },

  close: (id) => {
    const { sessionId, tabs, activeId } = get();
    const index = tabs.findIndex((tab) => tab.id === id);
    if (index < 0) {
      return;
    }
    const closing = tabs[index];
    if (hasDirtyDocument(id)) {
      toast.error("This file has unsaved changes.", { description: "Save it before closing, or discard your edits.",
        action: { label: "Discard and close", onClick: () => {
          // A toast can outlive a session switch. Do not close a different strip.
          if (get().sessionId !== sessionId) return;
          discardDocumentTab(id); get().close(id);
        } } });
      return;
    }
    if (closing) disposeTab(closing);
    const remaining = tabs.filter((tab) => tab.id !== id);
    const nextActive =
      activeId === id ? (remaining[Math.min(index, remaining.length - 1)]?.id ?? null) : activeId;
    commit(set, get().sessionId, remaining, nextActive);
  },

  closeActive: () => {
    const { activeId } = get();
    if (activeId) {
      get().close(activeId);
    }
  },

  setActive: (activeId) => set(state => ({ activeId,
    cadSelection: state.cadSelection?.tabId === activeId ? state.cadSelection : null,
    cadCapture: state.cadCapture?.tabId === activeId ? state.cadCapture : null,
    cadAnnotation: state.cadAnnotation?.tabId === activeId ? state.cadAnnotation : null })),

  selectIndex: (index) => {
    const tab = get().tabs[index - 1];
    if (tab) {
      get().setActive(tab.id);
    }
  },

  move: (id, toIndex) => {
    const { tabs, activeId } = get();
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
    commit(set, get().sessionId, next, activeId);
  },

  update: (id, patch) => {
    const { tabs, activeId, ready } = get();
    // Delayed tab callbacks cannot mutate a different or partially restored strip.
    if (!ready || !tabs.some(tab => tab.id === id)) return;
    const next = tabs.map((tab) => (tab.id === id ? ({ ...tab, ...patch, id: tab.id, sessionId: tab.sessionId, projectId: tab.projectId, kind: tab.kind } as ExplorerTab) : tab));
    commit(set, get().sessionId, next, activeId);
  },

  setCollapsed: (collapsed) => {
    const { sessionId } = get();
    // No session, no explorer: there is nothing for a preference to be about.
    if (!sessionId) {
      return;
    }
    writeLocal(PANE_COLLAPSED_KEY, JSON.stringify({ ...bySession<boolean>(PANE_COLLAPSED_KEY), [sessionId]: collapsed }));
    set({ collapsed });
  },

  toggleCollapsed: () => get().setCollapsed(!get().collapsed),

  setWidth: (width) => {
    const { sessionId } = get();
    const rounded = Math.round(width);
    if (!sessionId || rounded <= 0) {
      return;
    }
    writeLocal(PANE_WIDTH_KEY, JSON.stringify({ ...bySession<number>(PANE_WIDTH_KEY), [sessionId]: rounded }));
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

  openCadAnnotation: (tabId, id) => set(state => {
    const tab = state.tabs.find(tab => tab.id === tabId);
    if (!state.projectId || state.activeId !== tabId || tab?.kind !== "file" || !tab.path) return state;
    return { cadAnnotation: { projectId: state.projectId, tabId, path: tab.path, root: tab.root, id, nonce: ++cadCommandSequence } };
  }),

  acknowledgeCadCommand: (kind, nonce) => set(state => {
    if (kind === "selectReference") return state.cadSelection?.nonce === nonce ? { cadSelection: null } : state;
    if (kind === "openAnnotation") return state.cadAnnotation?.nonce === nonce ? { cadAnnotation: null } : state;
    return state.cadCapture?.nonce === nonce ? { cadCapture: null } : state;
  }),

  receiveChanges: (projectId, root, changes) => {
    changes = changes.filter(change => {
      if (!change.mutationId) return true;
      const key = JSON.stringify([projectId, root, change.mutationId]);
      if (appliedMutations.has(key)) return false;
      appliedMutations.add(key);
      while (appliedMutations.size > 256) appliedMutations.delete(appliedMutations.values().next().value!);
      return true;
    });
    if (!changes.length) return;
    for (const [sessionId, strip] of retainedStrips) {
      if (sessionId === get().sessionId || !strip.tabs.some(tab => tab.projectId === projectId)) continue;
      let changed = false;
      const tabs = strip.tabs.map(tab => {
        if (tab.kind !== "file" || tab.root !== root || !tab.path) return tab;
        let path = tab.path;
        for (const change of changes) if (change.kind === "moved") path = movedFilePath(path, change.previousPath, change.path);
        changed ||= path !== tab.path;
        return path === tab.path ? tab : { ...tab, path };
      });
      const next = { ...strip, tabs, trees: {} };
      if (changed) saveStrip(sessionId, next); else retainedStrips.set(sessionId, next);
    }
    if (get().projectId !== projectId) return;
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

/** Read only the specified session's scratch tab. */
export function getDrawingTab(tabId: string, sessionId: string): DrawingTab | null {
  const tab = currentStrip(sessionId)?.tabs.find(tab => tab.id === tabId && tab.kind === "drawing");
  return tab?.kind === "drawing" ? tab : null;
}

/** Rename only within the owning session, including an inactive sketch. */
export function renameDrawingTab(tabId: string, sessionId: string, title: string): void {
  const name = title.trim();
  if (!name || name.length > 200) throw new Error("Use a drawing name between 1 and 200 characters.");
  const strip = currentStrip(sessionId);
  if (!strip?.tabs.some(tab => tab.id === tabId && tab.kind === "drawing")) throw new Error("This drawing is closed.");
  updateSessionStrip(sessionId, { ...strip, tabs: strip.tabs.map(tab => tab.id === tabId ? { ...tab, title: name } : tab) });
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


/** Retained state belongs to sessions, not their directory grouping. */
useExplorer.subscribe(state => {
  if (state.sessionId && state.ready) retainedStrips.set(state.sessionId, {
    tabs: state.tabs, activeId: state.activeId, trees: state.trees, reveal: state.reveal, collapsed: state.collapsed, width: state.width,
  });
  notifySessionTabs();
});
function currentStrip(sessionId: string): Strip | undefined {
  const state = useExplorer.getState();
  return state.sessionId === sessionId && state.ready ? state : retainedStrips.get(sessionId);
}
export async function readSessionStrip(sessionId: string): Promise<Strip> {
  const retained = currentStrip(sessionId);
  if (retained) return retained;
  if (discardedSessions.has(sessionId)) throw new Error("This session is no longer active.");
  let pending = loadingStrips.get(sessionId);
  if (!pending) {
    const generation = sessionGenerations.get(sessionId) ?? 0;
    pending = (async () => {
      await savingSessions.get(sessionId);
      const persisted = await window.hardcore.explorer.loadTabs({ sessionId });
      if (discardedSessions.has(sessionId) || (sessionGenerations.get(sessionId) ?? 0) !== generation) throw new Error("This session is no longer active.");
      const tabs = (persisted as ExplorerTab[]).filter(tab => tab.sessionId === sessionId && tab.kind !== "drawing");
      const strip = currentStrip(sessionId) ?? { tabs, activeId: tabs[0]?.id ?? null };
      retainedStrips.set(sessionId, strip);
      notifySessionTabs();
      return strip;
    })();
    loadingStrips.set(sessionId, pending);
    void pending.finally(() => { if (loadingStrips.get(sessionId) === pending) loadingStrips.delete(sessionId); }).catch(() => {});
  }
  return pending;
}

function updateSessionStrip(sessionId: string, strip: Strip): void {
  if (discardedSessions.has(sessionId)) throw new Error("This session is no longer active.");
  const unique = dedupeFileTabs(strip.tabs, strip.activeId);
  const next = { ...strip, tabs: unique.tabs.map((tab, order) => ({ ...tab, order })), activeId: unique.activeId };
  const active = useExplorer.getState().sessionId === sessionId && useExplorer.getState().ready;
  if (active) useExplorer.setState({ ...next, cadSelection: null, cadCapture: null, cadAnnotation: null });
  saveStrip(sessionId, next);
}

function disposeTab(tab: ExplorerTab, discard = false, preserveDocuments = false): void {
  if (!preserveDocuments) {
    if (discard) discardDocumentTab(tab.id); else releaseDocumentTab(tab.id);
  }
  releaseCadTab(tab.id);
  // A file tab that is gone for good takes its stored view state with it; one retained for a
  // later restore keeps it.
  if (tab.kind === "file" && !preserveDocuments) forgetViewState(tab.id);
  if (tab.kind === "drawing") deleteDrawingScene(tab.id);
  if (tab.kind === "terminal" && tab.ptyId) void window.hardcore.terminal.kill({ id: tab.ptyId }).catch(() => {});
  if (tab.kind === "browser") void window.hardcore.browser.close({ sessionId: tab.sessionId, projectId: tab.projectId, root: tab.root, tabId: tab.id }).catch(() => {});
}

export async function openSessionTab<K extends ExplorerTabKind>(sessionId: string, projectId: string, root: ExplorerRoot, kind: K, init?: TabInit[K], signal?: AbortSignal): Promise<ExplorerTab> {
  await readSessionStrip(sessionId);
  signal?.throwIfAborted();
  const strip = currentStrip(sessionId)!;
  const rooted = { ...((kind === "file" || kind === "drawing" || kind === "browser") ? { root } : kind === "terminal" ? { cwd: root } : {}), ...init };
  const path = kind === "file" ? (init as TabInit["file"])?.path : null;
  // A panel asked for is the panel the file shows, in whichever tab shows it; none asked for
  // leaves a tab already showing the file as it is.
  const panel = kind === "file" ? (init as TabInit["file"])?.panel : undefined;
  const existing = path ? strip.tabs.find(tab => tab.kind === "file" && tab.path === path && tab.root === root) : null;
  const blank = path ? strip.tabs.find(tab => tab.kind === "file" && !tab.path) : null;
  const tab = existing ? (panel === undefined ? existing : { ...existing, panel } as FileTab)
    : blank ? { ...blank, path, root, panel: panel ?? null } as FileTab : blankTab(kind, projectId, sessionId, strip.tabs.length, rooted);
  const tabs = existing || blank ? strip.tabs.map(item => item.id === tab.id ? tab : item) : [...strip.tabs, tab];
  updateSessionStrip(sessionId, { ...strip, tabs, activeId: tab.id, reveal: null, collapsed: false });
  return tab;
}

function assertSameTabResource(tab: ExplorerTab, expected?: ExplorerTab): void {
  if (!expected) return;
  if (tab.sessionId !== expected.sessionId || tab.kind !== expected.kind
    || ("root" in tab && "root" in expected && tab.root !== expected.root)
    || (tab.kind === "file" && expected.kind === "file" && tab.path !== expected.path)
    || (tab.kind === "terminal" && expected.kind === "terminal" && tab.ptyId !== expected.ptyId)) {
    throw new Error("This tab closed or changed before the command was applied.");
  }
}

export async function selectSessionTab(sessionId: string, tabId: string, signal?: AbortSignal, expected?: ExplorerTab): Promise<void> {
  await readSessionStrip(sessionId);
  signal?.throwIfAborted();
  const strip = currentStrip(sessionId)!;
  const tab = strip.tabs.find(tab => tab.id === tabId);
  if (!tab) throw new Error("This tab is closed.");
  assertSameTabResource(tab, expected);
  updateSessionStrip(sessionId, { ...strip, activeId: tabId, collapsed: false });
}
export async function closeSessionTab(sessionId: string, tabId: string, signal?: AbortSignal, expected?: ExplorerTab): Promise<void> {
  await readSessionStrip(sessionId);
  signal?.throwIfAborted();
  const strip = currentStrip(sessionId)!;
  const tab = strip.tabs.find(tab => tab.id === tabId);
  if (!tab) throw new Error("This tab is closed.");
  assertSameTabResource(tab, expected);
  if (hasDirtyDocument(tabId)) throw new Error("Save or explicitly discard the document before closing its tab.");
  disposeTab(tab);
  const tabs = strip.tabs.filter(tab => tab.id !== tabId);
  updateSessionStrip(sessionId, { ...strip, tabs, activeId: strip.activeId === tabId ? tabs[0]?.id ?? null : strip.activeId });
}
export async function revealSessionPath(sessionId: string, projectId: string, root: ExplorerRoot, path: string, directory: boolean, signal?: AbortSignal): Promise<void> {
  await readSessionStrip(sessionId);
  signal?.throwIfAborted();
  const existing = currentStrip(sessionId)!.tabs.find(tab => tab.kind === "file" && tab.root === root);
  const tab = existing ?? await openSessionTab(sessionId, projectId, root, "file", { panel: FILE_PANEL_TREE }, signal);
  const strip = currentStrip(sessionId)!;
  updateSessionStrip(sessionId, { ...strip, tabs: strip.tabs.map(item => item.id === tab.id ? { ...item, panel: FILE_PANEL_TREE } as FileTab : item), activeId: tab.id, collapsed: false, reveal: { root, path, directory } });
}

/** A delayed native callback updates only the tab that requested it. */
export async function updateSessionTab(sessionId: string, tabId: string, patch: Partial<ExplorerTab>, signal?: AbortSignal): Promise<void> {
  await readSessionStrip(sessionId);
  signal?.throwIfAborted();
  const strip = currentStrip(sessionId)!;
  if (!strip.tabs.some(tab => tab.id === tabId)) throw new Error("This tab is closed.");
  updateSessionStrip(sessionId, { ...strip, tabs: strip.tabs.map(tab => tab.id === tabId
    ? { ...tab, ...patch, id: tab.id, sessionId: tab.sessionId, projectId: tab.projectId, kind: tab.kind } as ExplorerTab : tab) });
}

/** Archive waits for the latest ordinary tab metadata before releasing live resources. */
export function flushSessionTabs(sessionId: string): Promise<void> {
  const strip = currentStrip(sessionId);
  const tabs = strip?.tabs.filter((tab): tab is PersistedExplorerTab => tab.kind !== "drawing").map((tab, order) => ({ ...tab, order }))
    ?? pendingSaves.get(sessionId);
  clearTimeout(saveTimers.get(sessionId)); saveTimers.delete(sessionId); pendingSaves.delete(sessionId);
  if (!tabs) return savingSessions.get(sessionId) ?? Promise.resolve();
  const saving = (savingSessions.get(sessionId) ?? Promise.resolve()).then(() => window.hardcore.explorer.saveTabs({ sessionId, tabs }));
  const settled = saving.catch(() => {});
  savingSessions.set(sessionId, settled);
  void settled.then(() => { if (savingSessions.get(sessionId) === settled) savingSessions.delete(sessionId); });
  return saving;
}
