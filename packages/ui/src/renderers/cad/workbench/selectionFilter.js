export const SELECTION_FILTERS = [
  { id: 'all', label: 'All', detail: 'Parts, faces and edges' },
  { id: 'parts', label: 'Parts', detail: 'Whole components' },
  { id: 'faces', label: 'Faces', detail: 'Faces only' },
  { id: 'edges', label: 'Edges', detail: 'Edges only' },
  { id: 'edge-chain', label: 'Edge chain', detail: 'Connected edges; stops at ambiguous branches', section: 'Connected selection' },
  { id: 'tangent-faces', label: 'Tangent faces', detail: 'Smoothly joined faces; stops at sharp edges', section: 'Connected selection' },
];

export const MEASURE_SELECTION_FILTERS = [
  { id: 'all', label: 'Any geometry', detail: 'Points, edges and faces' },
  { id: 'points', label: 'Points', detail: 'Point-to-point distance' },
  { id: 'edges', label: 'Edges', detail: 'Snap to edges only' },
  { id: 'faces', label: 'Faces', detail: 'Snap to faces only' },
];

export function filterSelectionReferences(references, filter) {
  if (filter === 'parts') return [];
  if (filter === 'faces' || filter === 'tangent-faces') return references.filter(r => r.selectorType === 'face');
  if (filter === 'edges' || filter === 'edge-chain') return references.filter(r => r.selectorType === 'edge');
  return references;
}

export function toggleReferenceGroupSelection(current, referenceIds, additive = false) {
  if (!additive) return [...referenceIds];
  const next = new Set(current);
  const remove = referenceIds.every(id => next.has(id));
  for (const id of referenceIds) {
    if (remove) next.delete(id);
    else next.add(id);
  }
  return [...next];
}

export function connectedReferenceIds(graph, seed) {
  if (!graph.has(seed)) return [];
  const selected = new Set([seed]);
  const pending = [seed];
  while (pending.length) {
    for (const id of graph.get(pending.pop()) || []) {
      if (selected.has(id)) continue;
      selected.add(id);
      pending.push(id);
    }
  }
  return [...selected];
}
