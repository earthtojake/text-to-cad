import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createDesktopCadCommands } from "@renderer/features/explorer/host/cadCommands";
import { useExplorer } from "@renderer/state/explorer";
import { desktopCadLive, performCadViewerCommand } from "@renderer/state/live-cad";
import { MAX_IMAGE_BYTES } from "@shared/image-cap";
import type { CadLiveController } from "@text-to-cad/ui/renderers/step";

const shrink = vi.hoisted(() => vi.fn());
vi.mock("@renderer/lib/shrink-image", () => ({ shrinkImage: shrink }));

beforeEach(() => {
  vi.useFakeTimers();
  useExplorer.setState({ sessionId: "session", projectId: "project", root: null, tabs: [], activeId: null,
    cadSelection: null, cadCapture: null, cadAnnotation: null, ready: true });
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
  expect(source.getSnapshot()).toEqual({ selectReference: null, captureRequest: null, openAnnotation: null });
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

it("asks the active CAD tab to open an annotation, once, and forgets it when the tab changes", () => {
  const tab = useExplorer.getState().openFile("bracket.step", null)!;
  const source = createDesktopCadCommands("project", null, tab.id);
  useExplorer.getState().openCadAnnotation(tab.id, "a1");
  const asked = source.getSnapshot().openAnnotation;
  expect(asked).toMatchObject({ id: "a1" });
  source.acknowledge("openAnnotation", asked!.key);
  expect(source.getSnapshot().openAnnotation).toBeNull();
  useExplorer.getState().openCadAnnotation(tab.id, "a2");
  useExplorer.getState().update(tab.id, { path: "other.step" });
  expect(source.getSnapshot().openAnnotation).toBeNull();
});

async function captureWith(capture: () => Promise<Blob>, readState: () => object = () => ({ active: true, resource: { path: "a.step" } })) {
  const scope = { projectId: "project", root: null };
  desktopCadLive("cap-tab", scope).bind({ readState, capture } as unknown as CadLiveController);
  return performCadViewerCommand("capture-view", { tabId: "cap-tab" }, { ...scope, path: "a.step" }) as Promise<{ base64: string; scaled?: boolean; camera?: unknown }>;
}
it("scales a viewer capture over the model image limit down, and says so", async () => {
  const big = new Blob([new Uint8Array(4 * 1024 * 1024)], { type: "image/png" });
  shrink.mockReset().mockResolvedValueOnce(new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" }));
  const result = await captureWith(async () => big);
  expect(big.size).toBeGreaterThan(MAX_IMAGE_BYTES);
  expect(shrink).toHaveBeenCalled();
  expect(result.scaled).toBe(true);
  expect(result.base64.length * 3 / 4).toBeLessThan(MAX_IMAGE_BYTES);
});
it("passes a capture already under the limit through untouched", async () => {
  shrink.mockReset();
  const result = await captureWith(async () => new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" }));
  expect(shrink).not.toHaveBeenCalled();
  expect(result).not.toHaveProperty("scaled");
});
it("rejects a viewer capture that fails, so the agent gets an error and not an image", async () => {
  await expect(captureWith(async () => { throw new Error("the viewer's WebGL context is lost; try again once it restores"); })).rejects.toThrow(/WebGL context is lost/);
});
it("reports the state AFTER the capture resolves, since the capture waits for the camera to rest", async () => {
  let camera = "mid-flight";
  const result = await captureWith(async () => { camera = "at rest"; return new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" }); },
    () => ({ active: true, resource: { path: "a.step" }, camera }));
  expect(result.camera).toBe("at rest");
});
