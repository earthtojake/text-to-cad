import { buildSelectionCopyPayload, canonicalCadRefCopyText, withFileRefPrefix } from './referenceSelection.js';

// Preview IDs must resolve against the current document before becoming a
// prompt reference. Never send a partial group or invent a source-feature ID.
export function designFeaturePromptText(selection, { referenceMap, parts = [], entry } = {}) {
  const faceIds = [...new Set(selection?.faceIds || [])];
  const partIds = [...new Set(selection?.partIds || [])];
  if (!entry || !faceIds.length && !partIds.length) return '';
  const references = faceIds.map(id => referenceMap?.get(id));
  const selectedParts = partIds.map(id => parts.find(part => part.id === id));
  if (references.some(reference => reference?.selectorType !== 'face' || !canonicalCadRefCopyText(reference.copyText)) || selectedParts.some(part => !part)) return '';
  const payload = buildSelectionCopyPayload({ references, parts: selectedParts, entry });
  if (payload.missingPartNames.length) return '';
  return payload.lines.map(line => withFileRefPrefix(canonicalCadRefCopyText(line), entry.fileRefPrefix)).filter(Boolean).join('\n');
}
