/**
 * The tree paths the selection reveals, for presentation only: a selected part or subassembly
 * at its own row (the exact row before an assembly holding it), and a picked face or edge at
 * the row of the part it belongs to.
 */
export function modelingSelectionPaths(tree, selectedReferences, selectedPartIds = []) {
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
    const path = paths.find(p => p.at(-1).selectionId === id) || [...paths].reverse().find(p => p.at(-1).leafPartIds?.includes(id));
    if (path) matches.push(path);
  }
  for (const ref of selectedReferences) {
    const part = paths.find(p => p.at(-1).kind === 'part' && p.at(-1).selectionId === ref.occurrenceId);
    if (part) matches.push(part);
  }
  return [...new Map(matches.map(path => [path.at(-1).id, path])).values()];
}
