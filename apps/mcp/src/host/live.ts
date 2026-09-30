import { formatPromptReference } from '@text-to-cad/core/prompt';
import type { PromptReference, ResourceRef } from '@text-to-cad/core/prompt';

/** What every renderer's live controller answers, whichever family it is. */
export interface LiveController {
  readState(): { revision?: string; active?: boolean; loading?: boolean; selection?: readonly PromptReference[]; camera?: unknown; display?: Record<string, unknown>; renderMode?: string };
  capture(): Promise<Blob>;
}

/**
 * The mounted view's live controller, bound by whichever renderer is showing. The agent's
 * tools reach the view through it: a capture, or what is on screen and selected.
 */
export function createLiveRegistry() {
  let current: LiveController | null = null;
  const listeners = new Set<() => void>();
  const changed = () => { for (const listener of [...listeners]) listener(); };
  return {
    binding: {
      bind(controller: LiveController) {
        current = controller;
        changed();
        return () => { if (current === controller) { current = null; changed(); } };
      },
    },
    current: () => current,
    subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener); },
  };
}
export type LiveRegistry = ReturnType<typeof createLiveRegistry>;

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

/** A PNG of the view, scaled to at most `width` pixels wide. */
export async function scaledPng(image: Blob, width: number): Promise<Blob> {
  const bitmap = await createImageBitmap(image);
  try {
    const scale = Math.min(1, width / bitmap.width);
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Could not encode the thumbnail.')), 'image/png'));
  } finally { bitmap.close(); }
}
