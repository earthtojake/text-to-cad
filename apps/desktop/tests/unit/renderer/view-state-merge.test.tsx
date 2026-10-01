import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { useDesktopViewState } from "@renderer/features/explorer/adapters/persistence";
import { forgetTabStore } from "@renderer/features/explorer/adapters/tabStore";
import { useExplorer } from "@renderer/state/explorer";

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  useExplorer.setState({ sessionId: "session", projectId: "merge-project", root: null, tabs: [], activeId: null, ready: true, trees: {}, panelWidth: 248 });
});

it("a stale view cannot overwrite another tab's file views or newer root chrome", () => {
  const tabA = useExplorer.getState().open("file", { path: "a.step" })!;
  const tabB = useExplorer.getState().open("file", { path: "b.step" })!;
  const a = renderHook(() => useDesktopViewState("shared-root", tabA.id, null, null));
  const b = renderHook(() => useDesktopViewState("shared-root", tabB.id, null, null));
  const oldA = a.result.current;
  const oldB = b.result.current;
  act(() => oldB.onStateChange({ ...oldB.state, panelWidth: 360, expandedDirectories: ["parts"], renderers: { '["b.step","step"]': { camera: "new-b" } } }));
  act(() => oldA.onStateChange({ ...oldA.state, renderers: { '["a.step","step"]': { camera: "new-a" } } }));
  const stored = JSON.parse(localStorage.getItem("text-to-cad.tabs.v1")!);
  expect(Object.keys(stored)).toEqual([tabB.id, tabA.id]);
  expect(stored[tabA.id].files).toEqual({ [JSON.stringify(["shared-root", "a.step", "step"])]: { camera: "new-a" } });
  expect(stored[tabB.id].files).toEqual({ [JSON.stringify(["shared-root", "b.step", "step"])]: { camera: "new-b" } });
  expect(a.result.current.state.renderers).toEqual({ '["a.step","step"]': { camera: "new-a" } });
  // The explorer's chrome is the window's and the root's, not the tab record's.
  expect(useExplorer.getState().panelWidth).toBe(360);
  expect(a.result.current.state.expandedDirectories).toEqual(["parts"]);
  expect(stored[tabB.id].settings.fileTree).toEqual({ width: 220, expanded: {} });
  a.unmount(); b.unmount();
  forgetTabStore(tabA.id); forgetTabStore(tabB.id);
});
