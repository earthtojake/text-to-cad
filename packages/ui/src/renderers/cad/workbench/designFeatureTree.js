import { designFeatureSelection } from './designFeatureSelection.js';

export const designFeatureTitle = value => String(value || '').replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2');
export const designFeatureLabel = node => node.type === 'sketch' && !/^Sketch\b/i.test(node.label) ? `Sketch · ${node.label === 'RectangleRounded' ? 'Rounded rectangle' : designFeatureTitle(node.label)}` : designFeatureTitle(node.label);
export const designFeatureValue = value => typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 5 }) : String(value);


// Expand actual topology only on demand. Large imports must not instantiate a
// face row for every part before the person opens that part's Faces group.
export function withDesignFaceRows(nodes, resolved, references, expanded, parentLine = null) {
  return nodes.map(node => {
    const children = expanded.has(node.id) ? withDesignFaceRows(node.children || [], resolved, references, expanded, node.line || parentLine) : node.children || [];
    if (['model', 'group', 'parameters', 'parameter', 'sketch'].includes(node.type)) return { ...node, children };
    const selection = designFeatureSelection(node, resolved, parentLine);
    const ids = new Set(selection.faceIds), parts = new Set(selection.partIds);
    const faces = references.filter(ref => ref.selectorType === 'face' && (ids.has(ref.id) || parts.has(ref.partId)));
    if (!faces.length) return { ...node, children };
    const groupId = `faces:${node.id}`;
    const group = { id: groupId, type: 'geometry-faces', label: `Associated faces (${faces.length})`, faceIds: faces.map(ref => ref.id), parameters: [],
      children: expanded.has(groupId) ? faces.map(ref => ({ id: `face:${node.id}:${ref.id}`, type: 'geometry-face',
        label: `${ref.label || ref.displaySelector || 'Face'}${ref.pickData?.surfaceType ? ` · ${ref.pickData.surfaceType}` : ''}`,
        faceIds: [ref.id], parameters: [], children: [] })) : [], hasFaceChildren: true };
    return { ...node, children: [...children, group] };
  });
}

// Keep each source operation exactly once. Repeats or operations spanning
// multiple parts stay at assembly level instead of inventing per-part history.
export function groupDesignFeatures(features, resolved, parts) {
  if (!resolved?.parts.length || !features.length) return features;
  const groups = new Map(parts.map(part => [part.id, {
    id: `part:${part.id}`, label: part.name || 'Part', type: 'part',
    partIds: [part.id], parameters: [], children: [],
  }]));
  const shared = [];
  for (const feature of features) {
    const { partIds } = designFeatureSelection(feature, resolved);
    const group = partIds.length === 1 && groups.get(partIds[0]);
    if (group) group.children.push(feature);
    else shared.push(feature);
  }
  return [
    { id: 'parts', label: 'Parts', type: 'group', parameters: [], children: [...groups.values()] },
    ...(shared.length ? [{ id: 'assembly-operations', label: 'Assembly operations', type: 'group', parameters: [], children: shared }] : []),
  ];
}

export function sourceParameterNode(parameter, features) {
  const lines = new Set();
  const visit = (node, parentLine) => {
    const line = node.type === 'sketch' ? parentLine : node.line;
    const names = [...(node.sourceParameters || []), ...(node.parameters || []).flatMap(item => item.sourceParameters || [])];
    if (names.includes(parameter.name)) {
      const collect = (item, inherited) => {
        const current = item.type === 'sketch' ? inherited : item.line;
        if (current) lines.add(current);
        (item.children || []).forEach(child => collect(child, current));
      };
      collect(node, parentLine);
    }
    (node.children || []).forEach(child => visit(child, line));
  };
  features.forEach(node => visit(node, null));
  return { id: `parameter:${parameter.name}`, label: parameter.name, type: 'parameter',
    parameters: [parameter], sourceLines: [...lines], children: [] };
}
