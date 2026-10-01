import type { CadLiveBinding, CadLiveController, CadLiveState } from "@text-to-cad/ui/renderers/step";
import { imageResult } from "./image-result";
type Scope = { projectId: string; root: string | null };
const live = new Map<string, Scope & { controller: CadLiveController }>();
const snapshots = new Map<string, Scope & { state: CadLiveState }>();
export function desktopCadLive(tabId: string, scope: Scope): CadLiveBinding {
  return { bind(controller) {
    const binding = { ...scope, controller }; live.set(tabId, binding);
    return () => {
      if (live.get(tabId) !== binding) return;
      // Deleted first so the Map's order is recency: the last key is the tab left most recently.
      snapshots.delete(tabId);
      snapshots.set(tabId, { ...scope, state: { ...controller.readState(), active: false } });
      live.delete(tabId);
    };
  } };
}
export async function performCadViewerCommand(kind: string, params: Record<string, unknown>, scope: Scope & { path?: string }) {
  const tabId = String(params.tabId);
  const binding = live.get(tabId);
  const snapshot = snapshots.get(tabId);
  const target = binding ?? snapshot;
  if (!target || target.projectId !== scope.projectId || target.root !== scope.root) throw new Error("No CAD viewer state in this workspace. Open the model first.");
  const state = binding?.controller.readState() ?? snapshot!.state;
  if (scope.path && (!("path" in state.resource) || state.resource.path !== scope.path)) throw new Error("Wait for the requested model to finish loading.");
  if (kind === "viewer-state") return { tabId, ...state };
  if (!binding) throw new Error("Show the model tab before controlling its viewer.");
  const controller = binding.controller;
  if (kind === "select-reference") return controller.select({ selectors: [String(params.selector)], replace: true });
  if (kind === "cad-clear-selection") return controller.clearSelection();
  if (kind === "cad-reset-camera") return controller.resetCamera();
  if (kind === "cad-render-mode") return controller.setRenderMode(params.mode === "render");
  if (kind === "cad-camera") return controller.setCamera(params.camera as Parameters<CadLiveController['setCamera']>[0]);
  if (kind === "capture-view") {
    // The state is read AFTER the capture, which waits for the camera to rest: the image and the
    // camera it reports are the same moment.
    const blob = await controller.capture();
    const state = controller.readState();
    return imageResult(blob, { tabId, ...state });
  }
  throw new Error(`Unknown CAD operation: ${kind}`);
}

/**
 * Tab ids that have shown a CAD viewer, most recently active first: the ones displayed now, then
 * the ones left behind, newest departure first. For an integration command that names no tab.
 */
export function recentCadTabIds(): string[] {
  return [...live.keys(), ...[...snapshots.keys()].reverse()].filter((id, index, all) => all.indexOf(id) === index);
}

export function releaseCadTab(tabId: string) { live.delete(tabId); snapshots.delete(tabId); }
