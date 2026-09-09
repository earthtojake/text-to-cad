export const SELECTION_FILTERS = [
  { id: 'all', label: 'All', detail: 'Parts, faces and edges' },
  { id: 'parts', label: 'Parts', detail: 'Whole components' },
  { id: 'faces', label: 'Faces', detail: 'Faces only' },
  { id: 'edges', label: 'Edges', detail: 'Edges only' },
  { id: 'groups', label: 'Feature groups', detail: 'Recognized hole and slot walls' },
];

export function filterSelectionReferences(references, filter, groups = []) {
  if (filter === 'parts') return [];
  if (filter === 'faces') return references.filter(r => r.selectorType === 'face');
  if (filter === 'edges') return references.filter(r => r.selectorType === 'edge');
  if (filter === 'groups') {
    const ids = new Set(groups.flatMap(group => group.faceIds));
    return references.filter(r => r.selectorType === 'face' && ids.has(r.id));
  }
  return references;
}

export function toggleFaceGroupSelection(current, faceIds, additive = false) {
  if (!additive) return [...faceIds];
  const next = new Set(current);
  const remove = faceIds.every(id => next.has(id));
  for (const id of faceIds) {
    if (remove) next.delete(id);
    else next.add(id);
  }
  return [...next];
}
