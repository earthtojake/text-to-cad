import type { PromptReference } from '@hardcore/core/prompt';
import type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

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
