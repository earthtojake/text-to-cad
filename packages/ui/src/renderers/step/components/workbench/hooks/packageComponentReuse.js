export function matchingDisplayedPackageContext(displayed, meshState, file) {
  const expectedFile = String(file || "");
  if (!displayed?.complete || !meshState?.assemblyInteractionReady) return null;
  if (String(displayed.file || "") !== expectedFile || String(meshState.file || "") !== expectedFile) {
    return null;
  }
  return String(displayed.meshHash || "") === String(meshState.meshHash || "")
    ? displayed
    : null;
}

// Keep decoded geometry that is still visible alive across an atomic revision swap: a component
// whose part is one already drawn (its key binds the exact geometry and producer) keeps that part's
// mesh, and the row it was drawn from, whatever its id in the new tree -- a part is named by its
// geometry (STORE.md 2), so a build's preview and the file it saves name one body by different ids
// and one part, and nothing is read twice. Keyed by the new tree's component id.
export function retainedComponentsForRevision({
  previous,
  descriptor,
  meshUrl,
} = {}) {
  if (!previous?.descriptor || !previous?.meshUrl || !descriptor || !meshUrl) {
    return {};
  }
  const byPart = new Map();
  for (const [cid, row] of Object.entries(previous.componentIdentityByCid || {})) {
    const meshData = previous.componentMeshDataByCid?.[cid];
    if (row?.part && meshData && !byPart.has(row.part)) byPart.set(row.part, { meshData, row });
  }
  const retained = {};
  for (const [cid, component] of Object.entries(descriptor.components || {})) {
    const kept = component?.part ? byPart.get(component.part) : null;
    if (kept) retained[cid] = kept;
  }
  return retained;
}
