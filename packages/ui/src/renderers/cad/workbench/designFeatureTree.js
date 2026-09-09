import { designFeatureSelection } from './designFeatureSelection.js';

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
