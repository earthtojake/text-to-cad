import { formatPromptReference } from '@text-to-cad/core/prompt';
import type { PromptReference, ResourceRef } from '@text-to-cad/core/prompt';
import { createLiveRegistry as createRegistry, type LiveRegistry as Registry } from '@text-to-cad/ui/host';

/** What every renderer's live controller answers, whichever family it is. */
export interface LiveController {
  readState(): { revision?: string; active?: boolean; loading?: boolean; selection?: readonly PromptReference[]; camera?: unknown; display?: Record<string, unknown>; renderMode?: string };
  capture(): Promise<Blob>;
}

/**
 * The mounted view's live controller, bound by whichever renderer is showing. The agent's
 * tools reach the view through it: a capture, or what is on screen and selected.
 */
export const createLiveRegistry = () => createRegistry<LiveController>();
export type LiveRegistry = Registry<LiveController>;

/** The view as the agent reads it: references resolved to absolute paths it can quote back. */
export function describeView(controller: LiveController | null, model: string | null, resolvePath: (resource: ResourceRef) => string): Record<string, unknown> {
  if (!controller) return { model, loading: Boolean(model) };
  const state = controller.readState();
  const selection = (state.selection || []).flatMap(reference => {
    try { return [formatPromptReference(reference, { resolvePath })]; } catch { return []; }
  });
  return {
    model, revision: state.revision, loading: Boolean(state.loading), selection,
    camera: state.camera ?? null, display: state.display?.mode ?? null, renderMode: state.renderMode ?? null,
  };
}
