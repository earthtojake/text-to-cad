import { beforeEach, describe, expect, it } from "vitest";

import { tabTitle, useExplorer } from "@renderer/state/explorer";

describe("the explorer strip", () => {
  beforeEach(() => {
    useExplorer.setState({ tabs: [], activeId: null });
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
    expect(useExplorer.getState().activeId).toBe(tab.id);
  });

  it("selects the neighbour when the active tab closes", () => {
    const { open } = useExplorer.getState();
    const first = open("file");
    const second = open("review");
    const third = open("terminal");

    useExplorer.getState().setActive(second.id);
    useExplorer.getState().close(second.id);

    expect(useExplorer.getState().activeId).toBe(third.id);
    expect(useExplorer.getState().tabs.map((tab) => tab.id)).toEqual([first.id, third.id]);
  });

  it("leaves the selection alone when an inactive tab closes", () => {
    const { open } = useExplorer.getState();
    const first = open("file");
    const second = open("review");
    useExplorer.getState().setActive(second.id);
    useExplorer.getState().close(first.id);
    expect(useExplorer.getState().activeId).toBe(second.id);
  });

  it("renumbers order after a close so the strip stays contiguous", () => {
    const { open } = useExplorer.getState();
    const first = open("file");
    open("review");
    open("terminal");
    useExplorer.getState().close(first.id);
    expect(useExplorer.getState().tabs.map((tab) => tab.order)).toEqual([0, 1]);
  });

  it("titles a file tab by its basename", () => {
    expect(
      tabTitle({ id: "t", sessionId: "s", order: 0, kind: "file", path: "/a/b/wrist.step", viewSource: false }),
    ).toBe("wrist.step");
    expect(tabTitle({ id: "t", sessionId: "s", order: 0, kind: "file", path: null, viewSource: false })).toBe(
      "Untitled",
    );
  });
});
