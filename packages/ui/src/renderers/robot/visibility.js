const EMPTY = Object.freeze([]);

/** A link controls its own visuals, never the joints or links below it; a partly hidden one is not hidden. */
export function robotVisibilityState(partIds = EMPTY, hiddenIds = new Set()) {
  return { ids: partIds, allHidden: partIds.length > 0 && partIds.every(id => hiddenIds.has(id)) };
}

/** Keep only loaded part identities; return a new array for every visibility edit. */
export function changeRobotVisibility(current, partIds, visible, validIds) {
  const changed = new Set((Array.isArray(partIds) ? partIds : EMPTY)
    .filter(id => typeof id === "string" && validIds.has(id)));
  const retained = current.filter(id => validIds.has(id) && (!visible || !changed.has(id)));
  return visible ? retained : [...new Set([...retained, ...changed])];
}
