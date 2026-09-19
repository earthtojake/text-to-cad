import { buildSelectionCopyPayload, canonicalCadRefCopyText, withFileRefPrefix } from './referenceSelection.js';

// Optional measured values accompany canonical STEP references, without source context.
export function stepGeometryContextText(context, { includeModel = true } = {}) {
  if (!context?.file || !context?.label) return '';
  const quote = value => /[\s#"\\]/.test(value) ? JSON.stringify(value) : value;
  const details = [];
  if (context.inspection?.kind === 'axis') {
    const axis = context.inspection.value, value = context.measurements?.size?.[axis];
    details.push(`${['X', 'Y', 'Z'][axis]} extent${Number.isFinite(value) ? ` = ${Number(value.toFixed(5))} mm` : ''}`);
  }
  if (context.inspection?.kind === 'radius') details.push(`radius = ${context.inspection.value} mm`);
  if (!includeModel && !details.length) return '';
  return [context.label, ...details, includeModel ? quote(context.file) : ''].filter(Boolean).join(' · ');
}

// Preview IDs must resolve against the current document before becoming a
// prompt reference. Never send a partial group or invent a source-feature ID.
export function stepGeometryPromptText(selection, { referenceMap, parts = [], entry } = {}) {
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
