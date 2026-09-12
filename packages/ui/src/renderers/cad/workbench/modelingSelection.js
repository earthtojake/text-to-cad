const OPERATIONS = new Set(['boss','pocket','hole','extrude','loft','cut','revolve','round']);
const allEdges = node => [...(node.edges || []), ...(node.children || []).flatMap(allEdges)];

/** Match selection for presentation only. Never replace a picked edge/face with a feature. */
export function modelingSelectionPaths(tree, selectedReferences, selectedPartIds = [], descriptor, results = {}) {
  const paths = [];
  const visit = (nodes, parents = []) => {
    for (const node of nodes) {
      const path = [...parents, node];
      paths.push(path);
      visit(node.children || [], path);
    }
  };
  visit(tree);
  const matches = [];
  for (const id of selectedPartIds) {
    const path = paths.find(p => p.at(-1).selectionId === id || p.at(-1).occurrenceId === id) || [...paths].reverse().find(p => p.at(-1).leafPartIds?.includes(id));
    if (path) matches.push(path);
  }
  for (const ref of selectedReferences) {
    const part = paths.find(p => ['part','body'].includes(p.at(-1).kind) && (p.at(-1).occurrenceId === ref.occurrenceId || p.at(-1).selectionId === ref.occurrenceId)) || (descriptor?.occurrences.length === 1 ? paths.find(p => p.at(-1).selectionId === '__step_model__') : null);
    const ordinal = Number(ref.normalizedSelector?.match(/\.[fe](\d+)$/)?.[1]);
    const operations = paths.filter(p => p.at(-1).occurrenceId === ref.occurrenceId && OPERATIONS.has(p.at(-1).kind));
    let candidates = [];
    if (ref.selectorType === 'face') candidates = operations.filter(p => p.at(-1).faces?.includes(ordinal));
    if (ref.selectorType === 'edge') {
      candidates = operations.filter(p => allEdges(p.at(-1)).includes(ordinal));
      if (!candidates.length) {
        const component = descriptor?.occurrences.find(o => o.id === ref.occurrenceId)?.component;
        const faces = results[component]?.edgeFaces?.[ordinal] || [];
        if (faces.length) candidates = operations.filter(p => faces.every(face => p.at(-1).faces?.includes(face)));
      }
    }
    // A shared boundary may legitimately belong to several features. Show its part instead.
    if (candidates.length === 1) matches.push(candidates[0]);
    else if (part) matches.push(part);
  }
  return [...new Map(matches.map(path => [path.at(-1).id, path])).values()];
}
