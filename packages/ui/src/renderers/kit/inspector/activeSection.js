// Which Inspector tab is open. Section ids are opaque strings: the caller
// decides which exist and in what order; these helpers only reconcile a stored
// selection against the ids that are rendered now.

function normalizeString(value) {
  return String(value || "").trim();
}

// A stored id that is no longer rendered simply is not open: the sheet lands on
// the first tab. There is no table of retired names to keep alive.
export function normalizeFileSheetSectionId(value) {
  return normalizeString(value);
}

export function normalizeSectionIds(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return [...new Set(value.map(normalizeFileSheetSectionId).filter(Boolean))];
}

export function normalizeFileSheetOpenSectionIds(sectionIds, renderedSectionIds) {
  const rendered = new Set(normalizeSectionIds(renderedSectionIds));
  if (!rendered.size) {
    return [];
  }
  const open = (Array.isArray(sectionIds) ? sectionIds : []).map(normalizeFileSheetSectionId);
  // Only one section is active: the last selected one that is still rendered.
  return open.filter(id => rendered.has(id)).slice(-1);
}

// The last selected available section wins, and a missing/unsupported selection
// falls back to the first tab.
export function resolveActiveFileSheetSectionId(openSectionIds, renderedSectionIds) {
  const rendered = normalizeSectionIds(renderedSectionIds);
  return normalizeFileSheetOpenSectionIds(openSectionIds, rendered).at(-1) || rendered[0] || "";
}
