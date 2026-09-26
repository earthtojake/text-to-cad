import { useCallback } from 'react';
import { annotationPart, createPromptContext } from '@hardcore/core/prompt';
import type { PromptContext, PromptDeliveryResult, PromptReference } from '@hardcore/core/prompt';
import { usePromptDestination, useViewerHost } from './context.js';

// A markup made into an annotation: what the person drew over a view, captured as an image, with
// the note they typed about it, sent to the chat box as one annotation beside the prompt. Any viewer
// with ink over it (the CAD viewer's Draw, a PDF page's markup) makes the same thing: it says what
// the markup is on and how to capture it; delivery and the chat box are the same for all of them.

export interface MarkupAnnotation {
  /** What the markup is on: the file (and page), as the agent should read it. */
  reference: PromptReference;
  /** The view as it is on screen, ink included. */
  image: Promise<Blob>;
  /** The image's file name in the prompt. */
  name: string;
  note: string;
  id?: string;
}

let sequence = 0;

/** The markup's image as an attachment, and the note as an annotation on it. */
export function createMarkupAnnotationContext({ reference, image, name, note, id = `markup-${Date.now().toString(36)}-${++sequence}` }: MarkupAnnotation): PromptContext {
  const attachment = `${id}-image`;
  return createPromptContext([
    { id: attachment, kind: 'attachment', name, mimeType: 'image/png', content: image },
    annotationPart([reference], note, id, { attachment }),
  ]);
}

export interface MarkupAnnotate {
  /** False when there is no chat to add to. */
  available: boolean;
  /** Capture, deliver, and on success hand the ink back to `onAdded` (to clear it for the next one). */
  annotate(note: string): Promise<PromptDeliveryResult>;
}

/**
 * Annotate a markup from any viewer. `capture` is called at the moment of annotating; `onAdded`
 * runs when the chat box took it (a viewer clears its ink there, ready for the next markup).
 */
export function useMarkupAnnotate({ reference, capture, name, onAdded }: {
  reference: () => PromptReference | null;
  capture: () => Promise<Blob>;
  name: () => string;
  onAdded?: () => void;
}): MarkupAnnotate {
  const host = useViewerHost();
  const destination = usePromptDestination();
  const annotate = useCallback(async (note: string): Promise<PromptDeliveryResult> => {
    const on = reference();
    if (!on) return { status: 'failed', message: 'Nothing to annotate yet.' };
    let result: PromptDeliveryResult;
    try {
      result = await host.promptContext.deliver(createMarkupAnnotationContext({ reference: on, image: capture(), name: name(), note }));
    } catch (error) {
      result = { status: 'failed', message: error instanceof Error ? error.message : String(error) };
    }
    if (result.status === 'added' || result.status === 'copied' || result.status === 'partial') onAdded?.();
    return result;
  }, [host.promptContext, reference, capture, name, onAdded]);
  return { available: destination.available, annotate };
}
