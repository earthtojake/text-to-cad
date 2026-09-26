import { imageResult } from "../results";
import type { PluginCommandScope, PluginTab } from "../renderer";
import type { GcodeStats } from "./parse";

/** What the mounted viewer answers for the agent. */
export interface LiveGcodeView {
  path: string;
  state(): GcodeViewState;
  setLayer(layer: number): GcodeViewState;
  capture(): Promise<Blob>;
}
export type GcodeViewState = GcodeStats & { path: string; revision?: string; layer: number; layerZ: number | null };

// One mounted viewer per tab. A binding is the plugin's own: nothing in the app's host knows G-code.
const views = new Map<string, { tab: PluginTab; view: LiveGcodeView }>();

/** Called by a tab's viewer while it is mounted; returns the release. */
export function bindGcodeView(tab: PluginTab, view: LiveGcodeView): () => void {
  const binding = { tab, view };
  views.set(tab.tabId, binding);
  return () => { if (views.get(tab.tabId) === binding) views.delete(tab.tabId); };
}

export async function performGcodeCommand(kind: string, params: Record<string, unknown> & { tabId: string }, scope: PluginCommandScope) {
  const binding = views.get(params.tabId);
  if (!binding || binding.tab.projectId !== scope.projectId || binding.tab.root !== scope.root || binding.view.path !== scope.path) {
    throw new Error("No G-code toolpath is showing in this tab. Open the .gcode file and show its tab first.");
  }
  const { view } = binding;
  if (kind === "gcode-state") return view.state();
  if (kind === "gcode-layer") return view.setLayer(Number(params.layer));
  if (kind === "gcode-capture") { const state = view.state(); return imageResult(await view.capture(), state); }
  throw new Error(`Unknown G-code command: ${kind}`);
}
