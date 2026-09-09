import { buildSelectionCopyPayload, canonicalCadRefCopyText, withFileRefPrefix } from './referenceSelection.js';

// Source context remains useful when a final face link does not exist. Keep it
// plain text: source operation IDs are never fabricated geometry references.
export function designFeatureContextText(context, { includeModel = true } = {}) {
  if (!context?.file || !context?.label) return '';
  const lines = [`Feature context: ${context.label}`];
  if (includeModel) lines.push(`Model: ${/[\s#"\\]/.test(context.file) ? JSON.stringify(context.file) : context.file}`);
  if (context.source) lines.push(`Source: ${context.source}${context.line ? ` (line ${context.line})` : ''}`);
  if (context.parameters?.length) lines.push(`Source inputs: ${context.parameters.map(param => `${param.name} = ${param.value == null ? param.expression : String(param.value)}`).join('; ')}`);
  if (context.children?.length) lines.push(`Contains: ${context.children.join('; ')}`);
  const values = context.measurements;
  const format = value => Number(value.toFixed(5));
  if (values?.size) lines.push(`Measured result extents (X × Y × Z): ${values.size.map(format).join(' × ')} mm`);
  if (values?.area != null) lines.push(`Measured face area: ${format(values.area)} mm²`);
  if (values?.radii?.length) lines.push(`Measured surface radii: ${values.radii.map(format).join(', ')} mm`);
  if (context.inspection?.kind === 'axis') lines.push(`Selected measurement: ${['X', 'Y', 'Z'][context.inspection.value]} extent`);
  if (context.inspection?.kind === 'radius') lines.push(`Selected surface radius: ${context.inspection.value} mm`);
  return lines.join('\n');
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
