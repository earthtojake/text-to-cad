/** Numerical sketches only: no original source, topology handles or borrowed faces. */
export function reconstructionRecipe(index, tree) {
  if (tree.length !== 1 || !tree[0].complete) return null;
  if (tree[0].recipe) return tree[0].recipe;
  const features = tree[0].children, first = features[0], steps = [];
  if (!first || !['extrude', 'revolve'].includes(first.kind)) return null;
  let previous = null;
  for (const [i, feature] of features.entries()) {
    if (i > 0 && feature.kind !== 'cut') return null;
    const sketch = `sketch-${i + 1}`, id = `operation-${i + 1}`;
    let profile;
    if (feature.kind === 'revolve') {
      if (!feature.reconstruction) return null;
      profile = { kind: 'axial', ...feature.reconstruction };
    } else {
      const edges = feature.children?.[0]?.edges;
      const face = index.faces.find(f => f.ord === first.reconstruction?.face);
      const loop = face?.loops?.find(l => edges && l.length === edges.length && l.every(e => edges.includes(e.edgeOrd)));
      if (!loop || !first.reconstruction?.direction) return null;
      const uses = loop.map(use => ({ curve: index.edges.find(e => e.ord === use.edgeOrd)?.curve, reversed: use.reversed }));
      if (uses.some(use => !['line', 'circle'].includes(use.curve?.kind))) return null;
      profile = { kind: 'boundary', edges: uses };
    }
    steps.push({ id: sketch, kind: 'sketch', label: `Sketch ${i + 1}`, dependsOn: [], profile });
    steps.push({ id, kind: feature.kind, label: feature.label, sketch,
      dependsOn: [...(previous ? [previous] : []), sketch],
      ...(previous ? { input: previous } : {}), measurements: feature.measurements || [],
      ...(feature.kind === 'revolve' ? { axis: first.reconstruction.axis, origin: first.reconstruction.origin, angle: 2 * Math.PI } : { direction: first.reconstruction.direction }) });
    previous = id;
  }
  return steps.length <= 128 ? { schema: 1, units: 'mm', steps, output: previous } : null;
}
