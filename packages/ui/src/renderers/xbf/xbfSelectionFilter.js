// What an engine document's Select picks, as the STEP renderer's did: the kinds of the
// model's geometry its filter ticks, how they are picked as one mode, how a face or edge pick
// grows, and the model tree's shape under each mode.

/**
 * The kinds of the model's geometry Select picks, each a checkbox of its selection filter
 * (`kit/tools/select/selectFilter.js`), each on its own. `assemblyOnly`: a single part is one
 * thing, so a part file's filter offers no Parts.
 */
export const SELECT_GEOMETRY = Object.freeze([
  { id: 'parts', label: 'Parts', assemblyOnly: true },
  { id: 'faces', label: 'Faces' },
  { id: 'edges', label: 'Edges' },
]);

/**
 * How the geometry a filter ticks is picked, as one mode: "all" — Parts with Faces or Edges — a
 * press takes the face or edge it lands on where the part is open, the part elsewhere; "parts",
 * the part alone; "topology" — Faces and Edges — "faces" and "edges" that topology alone; "none",
 * no geometry.
 */
export function selectGeometryMode(filter) {
  const parts = filter.includes('parts'), faces = filter.includes('faces'), edges = filter.includes('edges');
  if (parts) return faces || edges ? 'all' : 'parts';
  if (faces && edges) return 'topology';
  return faces ? 'faces' : edges ? 'edges' : 'none';
}

/** The model tree's shape under a mode: the person's own ("all"), or held by the filter. */
export const treeShape = mode => (mode === 'none' ? 'all' : mode === 'topology' ? 'faces' : mode);

/**
 * How a face or edge pick grows, independent of the filter and of each other: Group faces takes
 * the smoothly joined faces with a picked face, Group edges the connected edges with a picked
 * edge. Each applies while its kind of topology is ticked.
 */
export const CONNECTED_SELECTION = [
  { id: 'edgeChain', label: 'Group edges', kind: 'edges' },
  { id: 'tangentFaces', label: 'Group faces', kind: 'faces' },
];
export const NO_CONNECTED_SELECTION = Object.freeze({ edgeChain: false, tangentFaces: false });

/** Whether a connected-selection option does anything under `filter` (its kind ticked). */
export function connectedSelectionApplies(id, filter) {
  const kind = CONNECTED_SELECTION.find(option => option.id === id)?.kind;
  return Boolean(kind) && filter.includes(kind);
}

/**
 * The selection after a pick of `ids` (one element, or a grown group): replaced, or with
 * `additive` the group added -- or taken away where every one of it is selected already. A plain
 * pick of the one thing selected already lets it go, as every selecting view does.
 */
export function nextSelectionIds(current, ids, additive = false) {
  if (!ids.length) return additive ? current : [];
  if (additive) {
    const next = new Set(current);
    const remove = ids.every(id => next.has(id));
    for (const id of ids) { if (remove) next.delete(id); else next.add(id); }
    return [...next];
  }
  if (ids.length === 1 && current.length === 1 && current[0] === ids[0]) return [];
  return [...ids];
}
