// Use the topology's measured edge classification, never proximity or matching
// face normals: a curved face's normal varies along its boundary.
export function buildTangentFaceGraph(references) {
  const unique = new Map(references.map(reference => [reference.id, reference]));
  const faces = new Map();
  const graph = new Map();
  for (const reference of unique.values()) {
    if (reference.selectorType !== 'face') continue;
    if (reference.displaySelector) {
      faces.set(reference.displaySelector, faces.has(reference.displaySelector) ? null : reference);
    }
    graph.set(reference.id, new Set());
  }
  for (const edge of unique.values()) {
    if (edge.selectorType !== 'edge' || edge.pickData?.visibilityClass !== 'tangent') continue;
    const adjacent = [...new Set(edge.pickData.adjacentSelectors || [])];
    if (adjacent.length !== 2) continue;
    const [a, b] = adjacent.map(selector => faces.get(selector));
    if (!a || !b || a.occurrenceId !== b.occurrenceId || a.shapeId !== b.shapeId) continue;
    graph.get(a.id).add(b.id);
    graph.get(b.id).add(a.id);
  }
  return graph;
}
