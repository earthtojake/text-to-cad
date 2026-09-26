import { annotationPart, createPromptContext, referencePart, textPart } from '@hardcore/core/prompt';

/** A selector in a CAD file as a prompt reference; no selector is the whole file. */
function cadPromptReference(resource, { selector, label }) {
  return {
    resource: { ...resource },
    target: selector ? { kind: 'cad-selector', selectors: selector.split(',') } : { kind: 'whole-resource' },
    ...(label ? { label } : {}),
  };
}

/** Assemble a snapshot once, before asynchronous image encoding or host routing. */
export function createCadPromptContext({ resource, references = [], text = '', capture, operationId }) {
  const parts = references.map((reference, index) => referencePart(cadPromptReference(resource, reference), `reference-${index}`));
  if (text) parts.push(textPart(text));
  if (capture) {
    if (!parts.some(part => part.kind === 'reference')) parts.unshift(referencePart({ resource: { ...resource }, target: { kind: 'whole-resource' } }, 'source'));
    parts.push({ id: 'capture', kind: 'attachment', name: `${resource.path.split('/').pop().replace(/\.[^.]+$/, '')}-view.png`, mimeType: 'image/png', content: capture, about: parts.filter(part => part.kind === 'reference').map(part => part.id) });
  }
  return createPromptContext(parts, operationId);
}

/**
 * Annotations as one delivery: each is a part of its own (the references it is about and its
 * note), keyed by the annotation's id so adding an edited one again replaces it in the draft.
 */
export function createAnnotationsPromptContext({ resource, annotations, operationId }) {
  return createPromptContext(annotations.map(annotation => annotationPart(
    annotation.references.map(reference => cadPromptReference(resource, reference)), annotation.text, annotation.id,
  )), operationId);
}
