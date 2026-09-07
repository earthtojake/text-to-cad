import { beforeEach, describe, expect, it, vi } from "vitest";

import { tabTitle, useExplorer } from "@renderer/state/explorer";

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

function reset() {
  window.localStorage.clear();
  useExplorer.setState({
    projectId: PROJECT,
    root: null,
    tabs: [],
    activeId: null,
    ready: true,
    expanded: false,
    collapsed: true,
    fsRevision: 0,
    changedPaths: [],
  });
}

describe("the explorer strip", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    reset();
  });

  it("opens each of the four kinds into one strip", () => {
    const { open } = useExplorer.getState();
    for (const kind of ["file", "review", "browser", "terminal"] as const) {
      open(kind);
    }
    expect(useExplorer.getState().tabs.map((tab) => tab.kind)).toEqual([
      "file",
      "review",
      "browser",
      "terminal",
    ]);
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

  it("ignores a change batch for another project", () => {
    useExplorer.getState().receiveChanges("some-other-project", null, ["a.txt"]);
    expect(useExplorer.getState().fsRevision).toBe(0);
    useExplorer.getState().receiveChanges(PROJECT, null, ["a.txt"]);
    expect(useExplorer.getState().fsRevision).toBe(1);
    expect(useExplorer.getState().changedPaths).toEqual(["a.txt"]);
    expect(useExplorer.getState().changedRoot).toBeNull();
    useExplorer.getState().receiveChanges(PROJECT, "/wt/slug", ["b.txt"]);
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
    for (const kind of ["file", "review", "browser", "terminal"] as const) {
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
    expect(tabTitle({ ...base, kind: "file", path: "src/wrist.step", root: null, viewSource: false })).toBe(
      "wrist.step",
    );
    expect(tabTitle({ ...base, kind: "file", path: null, root: null, viewSource: false })).toBe("Untitled");
    expect(tabTitle({ ...base, kind: "browser", url: "https://example.com/a/b" })).toBe(
      "example.com",
    );
    expect(tabTitle({ ...base, kind: "browser", url: null })).toBe("New tab");
    expect(tabTitle({ ...base, kind: "review", scope: "all", sessionId: null })).toBe("Review");
  });
});
