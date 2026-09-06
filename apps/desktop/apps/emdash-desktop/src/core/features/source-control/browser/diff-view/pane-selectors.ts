/**
 * Pane selectors for the diff-view domain.
 *
 * These helpers let diff UI read diff-tab state from a generic PaneStore
 * without the engine having to know about DiffTabResource.
 */
import type { PaneStore } from '@core/primitives/workbench-shell/browser/tabs/pane-store';
import type { DiffTabResource } from './stores/diff-tab-resource';

export function activeDiffResource(pane: PaneStore): DiffTabResource | undefined {
  return pane.activeResourceOfKind<DiffTabResource>('diff');
}

/** @deprecated Use activeDiffResource */
export const activeDiffEntry = activeDiffResource;
