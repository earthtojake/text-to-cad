/**
 * The keys of a tree's rows, one rule for every tree here that walks its rows by the keyboard (the Model
 * tree, the name menu's Files): the WAI-ARIA tree pattern's. From the row that has the keyboard, Down
 * and Up move to the next and the previous row on screen, Home and End to the first and the last; Right
 * opens a shut branch, and on an open one moves to its first row; Left shuts an open branch, and on any
 * other row moves to the row it hangs from. Enter and Space are the row's own button's, as a press is.
 * From outside the rows (`at` -1: a filter over them), Down moves to the first.
 *
 * Pure: a tree hands its rows as they are drawn, top to bottom, each with its depth and whether it is a
 * branch and open, and does what comes back: moves the keyboard to a row, or opens or shuts one, as a
 * press of its chevron does. Null: the key is not the tree's (Up from the first row, a key from the filter
 * other than Down), and the tree leaves it to whoever has it.
 *
 * @param {string} key  `KeyboardEvent.key`
 * @param {readonly { depth: number, branch: boolean, open: boolean }[]} rows
 * @param {number} at  The row with the keyboard, -1 for none.
 * @returns {{ focus: number } | { toggle: number } | null}
 */
export function treeKey(key, rows, at) {
  const last = rows.length - 1;
  if (last < 0) return null;
  if (at < 0 || at > last) return key === "ArrowDown" ? { focus: 0 } : null;
  const row = rows[at];
  switch (key) {
    case "ArrowDown": return at < last ? { focus: at + 1 } : null;
    case "ArrowUp": return at > 0 ? { focus: at - 1 } : null;
    case "Home": return at > 0 ? { focus: 0 } : null;
    case "End": return at < last ? { focus: last } : null;
    case "ArrowRight":
      if (!row.branch) return null;
      if (!row.open) return { toggle: at };
      return at < last && rows[at + 1].depth > row.depth ? { focus: at + 1 } : null;
    case "ArrowLeft": {
      if (row.branch && row.open) return { toggle: at };
      for (let above = at - 1; above >= 0; above -= 1) if (rows[above].depth < row.depth) return { focus: above };
      return null;
    }
    default: return null;
  }
}
