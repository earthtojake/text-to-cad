const empty = () => ({ faceIds: [], partIds: [] });
const near = (a, b, tolerance) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) <= tolerance;
function sameBounds(a, b, tolerance = 0.002) {
  return ['min', 'max'].every(key => a?.[key]?.length === 3 && b?.[key]?.length === 3 && a[key].every((n, i) => near(n, b[key][i], tolerance)));
}
// OCCT's conservative BREP box can contain unused surface control points;
// a trimmed display mesh therefore need not reach all six limits.
function containsBounds(outer, inner) {
  return ['min', 'max'].every(key => outer?.[key]?.length === 3 && inner?.[key]?.length === 3) &&
    outer.min.every((n, i) => Number.isFinite(n) && Number.isFinite(inner.min[i]) && n <= inner.min[i] + 0.002) &&
    outer.max.every((n, i) => Number.isFinite(n) && Number.isFinite(inner.max[i]) && n >= inner.max[i] - 0.002);
}
function sameFace(a, b) {
  return sameBounds(a?.bbox, b?.bbox) && near(a?.area, b?.area, Math.max(0.0001, a?.area * 1e-5)) && a?.center?.length === 3 && b?.center?.length === 3 && a.center.every((n, i) => near(n, b.center[i], 0.0001));
}
function uniqueMatches(descriptors, candidates, matches) {
  if (!Array.isArray(descriptors) || !Array.isArray(candidates) || !descriptors.length || descriptors.length > 250 || descriptors.length !== candidates.length) return null;
  const result = descriptors.map(item => candidates.filter(candidate => matches(item, candidate)));
  if (result.some(items => items.length !== 1)) return null;
  const ids = result.map(items => items[0].id);
  return new Set(ids).size === ids.length ? ids : null;
}

// Source/artifact hashes are checked by the backend. Also require a complete,
// unique match against the currently loaded geometry: never trust face order.
export function resolveDesignFeatureLinks(links, references = [], parts = []) {
  if (links?.schema !== 1) return null;
  if (links.parts) {
    const ids = uniqueMatches(links.parts, parts, (a, b) => a.name === b.name && containsBounds(a.bbox, b.bounds));
    return ids ? { parts: ids, faces: [], lines: {}, partLines: links.partLines || {} } : null;
  }
  const faces = references.filter(reference => reference.selectorType === 'face');
  const ids = uniqueMatches(links.faces, faces, (a, b) => sameFace(a, b.pickData));
  return ids ? { faces: ids, parts: [], lines: links.lines || {}, partLines: {} } : null;
}

export function designFeatureSelection(node, resolved, inheritedLine = null) {
  if (!resolved || !node || node.type === 'parameters') return empty();
  if (node.type === 'model' || node.type === 'imported') return {faceIds: resolved.faces, partIds: resolved.parts};
  const lines = new Set();
  const collect = (item, parentLine) => {
    const line = item.type === 'sketch' ? parentLine : item.line;
    if (line) lines.add(String(line));
    for (const child of item.children || []) collect(child, line);
  };
  collect(node, inheritedLine);
  return {
    faceIds: [...new Set([...lines].flatMap(line => (resolved.lines[line] || []).map(index => resolved.faces[index]).filter(Boolean)))],
    partIds: [...new Set([...lines].flatMap(line => (resolved.partLines[line] || []).map(index => resolved.parts[index]).filter(Boolean)))],
  };
}
