/**
 * The Model tree's open rows (`XbfRenderer.jsx`'s, the host's: an assembly by its selection id, a folded
 * row by its own id), and who opened those the person did not:
 *
 *   { open: string[], by: { [row id]: "reveal" | "isolation" } }
 *
 * A row the person opened (its chevron, a key, the menu's Expand) is theirs, and so is a row a reveal
 * opened once they open or shut it. A reveal of a pick opens rows of its own ("reveal"); an isolation
 * opens what it isolates and, with its reveal, the rows above it ("isolation"). Only the person's rows
 * are kept with the file's view, so a reload opens what the person opened and nothing a pick did; and
 * leaving isolation shuts what isolating opened, so the tree is as it was before. Pure.
 */

export const NO_EXPANSION = Object.freeze({ open: Object.freeze([]), by: Object.freeze({}) });

const without = (by, ids) => {
  const gone = new Set(ids);
  return Object.fromEntries(Object.entries(by).filter(([id]) => !gone.has(id)));
};

/** The person's rows, as a file's view gives them back: open, and theirs. */
export const personsExpansion = ids => ({ open: [...new Set(ids)], by: {} });

/** The person opens or shuts a row: open or shut, it is theirs from now on. */
export function toggleRow(expansion, id) {
  const open = expansion.open.includes(id) ? expansion.open.filter(item => item !== id) : [...expansion.open, id];
  return { open, by: without(expansion.by, [id]) };
}

/** The person opens every row of `ids` at once (the menu's Expand all): the tree's open shape is theirs, all of it. */
export function openAllRows(expansion, ids) {
  return { open: [...new Set([...expansion.open, ...ids])], by: {} };
}

/** Rows a reveal or an isolation opens (`reason`), those of them that are shut: a row already open stays whose it was. */
export function openRows(expansion, ids, reason) {
  const shut = [...new Set(ids)].filter(id => !expansion.open.includes(id));
  if (!shut.length) return expansion;
  return { open: [...expansion.open, ...shut], by: { ...expansion.by, ...Object.fromEntries(shut.map(id => [id, reason])) } };
}

/** Rows shut, whoever opened them (the person's Collapse, a hidden node's subtree). */
export function shutRows(expansion, ids) {
  const gone = new Set(ids);
  if (!expansion.open.some(id => gone.has(id))) return expansion;
  return { open: expansion.open.filter(id => !gone.has(id)), by: without(expansion.by, ids) };
}

/** The rows `reason` opened shut again, those of them in `within` where it is given; the rest as they are. */
export function shutOpenedBy(expansion, reason, within = null) {
  const ids = Object.entries(expansion.by).filter(([id, by]) => by === reason && (!within || within.has(id))).map(([id]) => id);
  return ids.length ? shutRows(expansion, ids) : expansion;
}

/** The rows the person opened: what the file's view keeps. */
export const personsRows = expansion => expansion.open.filter(id => !expansion.by[id]);
