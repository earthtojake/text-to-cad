const LABELS = { face: ['face', 'faces'], edge: ['edge', 'edges'], vertex: ['vertex', 'vertices'], shape: ['solid', 'solids'], part: ['part', 'parts'], assembly: ['assembly', 'assemblies'], other: ['item', 'items'] };

/** Summarize the canonical selection, counting instances rather than shared components. */
export function selectionSummary(references = [], occurrences = []) {
  const items = [...new Map(references.filter(Boolean).map(item => [item.id, item])).values()];
  const counts = {};
  for (const item of items) {
    const kind = item.selectorType === 'occurrence' || !item.selectorType
      ? (item.nodeType === 'assembly' || item.children?.length ? 'assembly' : 'part')
      : item.selectorType;
    const key = LABELS[kind] ? kind : 'other';
    counts[key] = (counts[key] || 0) + 1;
  }
  const label = Object.entries(LABELS).filter(([kind]) => counts[kind])
    .map(([kind, names]) => `${counts[kind]} ${names[counts[kind] === 1 ? 0 : 1]}`).join(', ');
  // A parent label is useful for topology selections; whole-part counts already say it.
  const topologyOnly = items.length > 0 && items.every(item => ['face', 'edge', 'vertex', 'shape'].includes(item.selectorType));
  const partIds = new Set(items.map(item => item.occurrenceId).filter(Boolean));
  let context = '';
  if (topologyOnly && items.every(item => item.occurrenceId)) {
    if (partIds.size > 1) context = `${partIds.size} parts`;
    else {
      const id = items[0].occurrenceId;
      context = [occurrences.find(part => part.id === id)?.name, items[0].pickData?.sourceName]
        .find(name => name?.trim() && name !== id) || '';
    }
  }
  return { label, context };
}
