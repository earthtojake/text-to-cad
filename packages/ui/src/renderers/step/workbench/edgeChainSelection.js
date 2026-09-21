// Endpoint matching is scoped to the same solid/occurrence and a shared face.
// At a branch, continue only along one reciprocal, smoothly aligned edge.
export function buildEdgeChainGraph(references) {
  const edges = [...new Map(references.filter(ref => ref.selectorType === 'edge').map(ref => [ref.id, ref])).values()];
  const graph = new Map(edges.map(edge => [edge.id, new Set()]));
  const buckets = new Map(), ends = [];
  const tolerance = 1e-5;
  const key = (scope, cell) => JSON.stringify([scope, ...cell]);
  for (const edge of edges) {
    const endpoints = edge.pickData?.chainEndpoints;
    if (endpoints?.length !== 2) continue;
    const scope = [edge.partId || '', edge.occurrenceId || '', edge.shapeId || ''];
    for (const endpoint of endpoints) {
      if (![endpoint.point, endpoint.direction].every(v => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite))) continue;
      const end = { ...endpoint, edge, scope, cell: endpoint.point.map(v => Math.floor(v / tolerance)) };
      const bucket = key(scope, end.cell);
      if (!buckets.has(bucket)) buckets.set(bucket, []);
      buckets.get(bucket).push(end); ends.push(end);
    }
  }
  const choices = new Map();
  for (const end of ends) {
    const candidates = [];
    for (let x = -1; x <= 1; x++) for (let y = -1; y <= 1; y++) for (let z = -1; z <= 1; z++) {
      for (const other of buckets.get(key(end.scope, [end.cell[0]+x,end.cell[1]+y,end.cell[2]+z])) || []) {
        if (other.edge.id === end.edge.id || Math.hypot(...end.point.map((v,i) => v-other.point[i])) > tolerance) continue;
        if (!end.edge.pickData.adjacentSelectors?.some(face => other.edge.pickData.adjacentSelectors?.includes(face))) continue;
        candidates.push(other);
      }
    }
    const aligned = candidates.length > 1 ? candidates.filter(other => end.direction.reduce((sum,v,i) => sum+v*other.direction[i],0) < -Math.cos(Math.PI/60)) : candidates;
    if (aligned.length === 1) choices.set(end, aligned[0]);
  }
  for (const [end, other] of choices) {
    if (choices.get(other) !== end) continue;
    graph.get(end.edge.id).add(other.edge.id);
    graph.get(other.edge.id).add(end.edge.id);
  }
  return graph;
}
