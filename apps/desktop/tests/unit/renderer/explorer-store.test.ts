import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { dedupeFileTabs, getDrawingTab, tabTitle, useExplorer } from "@renderer/state/explorer";
import { deleteDrawingScene } from "@renderer/state/drawings";

vi.mock("@renderer/state/drawings", () => ({ deleteDrawingScene: vi.fn() }));

import { PersistedExplorerTabSchema } from "@shared/types";
import type { PersistedExplorerTab } from "@shared/types";

/**
 * The strip's behaviour, without React.
 *
 * Everything here goes through `commit` in the store, which is also what
 * renumbers `order` and schedules the write to `explorer_tabs`. Testing the
 * store rather than the component is what makes "closing the active tab
 * selects its neighbour" a fact about the app rather than a fact about one
 * rendering of it.
 */
const PROJECT = "project-1";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function reset() {
  useExplorer.getState().discardProjectResources(PROJECT);
  useExplorer.getState().discardProjectResources("project-2");
  window.localStorage.clear();
  useExplorer.setState({
    projectId: PROJECT,
    root: null,
    tabs: [],
    activeId: null,
    ready: true,
    collapsed: true,
    fsRevision: 0,
    changedPaths: [],
  });
}

describe("the explorer strip", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    vi.mocked(window.hardcore.explorer.saveTabs).mockReset().mockResolvedValue(undefined);
    vi.mocked(window.hardcore.explorer.loadTabs).mockReset().mockResolvedValue([]);
    reset();
  });

  afterEach(async () => {
    await useExplorer.getState().bindProject(null);
    await vi.runOnlyPendingTimersAsync();
    vi.useRealTimers();
  });

  it("opens each of the five kinds into one strip", () => {
    const { open } = useExplorer.getState();
    for (const kind of ["file", "review", "browser", "terminal", "drawing"] as const) {
      open(kind);
    }
    expect(useExplorer.getState().tabs.map((tab) => tab.kind)).toEqual([
      "file",
      "review",
      "browser",
      "terminal",
      "drawing",
    ]);
  });

  it("retains drawings and their mixed order across project switches without saving them", async () => {
    const saved = new Map<string, PersistedExplorerTab[]>();
    vi.mocked(window.hardcore.explorer.saveTabs).mockImplementation(async ({ projectId, tabs }) => {
      saved.set(projectId, tabs.map((tab, order) => ({ ...tab, order }) as PersistedExplorerTab));
    });
    vi.mocked(window.hardcore.explorer.loadTabs).mockImplementation(async ({ projectId }) => saved.get(projectId) ?? []);
    const file = useExplorer.getState().open("file")!;
    const drawing = useExplorer.getState().open("drawing", { root: "/worktree", title: "Bracket sketch" })!;
    const review = useExplorer.getState().open("review")!;
    const secondDrawing = useExplorer.getState().open("drawing")!;
    useExplorer.getState().move(secondDrawing.id, 0);
    useExplorer.getState().setActive(drawing.id);
    await useExplorer.getState().bindProject("project-2");
    expect(getDrawingTab(drawing.id, PROJECT)).toMatchObject({ root: "/worktree", title: "Bracket sketch" });
    expect(saved.get(PROJECT)?.map(tab => tab.kind)).toEqual(["file", "review"]);
    expect(JSON.stringify(vi.mocked(window.hardcore.explorer.saveTabs).mock.calls)).not.toContain("Bracket sketch");
    await useExplorer.getState().bindProject(PROJECT);
    expect(useExplorer.getState().tabs.map(tab => tab.id)).toEqual([secondDrawing.id, file.id, drawing.id, review.id]);
    expect(useExplorer.getState().activeId).toBe(drawing.id);
    expect(useExplorer.getState().tabs.map(tab => tab.order)).toEqual([0, 1, 2, 3]);
    expect(tabTitle(getDrawingTab(drawing.id, PROJECT)!)).toBe("Bracket sketch");
    expect(deleteDrawingScene).not.toHaveBeenCalledWith(drawing.id);
  });

  it("retains both projects' drawings when navigating away from an unfinished restore", async () => {
    const stored = new Map<string, PersistedExplorerTab[]>();
    vi.mocked(window.hardcore.explorer.saveTabs).mockImplementation(async ({ projectId, tabs }) => {
      stored.set(projectId, tabs.map(tab => PersistedExplorerTabSchema.parse(tab)));
    });
    vi.mocked(window.hardcore.explorer.loadTabs).mockImplementation(async ({ projectId }) => stored.get(projectId) ?? []);
    const drawingA = useExplorer.getState().open("drawing", { title: "Drawing A" })!;
    await useExplorer.getState().bindProject("project-2");
    const fileB = useExplorer.getState().open("file")!;
    const drawingB = useExplorer.getState().open("drawing", { title: "Drawing B" })!;
    await useExplorer.getState().bindProject(PROJECT);
    expect(useExplorer.getState().activeId).toBe(drawingA.id);

    const lateRestore = deferred<PersistedExplorerTab[]>();
    vi.mocked(window.hardcore.explorer.loadTabs).mockImplementationOnce(() => lateRestore.promise);
    const unfinishedVisit = useExplorer.getState().bindProject("project-2");
    expect(useExplorer.getState()).toMatchObject({ projectId: "project-2", ready: false, tabs: [] });
    expect(getDrawingTab(drawingB.id, "project-2")).toMatchObject({ title: "Drawing B" });
    await useExplorer.getState().bindProject(PROJECT);
    expect(useExplorer.getState().activeId).toBe(drawingA.id);
    lateRestore.resolve([]);
    await unfinishedVisit;
    expect(useExplorer.getState().activeId).toBe(drawingA.id);

    await useExplorer.getState().bindProject("project-2");
    expect(useExplorer.getState().tabs.map(tab => tab.id)).toEqual([fileB.id, drawingB.id]);
    expect(useExplorer.getState().activeId).toBe(drawingB.id);
    expect(getDrawingTab(drawingA.id, PROJECT)).toMatchObject({ title: "Drawing A" });
    expect(deleteDrawingScene).not.toHaveBeenCalledWith(drawingA.id);
    expect(deleteDrawingScene).not.toHaveBeenCalledWith(drawingB.id);
  });

  it("ignores open requests during restoration without replacing retained drawings", async () => {
    const stored = new Map<string, PersistedExplorerTab[]>();
    vi.mocked(window.hardcore.explorer.saveTabs).mockImplementation(async ({ projectId, tabs }) => {
      stored.set(projectId, tabs.map(tab => PersistedExplorerTabSchema.parse(tab)));
    });
    vi.mocked(window.hardcore.explorer.loadTabs).mockImplementation(async ({ projectId }) => stored.get(projectId) ?? []);
    const file = useExplorer.getState().open("file")!;
    const drawing = useExplorer.getState().open("drawing", { title: "Keep this sketch" })!;
    await useExplorer.getState().bindProject("project-2");
    const loading = deferred<PersistedExplorerTab[]>();
    vi.mocked(window.hardcore.explorer.loadTabs).mockImplementationOnce(() => loading.promise);
    const restoring = useExplorer.getState().bindProject(PROJECT);
    expect(useExplorer.getState().ready).toBe(false);
    vi.mocked(window.hardcore.explorer.saveTabs).mockClear();
    for (const kind of ["file", "review", "browser", "terminal", "drawing"] as const) {
      expect(useExplorer.getState().open(kind)).toBeNull();
    }
    expect(useExplorer.getState().openFile("unexpected.txt")).toBeNull();
    expect(useExplorer.getState().tabs).toEqual([]);
    expect(getDrawingTab(drawing.id, PROJECT)).toMatchObject({ title: "Keep this sketch" });
    expect(window.hardcore.explorer.saveTabs).not.toHaveBeenCalled();
    loading.resolve(stored.get(PROJECT) ?? []);
    await restoring;
    expect(useExplorer.getState().tabs.map(tab => tab.id)).toEqual([file.id, drawing.id]);
    const accepted = useExplorer.getState().open("drawing");
    expect(accepted?.kind).toBe("drawing");
    expect(useExplorer.getState().tabs).toHaveLength(3);
  });

  it("ignores late updates from a departed tab while another strip is restoring", async () => {
    const drawing = useExplorer.getState().open("drawing")!;
    await useExplorer.getState().bindProject("project-2");
    const loading = deferred<PersistedExplorerTab[]>();
    vi.mocked(window.hardcore.explorer.loadTabs).mockImplementationOnce(() => loading.promise);
    const restoring = useExplorer.getState().bindProject(PROJECT);
    vi.mocked(window.hardcore.explorer.saveTabs).mockClear();
    useExplorer.getState().update("departed-terminal", { ptyId: "late-pty" });
    expect(getDrawingTab(drawing.id, PROJECT)).not.toBeNull();
    expect(window.hardcore.explorer.saveTabs).not.toHaveBeenCalled();
    loading.resolve([]);
    await restoring;
    expect(useExplorer.getState().tabs.map(tab => tab.id)).toEqual([drawing.id]);
  });

  it("disposes closed drawings and cannot resurrect them from storage", async () => {
    const drawing = useExplorer.getState().open("drawing")!;
    expect(drawing).toMatchObject({ root: null, title: "Drawing" });
    useExplorer.getState().close(drawing.id);
    expect(deleteDrawingScene).toHaveBeenCalledWith(drawing.id);
    expect(getDrawingTab(drawing.id, PROJECT)).toBeNull();
    await useExplorer.getState().bindProject("project-2");
    // Simulate a response written by an older or compromised persistence path.
    vi.mocked(window.hardcore.explorer.loadTabs).mockResolvedValue([drawing as never]);
    await useExplorer.getState().bindProject(PROJECT);
    expect(useExplorer.getState().tabs).toEqual([]);
  });

  it("disposes drawings of a removed background project", async () => {
    const drawing = useExplorer.getState().open("drawing")!;
    await useExplorer.getState().bindProject("project-2");
    useExplorer.getState().discardProjectResources(PROJECT);
    expect(deleteDrawingScene).toHaveBeenCalledWith(drawing.id);
    expect(getDrawingTab(drawing.id, PROJECT)).toBeNull();
    await useExplorer.getState().bindProject(PROJECT);
    expect(useExplorer.getState().tabs).toEqual([]);
  });

  it("focuses a newly opened tab", () => {
    const tab = useExplorer.getState().open("file");
    expect(useExplorer.getState().activeId).toBe(tab?.id);
  });

  it("refuses to open a tab with no project", () => {
    useExplorer.setState({ projectId: null });
    expect(useExplorer.getState().open("file")).toBeNull();
    expect(useExplorer.getState().tabs).toHaveLength(0);
  });

  /**
   * No project, no explorer: `Shell` does not render the pane, so the toggle
   * is not drawn and the shortcut and the palette's command reach a store
   * with nowhere to file a preference. It must not write one under a
   * placeholder key that a real project would then never see.
   */
  it("has no explorer to toggle without a project", () => {
    useExplorer.setState({ projectId: null, collapsed: true });
    useExplorer.getState().toggleCollapsed();
    expect(useExplorer.getState().collapsed).toBe(true);
    expect(window.localStorage.getItem("hardcore.explorer.collapsed")).toBeNull();
  });

  it("remembers the toggle for the project it was made in", () => {
    useExplorer.getState().toggleCollapsed();
    expect(useExplorer.getState().collapsed).toBe(false);
    expect(JSON.parse(window.localStorage.getItem("hardcore.explorer.collapsed") ?? "{}")).toEqual({
      [PROJECT]: false,
    });
  });

  it("selects the neighbour when the active tab closes", () => {
    const { open } = useExplorer.getState();
    const first = open("file");
    const second = open("review");
    const third = open("terminal");

    useExplorer.getState().setActive(second!.id);
    useExplorer.getState().close(second!.id);

    expect(useExplorer.getState().activeId).toBe(third!.id);
    expect(useExplorer.getState().tabs.map((tab) => tab.id)).toEqual([first!.id, third!.id]);
  });

  it("leaves the selection alone when an inactive tab closes", () => {
    const { open } = useExplorer.getState();
    const first = open("file");
    const second = open("review");
    useExplorer.getState().setActive(second!.id);
    useExplorer.getState().close(first!.id);
    expect(useExplorer.getState().activeId).toBe(second!.id);
  });

  it("renumbers order after a close so the strip stays contiguous", () => {
    const { open } = useExplorer.getState();
    const first = open("file");
    open("review");
    open("terminal");
    useExplorer.getState().close(first!.id);
    expect(useExplorer.getState().tabs.map((tab) => tab.order)).toEqual([0, 1]);
  });

  it("kills the pty when a terminal tab closes", () => {
    const tab = useExplorer.getState().open("terminal");
    useExplorer.getState().update(tab!.id, { ptyId: "pty-9" });
    useExplorer.getState().close(tab!.id);
    expect(window.hardcore.terminal.kill).toHaveBeenCalledWith({ id: "pty-9" });
  });

  it("reuses the tab already showing a file", () => {
    const first = useExplorer.getState().openFile("README.md");
    const again = useExplorer.getState().openFile("README.md");
    expect(again!.id).toBe(first!.id);
    expect(useExplorer.getState().tabs).toHaveLength(1);
  });

  it("never holds two tabs for one file, whichever door opened it", () => {
    const { open, openFile } = useExplorer.getState();
    const first = openFile("src/a.ts");
    const again = open("file", { path: "src/a.ts", root: null });
    expect(again?.id).toBe(first?.id);
    expect(useExplorer.getState().tabs).toHaveLength(1);
    // The same path in another root is another file.
    open("file", { path: "src/a.ts", root: "/tmp/worktree" });
    expect(useExplorer.getState().tabs).toHaveLength(2);
  });

  it("drops a duplicate that reaches the strip by any other path, keeping the selection", () => {
    const tabs = [
      { id: "t1", kind: "file", path: "a.ts", root: null },
      { id: "t2", kind: "file", path: "a.ts", root: null },
      { id: "t3", kind: "file", path: null, root: null },
      { id: "t4", kind: "file", path: null, root: null },
    ] as never[];
    const result = dedupeFileTabs(tabs, "t2");
    expect(result.tabs.map((tab: { id: string }) => tab.id)).toEqual(["t1", "t3", "t4"]);
    expect(result.activeId).toBe("t1");
  });

  it("fills the blank tab the + button made instead of stacking one", () => {
    const blank = useExplorer.getState().open("file");
    const opened = useExplorer.getState().openFile("src/main/index.ts");
    expect(opened!.id).toBe(blank!.id);
    expect(useExplorer.getState().tabs).toHaveLength(1);
    expect(useExplorer.getState().tabs[0]).toMatchObject({ path: "src/main/index.ts" });
  });

  it("reorders on a drag and renumbers", () => {
    const { open } = useExplorer.getState();
    const first = open("file");
    const second = open("review");
    const third = open("terminal");

    useExplorer.getState().move(third!.id, 0);

    expect(useExplorer.getState().tabs.map((tab) => tab.id)).toEqual([
      third!.id,
      first!.id,
      second!.id,
    ]);
    expect(useExplorer.getState().tabs.map((tab) => tab.order)).toEqual([0, 1, 2]);
  });

  it("maps Cmd+9 to the last tab, not the ninth", () => {
    const { open } = useExplorer.getState();
    open("file");
    open("review");
    const last = open("terminal");
    useExplorer.getState().selectIndex(useExplorer.getState().tabs.length);
    expect(useExplorer.getState().activeId).toBe(last!.id);
  });

  it("persists the strip once, after the burst of changes", () => {
    const { open } = useExplorer.getState();
    open("file");
    open("review");
    open("terminal");

    expect(window.hardcore.explorer.saveTabs).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(window.hardcore.explorer.saveTabs).toHaveBeenCalledTimes(1);
    expect(vi.mocked(window.hardcore.explorer.saveTabs).mock.calls[0]?.[0]).toMatchObject({
      projectId: PROJECT,
    });
  });

  it("flushes the outgoing debounce and waits for that save on a rapid project return", async () => {
    const blank = useExplorer.getState().open("file")!;
    const stored = new Map<string, PersistedExplorerTab[]>([[PROJECT, [PersistedExplorerTabSchema.parse(blank)]]]);
    const saved = deferred<void>();
    vi.mocked(window.hardcore.explorer.saveTabs).mockImplementation(async ({ projectId, tabs }) => {
      if (projectId === PROJECT) await saved.promise;
      stored.set(projectId, tabs.map(tab => PersistedExplorerTabSchema.parse(tab)));
    });
    vi.mocked(window.hardcore.explorer.loadTabs).mockImplementation(async ({ projectId }) => stored.get(projectId) ?? []);

    useExplorer.getState().openFile("icon.png");
    expect(window.hardcore.explorer.saveTabs).not.toHaveBeenCalled();
    const leaving = useExplorer.getState().bindProject("project-2");
    expect(useExplorer.getState()).toMatchObject({ projectId: "project-2", ready: false });
    expect(window.hardcore.explorer.saveTabs).toHaveBeenCalledExactlyOnceWith({
      projectId: PROJECT, tabs: [expect.objectContaining({ id: blank.id, path: "icon.png" })],
    });
    // Loading B does not wait for A's delayed IPC write.
    await leaving;
    expect(useExplorer.getState()).toMatchObject({ projectId: "project-2", ready: true });
    const returning = useExplorer.getState().bindProject(PROJECT);
    expect(useExplorer.getState()).toMatchObject({ projectId: PROJECT, ready: false });
    expect(window.hardcore.explorer.loadTabs).not.toHaveBeenCalledWith({ projectId: PROJECT });
    saved.resolve();
    await returning;
    expect(window.hardcore.explorer.loadTabs).toHaveBeenCalledWith({ projectId: PROJECT });
    expect(useExplorer.getState()).toMatchObject({ ready: true, activeId: blank.id });
    expect(useExplorer.getState().tabs).toMatchObject([{ id: blank.id, path: "icon.png" }]);
  });

  it.each(["resolved", "rejected"])("serializes a flushed update behind a %s earlier save before restoring", async outcome => {
    const earlier = deferred<void>();
    const stored = new Map<string, PersistedExplorerTab[]>();
    const saveTabs = vi.mocked(window.hardcore.explorer.saveTabs);
    saveTabs.mockImplementationOnce(async ({ projectId, tabs }) => {
      await earlier.promise;
      stored.set(projectId, tabs.map(tab => PersistedExplorerTabSchema.parse(tab)));
    }).mockImplementation(async ({ projectId, tabs }) => { stored.set(projectId, tabs.map(tab => PersistedExplorerTabSchema.parse(tab))); });
    vi.mocked(window.hardcore.explorer.loadTabs).mockImplementation(async ({ projectId }) => stored.get(projectId) ?? []);

    const tab = useExplorer.getState().open("file")!;
    vi.advanceTimersByTime(400);
    expect(saveTabs).toHaveBeenCalledTimes(1);
    useExplorer.getState().openFile("icon.png");
    await useExplorer.getState().bindProject("project-2");
    const returning = useExplorer.getState().bindProject(PROJECT);
    expect(saveTabs).toHaveBeenCalledTimes(1);
    expect(window.hardcore.explorer.loadTabs).not.toHaveBeenCalledWith({ projectId: PROJECT });
    if (outcome === "rejected") earlier.reject(new Error("Temporary persistence failure"));
    else earlier.resolve();
    await returning;
    expect(saveTabs).toHaveBeenCalledTimes(2);
    expect(saveTabs.mock.calls[1]?.[0]).toMatchObject({ projectId: PROJECT, tabs: [{ id: tab.id, path: "icon.png" }] });
    expect(useExplorer.getState()).toMatchObject({ projectId: PROJECT, ready: true });
    expect(useExplorer.getState().tabs).toMatchObject([{ id: tab.id, path: "icon.png" }]);
  });

  it("ignores an earlier visit's late load after returning to the same project", async () => {
    const earlier = deferred<PersistedExplorerTab[]>();
    const base = { kind: "file", projectId: PROJECT, order: 0, root: null, panel: null } as const;
    const current: PersistedExplorerTab[] = [{ ...base, id: "current", path: "icon.png" }];
    vi.mocked(window.hardcore.explorer.loadTabs)
      .mockImplementationOnce(() => earlier.promise)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce(current);
    useExplorer.setState({ projectId: null });
    const firstVisit = useExplorer.getState().bindProject(PROJECT);
    await useExplorer.getState().bindProject("project-2");
    await useExplorer.getState().bindProject(PROJECT);
    expect(useExplorer.getState().tabs).toEqual(current);
    earlier.resolve([{ ...base, id: "old", path: null }]);
    await firstVisit;
    expect(useExplorer.getState().tabs).toEqual(current);
    expect(useExplorer.getState().activeId).toBe("current");
  });

  it("ignores a change batch for another project", () => {
    useExplorer.getState().receiveChanges("some-other-project", null, [{ kind: "changed", path: "a.txt", directory: false }]);
    expect(useExplorer.getState().fsRevision).toBe(0);
    useExplorer.getState().receiveChanges(PROJECT, null, [{ kind: "changed", path: "a.txt", directory: false }]);
    expect(useExplorer.getState().fsRevision).toBe(1);
    expect(useExplorer.getState().changedPaths).toEqual(["a.txt"]);
    expect(useExplorer.getState().changedRoot).toBeNull();
    useExplorer.getState().receiveChanges(PROJECT, "/wt/slug", [{ kind: "changed", path: "b.txt", directory: false }]);
    expect(useExplorer.getState().changedRoot).toBe("/wt/slug");
  });

  /**
   * The root (plan §9): where a new file or terminal opens, and which tree the
   * pane lists. It follows the active session — a worktree thread makes it the
   * worktree — while every tab keeps the root it was opened in.
   */
  describe("roots", () => {
    const WORKTREE = "/home/me/.hardcore/worktrees/proj/model-the-wrist";

    it("opens files and terminals in the active root, and remembers it on the tab", () => {
      useExplorer.getState().setRoot(WORKTREE);
      const file = useExplorer.getState().openFile("STEP/wrist.step");
      expect(file).toMatchObject({ kind: "file", path: "STEP/wrist.step", root: WORKTREE });
      const terminal = useExplorer.getState().open("terminal");
      expect(terminal).toMatchObject({ kind: "terminal", cwd: WORKTREE });
      useExplorer.getState().setRoot(null);
      expect(useExplorer.getState().open("file")).toMatchObject({ kind: "file", root: null });
      expect(useExplorer.getState().open("terminal")).toMatchObject({ kind: "terminal", cwd: null });
      // The worktree tab still says where it came from.
      expect(useExplorer.getState().tabs.find((tab) => tab.id === file?.id)).toMatchObject({ root: WORKTREE });
    });

    it("keeps the same path in two roots as two tabs, and reuses within a root", () => {
      useExplorer.getState().setRoot(null);
      const checkout = useExplorer.getState().openFile("README.md");
      const worktree = useExplorer.getState().openFile("README.md", WORKTREE);
      expect(worktree?.id).not.toBe(checkout?.id);
      expect(useExplorer.getState().openFile("README.md", WORKTREE)?.id).toBe(worktree?.id);
      expect(useExplorer.getState().openFile("README.md")?.id).toBe(checkout?.id);
      expect(useExplorer.getState().tabs).toHaveLength(2);
    });

    it("fills a blank tab with the root it was asked for", () => {
      useExplorer.getState().open("file");
      const filled = useExplorer.getState().openFile("a.py", WORKTREE);
      expect(useExplorer.getState().tabs).toHaveLength(1);
      expect(filled).toMatchObject({ path: "a.py", root: WORKTREE });
    });

    it("switches the watcher with the root and keeps each root's tree", () => {
      useExplorer.getState().setRoot(null);
      useExplorer.getState().setTreeOpen(null, (open) => new Set([...open, "src"]));
      vi.mocked(window.hardcore.explorer.watch).mockClear();
      vi.mocked(window.hardcore.explorer.unwatch).mockClear();
      useExplorer.getState().setRoot(WORKTREE);
      expect(window.hardcore.explorer.unwatch).toHaveBeenCalledWith({ projectId: PROJECT });
      expect(window.hardcore.explorer.watch).toHaveBeenCalledWith({ projectId: PROJECT, root: WORKTREE });
      expect(useExplorer.getState().root).toBe(WORKTREE);
      // The worktree's tree starts fresh; the checkout's keeps its open folder.
      expect(useExplorer.getState().trees[WORKTREE]).toBeUndefined();
      expect(useExplorer.getState().trees[""]?.open.has("src")).toBe(true);
      // Setting the same root again is a no-op.
      vi.mocked(window.hardcore.explorer.watch).mockClear();
      useExplorer.getState().setRoot(WORKTREE);
      expect(window.hardcore.explorer.watch).not.toHaveBeenCalled();
    });

    it("drops a reveal when the root changes; a reveal names its root", () => {
      useExplorer.getState().setRoot(null);
      useExplorer.getState().setReveal({ path: "STEP", directory: true, root: null });
      useExplorer.getState().setRoot(WORKTREE);
      expect(useExplorer.getState().reveal).toBeNull();
    });
  });

  it("opens the pane when a tab of any kind opens, without writing a preference", () => {
    for (const kind of ["file", "review", "browser", "terminal", "drawing"] as const) {
      useExplorer.setState({ collapsed: true, tabs: [], activeId: null });
      useExplorer.getState().open(kind);
      expect(useExplorer.getState().collapsed, kind).toBe(false);
    }
    useExplorer.setState({ collapsed: true, tabs: [], activeId: null });
    useExplorer.getState().openFile("src/wrist.step");
    expect(useExplorer.getState().collapsed).toBe(false);
    // The person never said anything, so nothing was remembered for them.
    expect(window.localStorage.getItem("hardcore.explorer.collapsed")).toBeNull();
  });

  it("remembers the pane's state for the project it was chosen in", () => {
    useExplorer.getState().setCollapsed(false);
    void useExplorer.getState().bindProject("project-2");
    // A project nobody has opened the pane in starts closed.
    expect(useExplorer.getState().collapsed).toBe(true);
    void useExplorer.getState().bindProject(PROJECT);
    expect(useExplorer.getState().collapsed).toBe(false);
  });

  it("titles a tab by what a person would call it", () => {
    const base = { id: "t", projectId: PROJECT, order: 0 } as const;
    expect(tabTitle({ ...base, kind: "file", path: "src/wrist.step", root: null, panel: null })).toBe(
      "wrist.step",
    );
    expect(tabTitle({ ...base, kind: "file", path: null, root: null, panel: null })).toBe("Untitled");
    expect(tabTitle({ ...base, kind: "browser", root: null, url: "https://example.com/a/b" })).toBe(
      "example.com",
    );
    expect(tabTitle({ ...base, kind: "browser", root: null, url: null })).toBe("New tab");
    expect(tabTitle({ ...base, kind: "review", scope: "all", sessionId: null })).toBe("Review");
  });
});
