import type { PromptReference } from '@hardcore/core/prompt';
import { attachLiveBinding } from '../kit/shell/liveBinding.js';
import type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewRuntime, LiveViewState } from '../kit/shell/liveBinding.js';

export type CadCameraSnapshot = LiveCameraSnapshot;
export interface CadLiveState extends LiveViewState {
  selection: readonly PromptReference[];
  selectedPartIds: readonly string[];
  selectedReferenceIds: readonly string[];
  hiddenPartIds: readonly string[];
  isolatedPartIds: readonly string[];
}
export interface CadLiveController extends LiveViewController<CadLiveState> {
  select(options: { selectors: readonly string[]; replace?: boolean }): Promise<CadLiveState>;
  clearSelection(): Promise<CadLiveState>;
}
export type CadLiveBinding = LiveViewBinding<CadLiveController>;

interface CadLiveRuntime extends LiveViewRuntime<CadLiveState> {
  select(options: Parameters<CadLiveController['select']>[0]): void;
  clearSelection(): void;
}

/** This renderer's commands on the shared live surface: it selects, so it adds the two selection commands. */
export function attachCadLiveBinding(binding: CadLiveBinding, readRuntime: () => CadLiveRuntime,
  settle?: () => Promise<void>): () => void {
  return attachLiveBinding(binding, readRuntime, { settle, commands: ['select', 'clearSelection'] });
}
