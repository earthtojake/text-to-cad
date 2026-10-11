// An edge's chain is cadgen's to decide (the selector table's `chain`: edges that continue one
// another at a shared vertex of one solid, from the exact BREP). Edges of one placed component
// with the same chain id are one chain; a chain never crosses a part, an occurrence or a solid,
// and an edge without a chain (a degenerate one) stands alone.
export function buildEdgeChainGraph(references) {
  const edges = [...new Map(references.filter(ref => ref.selectorType === 'edge').map(ref => [ref.id, ref])).values()];
  const graph = new Map(edges.map(edge => [edge.id, new Set()]));
  const chains = new Map();
  for (const edge of edges) {
    const chain = edge.pickData?.chain;
    if (!Number.isInteger(chain)) continue;
    const key = JSON.stringify([edge.partId || '', edge.occurrenceId || '', edge.shapeId || '', chain]);
    if (!chains.has(key)) chains.set(key, []);
    chains.get(key).push(edge);
  }
  for (const members of chains.values()) {
    for (let index = 1; index < members.length; index += 1) {
      graph.get(members[0].id).add(members[index].id);
      graph.get(members[index].id).add(members[0].id);
    }
  }
  return graph;
}
