import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createDesktopCadCommands } from "@renderer/features/explorer/host/cadCommands";
import { useExplorer } from "@renderer/state/explorer";

beforeEach(() => {
  vi.useFakeTimers();
  useExplorer.setState({ projectId: "project", root: null, tabs: [], activeId: null,
    cadSelection: null, cadCapture: null, ready: true });
});
afterEach(() => { vi.runOnlyPendingTimers(); vi.useRealTimers(); });

it("captures the request document and drops it when that tab changes path or root", () => {
  const tab = useExplorer.getState().openFile("first.step", null)!;
  const source = createDesktopCadCommands("project", null, tab.id);
  useExplorer.getState().selectCadReference(tab.id, "o1.f2");
  useExplorer.getState().captureCad(tab.id);
  expect(useExplorer.getState().cadSelection).toMatchObject({ projectId: "project", path: "first.step", root: null });
  expect(source.getSnapshot().captureRequest).not.toBeNull();
  useExplorer.getState().update(tab.id, { path: "replacement.step" });
  expect(source.getSnapshot()).toEqual({ selectReference: null, captureRequest: null });
  expect(useExplorer.getState().cadSelection).toBeNull();
  useExplorer.getState().captureCad(tab.id);
  useExplorer.getState().update(tab.id, { root: "/other" });
  expect(source.getSnapshot().captureRequest).toBeNull();
  expect(useExplorer.getState().cadCapture).toBeNull();
});

it("acknowledges only its original nonce and never replays after an ordinary remount", () => {
  const tab = useExplorer.getState().openFile("part.step", null)!;
  const source = createDesktopCadCommands("project", null, tab.id);
  useExplorer.getState().captureCad(tab.id);
  const first = source.getSnapshot().captureRequest!.key;
  useExplorer.getState().captureCad(tab.id);
  const second = source.getSnapshot().captureRequest!.key;
  expect(second).not.toBe(first);
  source.acknowledge("captureRequest", first);
  expect(source.getSnapshot().captureRequest!.key).toBe(second);
  source.acknowledge("captureRequest", second);
  source.acknowledge("captureRequest", second);
  expect(createDesktopCadCommands("project", null, tab.id).getSnapshot().captureRequest).toBeNull();
  useExplorer.getState().selectCadReference(tab.id, "o1.f2");
  const selected = source.getSnapshot().selectReference!.key!;
  source.acknowledge("selectReference", selected);
  useExplorer.getState().selectCadReference(tab.id, "o1.f2");
  expect(source.getSnapshot().selectReference!.key).not.toBe(selected);
});

it("rejects background, replacement project and closed-tab requests", () => {
  const first = useExplorer.getState().openFile("a.step", null)!;
  const second = useExplorer.getState().openFile("b.step", null)!;
  const source = createDesktopCadCommands("project", null, first.id);
  useExplorer.getState().captureCad(first.id);
  expect(useExplorer.getState().cadCapture).toBeNull();
  useExplorer.getState().setActive(first.id);
  useExplorer.getState().selectCadReference(first.id, "o1");
  useExplorer.getState().setActive(second.id);
  useExplorer.getState().setActive(first.id);
  expect(source.getSnapshot().selectReference).toBeNull();
  useExplorer.getState().captureCad(first.id);
  useExplorer.setState({ projectId: "replacement" });
  expect(source.getSnapshot().captureRequest).toBeNull();
  useExplorer.setState({ projectId: "project" });
  useExplorer.getState().close(first.id);
  expect(useExplorer.getState().cadCapture).toBeNull();
});
