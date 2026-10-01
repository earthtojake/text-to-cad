import type { PromptReference } from '@text-to-cad/core/prompt';
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

/**
 * The predicate that says a `select` is on screen: the live selection is the SET the command
 * resolved, not merely a non-empty one. `partIds` are the viewer's own part ids (what
 * `selectedPartIds` of the live state holds, after the assembly's re-mapping) and `referenceIds`
 * the resolved references. Every one must be held and, for a replacing select, nothing else, so
 * a previous selection (or a part-only selector, whose references are vacuously all held) cannot
 * answer for the new one.
 */
export function selectionCommitted(
  { partIds, referenceIds, replace }: { partIds: readonly string[]; referenceIds: readonly string[]; replace: boolean },
): (state: Pick<CadLiveState, 'selectedPartIds' | 'selectedReferenceIds'>) => boolean {
  const holds = (held: readonly string[], wanted: readonly string[]) => wanted.every(id => held.includes(id))
    && (!replace || held.every(id => wanted.includes(id)));
  return state => holds(state.selectedPartIds, partIds) && holds(state.selectedReferenceIds, referenceIds);
}
