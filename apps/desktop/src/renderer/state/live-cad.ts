import type { CadLiveBinding, CadLiveController, CadLiveState } from "@hardcore/ui/renderers/cad";
type Scope = { projectId: string; root: string | null };
const live = new Map<string, Scope & { controller: CadLiveController }>();
const snapshots = new Map<string, Scope & { state: CadLiveState }>();
export function desktopCadLive(tabId: string, scope: Scope): CadLiveBinding {
  return { bind(controller) {
    const binding = { ...scope, controller }; live.set(tabId, binding);
    return () => {
      if (live.get(tabId) !== binding) return;
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
    const state = controller.readState();
    const blob = await controller.capture();
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = ""; for (const byte of bytes) binary += String.fromCharCode(byte);
    return { tabId, ...state, base64: btoa(binary), mimeType: blob.type };
  }
  throw new Error(`Unknown CAD operation: ${kind}`);
}

export function releaseCadTab(tabId: string) { live.delete(tabId); snapshots.delete(tabId); }
