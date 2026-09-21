// The sheet's single-line rows are 28px tall with a 1px gap. The entire tree
// keeps its scroll extent; only the viewport and a small buffer need DOM rows.
export const STEP_TREE_ROW_HEIGHT = 28;
export const STEP_TREE_ROW_STRIDE = 29;
export const STEP_TREE_OVERSCAN = 8;

export function stepTreeWindowRange(rowCount, {
  scrollTop = 0,
  viewportHeight = 600,
  listTop = 0,
} = {}) {
  const count = Math.max(0, rowCount);
  const first = Math.floor(Math.max(0, scrollTop - listTop) / STEP_TREE_ROW_STRIDE);
  const last = Math.ceil(Math.max(0, scrollTop + viewportHeight - listTop) / STEP_TREE_ROW_STRIDE);
  // Clamp both ends after a collapse/filter shortens a scrolled tree. The
  // browser clamps scrollTop once the new spacer has reached the DOM.
  const end = Math.min(count, Math.max(0, last) + STEP_TREE_OVERSCAN);
  const start = Math.min(end, Math.max(0, Math.min(first, count) - STEP_TREE_OVERSCAN));
  return { start, end };
}

export function stepTreeWindowIndexes(range, rowCount, retainedIndexes = []) {
  const indexes = new Set();
  for (let index = range.start; index < Math.min(range.end, rowCount); index += 1) {
    indexes.add(index);
  }
  // Only a focused row and an open context menu can be retained. Selecting
  // thousands of parts must never turn into thousands of mounted rows.
  for (const index of retainedIndexes.slice(0, 2)) {
    if (Number.isInteger(index) && index >= 0 && index < rowCount) indexes.add(index);
  }
  return [...indexes].sort((a, b) => a - b);
}

export function stepTreeRowScrollTop(index, {
  scrollTop,
  viewportHeight,
  listTop,
}, { block = "nearest", paddingTop = 120 } = {}) {
  const top = listTop + index * STEP_TREE_ROW_STRIDE;
  const bottom = top + STEP_TREE_ROW_HEIGHT;
  if (block === "center") return Math.max(0, top + STEP_TREE_ROW_HEIGHT / 2 - viewportHeight / 2);
  const padding = Math.min(paddingTop, Math.max(0, viewportHeight - STEP_TREE_ROW_HEIGHT));
  if (top < scrollTop + padding) return Math.max(0, top - padding);
  if (bottom > scrollTop + viewportHeight) return Math.max(0, bottom - viewportHeight);
  return scrollTop;
}

export function findFocusableStepTreeRow(rows, startIndex, direction, isDisabled) {
  const step = direction < 0 ? -1 : 1;
  let index = Math.min(Math.max(startIndex, 0), rows.length - 1);
  for (; index >= 0 && index < rows.length; index += step) {
    if (!isDisabled(rows[index])) return index;
  }
  return -1;
}

export function stepTreeFocusFallback(previousRows, nextRows, focusedId) {
  const previousIndex = previousRows.findIndex((row) => row.id === focusedId);
  if (previousIndex < 0 || !nextRows.length) return -1;
  const nextIndexes = new Map(nextRows.map((row, index) => [row.id, index]));
  let depth = previousRows[previousIndex].depth;
  for (let index = previousIndex - 1; index >= 0; index -= 1) {
    if (previousRows[index].depth < depth) {
      depth = previousRows[index].depth;
      const nextIndex = nextIndexes.get(previousRows[index].id);
      if (nextIndex !== undefined) return nextIndex;
    }
  }
  return Math.min(previousIndex, nextRows.length - 1);
}

// Flat treeitems still expose their actual sibling positions to assistive
// technology when most siblings are outside the rendered window.
export function stepTreeSiblingPositions(rows) {
  const groups = [];
  const positions = [];
  const parentGroups = [];
  for (let index = 0; index < rows.length; index += 1) {
    const depth = Math.max(0, rows[index].depth || 0);
    parentGroups.length = depth + 1;
    const group = parentGroups[depth] || (parentGroups[depth] = []);
    if (!group.length) groups.push(group);
    group.push(index);
  }
  for (const group of groups) {
    group.forEach((index, position) => { positions[index] = { position: position + 1, size: group.length }; });
  }
  return positions;
}
