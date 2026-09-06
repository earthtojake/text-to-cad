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
  useExplorer.setState({
    projectId: PROJECT,
    tabs: [],
    activeId: null,
    ready: true,
    expanded: false,
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
    useExplorer.getState().receiveChanges("some-other-project", ["a.txt"]);
    expect(useExplorer.getState().fsRevision).toBe(0);
    useExplorer.getState().receiveChanges(PROJECT, ["a.txt"]);
    expect(useExplorer.getState().fsRevision).toBe(1);
    expect(useExplorer.getState().changedPaths).toEqual(["a.txt"]);
  });

  it("titles a tab by what a person would call it", () => {
    const base = { id: "t", projectId: PROJECT, order: 0 } as const;
    expect(tabTitle({ ...base, kind: "file", path: "src/wrist.step", viewSource: false })).toBe(
      "wrist.step",
    );
    expect(tabTitle({ ...base, kind: "file", path: null, viewSource: false })).toBe("Untitled");
    expect(tabTitle({ ...base, kind: "browser", url: "https://example.com/a/b" })).toBe(
      "example.com",
    );
    expect(tabTitle({ ...base, kind: "browser", url: null })).toBe("New tab");
    expect(tabTitle({ ...base, kind: "review", scope: "all", sessionId: null })).toBe("Review");
  });
});
