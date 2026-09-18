import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { mergeRendererState, useDesktopViewState } from "@renderer/features/explorer/adapters/persistence";
import { useExplorer } from "@renderer/state/explorer";

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  useExplorer.setState({ sessionId: "session", projectId: "merge-project", root: null, tabs: [], activeId: null, ready: true, trees: {}, panelWidth: 248 });
});

it("merges only renderer keys changed by a view, including deletion", () => {
  expect(mergeRendererState({ a: "latest-a", b: "new-b", c: "new-c" }, { a: "old-a", b: "old-b" }, { a: "changed-a", b: "old-b" })).toEqual({ a: "changed-a", b: "new-b", c: "new-c" });
  expect(mergeRendererState({ a: "latest-a", b: "new-b" }, { a: "old-a" }, {})).toEqual({ b: "new-b" });
});

it("a stale view cannot overwrite another tab's renderer state or newer root chrome", () => {
  const tabA = useExplorer.getState().open("file", { path: "a.step" })!;
  const tabB = useExplorer.getState().open("file", { path: "b.step" })!;
  const a = renderHook(() => useDesktopViewState("shared-root", tabA.id, null, null, "/project"));
  const b = renderHook(() => useDesktopViewState("shared-root", tabB.id, null, null, "/project"));
  const oldA = a.result.current;
  const oldB = b.result.current;
  act(() => oldB.onStateChange({ ...oldB.state, panelWidth: 360, expandedDirectories: ["parts"], renderers: { '["b.step","cad"]': { camera: "new-b" } } }));
  act(() => oldA.onStateChange({ ...oldA.state, renderers: { '["a.step","cad"]': { camera: "new-a" } } }));
  expect(JSON.parse(localStorage.getItem("hardcore.fileViewer.v1")!)).toEqual({
    [JSON.stringify(["shared-root", tabA.id])]: { '["a.step","cad"]': { camera: "new-a" } },
    [JSON.stringify(["shared-root", tabB.id])]: { '["b.step","cad"]': { camera: "new-b" } },
  });
  expect(useExplorer.getState().panelWidth).toBe(360);
  expect(a.result.current.state.expandedDirectories).toEqual(["parts"]);
  a.unmount(); b.unmount();
});
