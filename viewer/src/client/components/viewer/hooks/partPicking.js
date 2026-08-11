// Pick-candidate filtering and resolving the occurrence/part id a raycast
// intersection points at. A display record's mesh carries its id as
// userData.partId. Kept as a standalone pure module so it unit-tests in Node
// without the hook's Vite-resolved (extension-less) imports.

// Whether a display record's mesh belongs in the part-pick raycast candidate set:
// visible, and not filtered out by the active hidden/focus sets.
export function shouldRaycastRecordForPick(record, { focusIds, hiddenIds } = {}) {
  if (!record?.mesh?.visible) {
    return false;
  }
  const partId = String(record?.partId || "").trim();
  if (hiddenIds instanceof Set && hiddenIds.has(partId)) {
    return false;
  }
  if (focusIds instanceof Set && focusIds.size && !focusIds.has(partId)) {
    return false;
  }
  return true;
}

export function partIdFromIntersection(intersection) {
  return intersection?.object?.userData?.partId || null;
}
