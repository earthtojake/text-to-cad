import { buildSelectionCopyPayload, canonicalCadRefCopyText, withFileRefPrefix } from './referenceSelection.js';

// Source context remains useful when a final face link does not exist. Keep it
// plain text: source operation IDs are never fabricated geometry references.
export function designFeatureContextText(context, { includeModel = true } = {}) {
  if (!context?.file || !context?.label) return '';
  const quote = value => /[\s#"\\]/.test(value) ? JSON.stringify(value) : value;
  const details = [];
  if (context.inspection?.kind === 'axis') {
    const axis = context.inspection.value, value = context.measurements?.size?.[axis];
    details.push(`${['X', 'Y', 'Z'][axis]} extent${Number.isFinite(value) ? ` = ${Number(value.toFixed(5))} mm` : ''}`);
  }
  if (context.inspection?.kind === 'radius') details.push(`radius = ${context.inspection.value} mm`);
  // A clicked parameter may need its expression; entire parameter/child lists
  // and unrelated measured facts belong in inspection, not the user's draft.
  if (context.parameters?.length === 1 && !context.inspection) {
    const param = context.parameters[0];
    const value = param.value == null ? param.expression : String(param.value);
    if (value != null && String(value).length <= 80) details.push(`${param.name} = ${value}`);
  }
  if (!context.source && !includeModel && !details.length) return '';
  const location = [includeModel ? quote(context.file) : '', context.source ? `${quote(context.source)}${context.line ? `:${context.line}` : ''}` : ''].filter(Boolean).join(' · ');
  return [context.label, ...details, location].filter(Boolean).join(' · ');
}

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
