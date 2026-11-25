// What an engine document's Select picks, as the STEP renderer's did: the kinds of the
// model's geometry its Filter ticks, how any mix of them is picked as one mode, and the model
// tree's shape under each mode.

/**
 * The kinds of the model's geometry Select picks, each a box of its Filter
 * (`kit/tools/select/selectFilter.js`), each ticked on its own. `assemblyOnly`: a single part is one
 * thing, so a part file's filter offers no Parts.
 */
export const SELECT_GEOMETRY = Object.freeze([
  { id: 'parts', label: 'Parts', key: 'pick.parts', assemblyOnly: true },
  { id: 'faces', label: 'Faces', key: 'pick.faces' },
  { id: 'edges', label: 'Edges', key: 'pick.edges' },
]);

/**
 * How the geometry a filter ticks is picked, as one mode: "all" — Parts with Faces, Edges or both — a
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
 * What Select's filter (any of its boxes ticked) picks of the model: its geometry mode
 * (`selectGeometryMode`), the tree's shape under it (`treeShape`), and the booleans a click's pick and a
 * box's take (`options`: the scene's `pickElement` and `pickBox`, `faces`, `edges`, `parts`). A part
 * file has no Parts box: its whole part is what a press reaching no face or edge takes, whatever the
 * filter says of Parts, so it is read without it. Position, the annotations and the measurements are
 * no geometry: they are read off the filter where they are drawn.
 *
 * @param {readonly string[]} filter
 * @param {{ assembly: boolean }} options
 */
export function xbfGeometryPicks(filter, { assembly }) {
  const geometry = assembly ? filter : filter.filter(id => id !== 'parts');
  const mode = selectGeometryMode(geometry);
  return { mode, shape: treeShape(mode),
    options: { faces: geometry.includes('faces'), edges: geometry.includes('edges'), parts: assembly && geometry.includes('parts') } };
}

/**
 * A face's or an edge's tangent chain, what the view's menu's Select tangent faces and Select tangent
 * edges take: the faces joined across tangent edges, the edges that continue one another at a shared
 * vertex, as its part's groups say (`@cad/core`'s `fetchXbfPartGroups`: each face's and each edge's
 * group by ordinal); itself alone where they say nothing of it.
 *
 * @param {{ id: string, kind: "face" | "edge", instance: number, ordinal: number }} element
 * @param {{ faces?: Record<string, number>, edges?: Record<string, number> } | null} groups
 */
export function tangentChain(element, groups) {
  const table = groups?.[element.kind === 'face' ? 'faces' : 'edges'];
  const group = table?.[String(element.ordinal)];
  if (group == null) return [element.id];
  return Object.entries(table).filter(([, value]) => value === group).map(([ordinal]) => `i${element.instance}/${element.kind}/${ordinal}`);
}

/** The selection with tangent `chains` added to it: what was selected, in its order, then each chain's own. */
export const withTangentChains = (selected, chains) => [...new Set([...selected, ...chains.flat()])];

/**
 * The selection after a pick of `ids` (one element, a tangent chain, a folded row's parts): replaced, or
 * with `additive` the group added -- or taken away where every one of it is selected already. A plain
 * pick of the one thing selected already, exactly, lets it go, as every selecting view does: one element,
 * or the group it is (pressed again, a folded row's parts are let go of, as a part's row's part is).
 */
export function nextSelectionIds(current, ids, additive = false) {
  if (!ids.length) return additive ? current : [];
  if (additive) {
    const next = new Set(current);
    const remove = ids.every(id => next.has(id));
    for (const id of ids) { if (remove) next.delete(id); else next.add(id); }
    return [...next];
  }
  const picked = new Set(ids);
  if (current.length === picked.size && current.every(id => picked.has(id))) return [];
  return [...ids];
}
