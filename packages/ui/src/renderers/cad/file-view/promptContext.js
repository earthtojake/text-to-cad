import { createPromptContext, referencePart, textPart } from '@hardcore/core/prompt';

/** Assemble a snapshot once, before asynchronous image encoding or host routing. */
export function createCadPromptContext({ resource, references = [], text = '', capture, operationId }) {
  const parts = references.map((reference, index) => referencePart({
    resource: { ...resource },
    target: reference.selector ? { kind: 'cad-selector', selectors: reference.selector.split(',') } : { kind: 'whole-resource' },
    ...(reference.label ? { label: reference.label } : {}),
  }, `reference-${index}`));
  if (text) parts.push(textPart(text));
  if (capture) {
    if (!parts.some(part => part.kind === 'reference')) parts.unshift(referencePart({ resource: { ...resource }, target: { kind: 'whole-resource' } }, 'source'));
    parts.push({ id: 'capture', kind: 'attachment', name: `${resource.path.split('/').pop().replace(/\.[^.]+$/, '')}-view.png`, mimeType: 'image/png', content: capture, about: parts.filter(part => part.kind === 'reference').map(part => part.id) });
  }
  return createPromptContext(parts, operationId);
}

export function promptDeliveryMessage(result) {
  if (result.status === 'added') return 'Added to prompt';
  if (result.status === 'copied') return 'Copied for prompt';
  if (result.status === 'cancelled') return '';
  return result.message || (result.status === 'deferred' ? 'Choose a prompt destination' : 'Could not deliver prompt context');
}
