/**
 * The Select tool's modes: exclusive, each with its own icon on the strip
 * (`components/workbench/SelectionFilterMenu.jsx`). `assemblyOnly`: a single part is one
 * thing, so picking parts in it would pick nothing but the whole.
 */
export const SELECT_MODES = [
  { id: 'all', label: 'All' },
  { id: 'parts', label: 'Parts', assemblyOnly: true },
  { id: 'faces', label: 'Faces' },
  { id: 'edges', label: 'Edges' },
];

/**
 * How a face or edge pick grows, independent of the mode and of each other: Tangent faces
 * takes the smoothly joined faces with a picked face, Edge chain the connected edges with a
 * picked edge. Each applies wherever its kind of topology is picked — All, and its own mode —
 * and has no effect elsewhere.
 */
export const CONNECTED_SELECTION = [
  { id: 'edgeChain', label: 'Edge chain', appliesIn: ['all', 'edges'] },
  { id: 'tangentFaces', label: 'Tangent faces', appliesIn: ['all', 'faces'] },
];
export const NO_CONNECTED_SELECTION = Object.freeze({ edgeChain: false, tangentFaces: false });

/** Whether a connected-selection option does anything under `mode`. */
export function connectedSelectionApplies(id, mode) {
  return CONNECTED_SELECTION.find(option => option.id === id)?.appliesIn.includes(mode) === true;
}

export const MEASURE_SELECTION_FILTERS = [
  { id: 'all', label: 'Any geometry', detail: 'Points, edges and faces' },
  { id: 'points', label: 'Points', detail: 'Point-to-point distance' },
  { id: 'edges', label: 'Edges', detail: 'Snap to edges only' },
  { id: 'faces', label: 'Faces', detail: 'Snap to faces only' },
];

/** What a viewport press can pick under a Select mode (or Measure's snapping). */
export function filterSelectionReferences(references, mode) {
  if (mode === 'parts') return [];
  if (mode === 'faces') return references.filter(r => r.selectorType === 'face');
  if (mode === 'edges') return references.filter(r => r.selectorType === 'edge');
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
