/**
 * diff-lines — pure line-level diff using the Myers algorithm.
 *
 * No external dependencies. Operates on the replaced region supplied by ACP
 * (`oldText` = old_string, `newText` = new_string), not on whole-file content.
 *
 * Public API:
 *   computeDiffRows(oldText, newText) — full interleaved row list, pure (no cache)
 *   countChanges(rows)               — adds + dels over the whole diff
 *   selectPreview(rows)              — window of ≤12 rows around the first change
 *
 * Memoization is handled by the per-instance ChatCaches bundle in core/caches.ts.
 */

// ── Types ─────────────────────────────────────────────────────────────────────

export type DiffRowType = 'context' | 'add' | 'remove';

export type DiffRow = {
  type: DiffRowType;
  text: string;
  /** Index into the old lines array (present on 'context' and 'remove' rows). */
  oldIdx?: number;
  /** Index into the new lines array (present on 'context' and 'add' rows). */
  newIdx?: number;
};

// ── Myers diff ────────────────────────────────────────────────────────────────

/**
 * Classic Myers shortest-edit-script over two string arrays.
 * Returns the sequence of operations to transform `a` into `b`:
 *   'keep'   — line is equal (context)
 *   'insert' — line exists in `b` only (add)
 *   'delete' — line exists in `a` only (remove)
 */
type EditOp = { op: 'keep' | 'insert' | 'delete'; aIdx: number; bIdx: number };

function myersDiff(a: string[], b: string[]): EditOp[] {
  const n = a.length;
  const m = b.length;
  const max = n + m;

  if (max === 0) return [];
  if (n === 0) return b.map((_, i) => ({ op: 'insert' as const, aIdx: 0, bIdx: i }));
  if (m === 0) return a.map((_, i) => ({ op: 'delete' as const, aIdx: i, bIdx: 0 }));

  // v[k] = furthest x reached on diagonal k
  const v: number[] = new Array(2 * max + 1).fill(0);
  // trace[d] = snapshot of v taken BEFORE computing d-step edits.
  //   trace[0] = initial (all zeros)
  //   trace[1] = state after d=0
  //   trace[d+1] = state after d
  // So during backtracking at step d, trace[d] gives us the "came-from" x values.
  const trace: number[][] = [];

  outer: for (let d = 0; d <= max; d++) {
    trace.push(v.slice());
    for (let k = -d; k <= d; k += 2) {
      const ki = k + max;
      let x: number;
      // Choose whether to come from k+1 diagonal (insert) or k-1 diagonal (delete).
      if (k === -d || (k !== d && v[ki - 1]! < v[ki + 1]!)) {
        x = v[ki + 1]!; // insert: move down in b
      } else {
        x = v[ki - 1]! + 1; // delete: move right in a
      }
      let y = x - k;
      // Extend along the snake as far as equal lines allow.
      while (x < n && y < m && a[x] === b[y]) {
        x++;
        y++;
      }
      v[ki] = x;
      if (x >= n && y >= m) break outer;
    }
  }

  // Backtrack to reconstruct the edit script.
  // For each d-step (d > 0): determine whether an insert or delete was taken,
  // emit the snake (context lines) from current (x,y) back to just after the edit,
  // then emit the edit and step back to the previous (x,y).
  // After the loop, emit any remaining context from d=0's snake.
  const ops: EditOp[] = [];
  let x = n;
  let y = m;

  for (let d = trace.length - 1; d > 0; d--) {
    const vd = trace[d]!;
    const k = x - y;
    const ki = k + max;

    // Was this d-step taken via an insert (came from diagonal k+1)?
    const insertStep = k === -d || (k !== d && vd[ki - 1]! < vd[ki + 1]!);
    const prevK = insertStep ? k + 1 : k - 1;
    const prevX = vd[prevK + max]!;
    const prevY = prevX - prevK;

    // The snake for this d-step starts just after the edit:
    //   insert: (prevX, prevY+1)  delete: (prevX+1, prevY)
    const snakeX = insertStep ? prevX : prevX + 1;
    const snakeY = insertStep ? prevY + 1 : prevY;

    // Emit keeps (snake) from (x,y) back to (snakeX, snakeY).
    while (x > snakeX && y > snakeY) {
      ops.push({ op: 'keep', aIdx: x - 1, bIdx: y - 1 });
      x--;
      y--;
    }

    // Emit the edit, then step back to (prevX, prevY).
    if (insertStep) {
      ops.push({ op: 'insert', aIdx: x, bIdx: y - 1 });
      y--;
    } else {
      ops.push({ op: 'delete', aIdx: x - 1, bIdx: y });
      x--;
    }
  }

  // Remaining snake from d=0 (context lines from (x,y) back to (0,0)).
  while (x > 0 && y > 0) {
    ops.push({ op: 'keep', aIdx: x - 1, bIdx: y - 1 });
    x--;
    y--;
  }

  ops.reverse();
  return ops;
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Compute a line-level diff between `oldText` and `newText`.
 *
 * When `oldText` is null (new file), every line in `newText` is an 'add' row.
 * Pure — no internal cache. Memoization lives in ChatCaches (core/caches.ts).
 */
export function computeDiffRows(oldText: string | null, newText: string): DiffRow[] {
  if (oldText === null) {
    return newText.split('\n').map((text, i) => ({ type: 'add' as const, text, newIdx: i }));
  }

  const aLines = oldText.split('\n');
  const bLines = newText.split('\n');
  const ops = myersDiff(aLines, bLines);

  return ops.map((op) => {
    if (op.op === 'keep') {
      return {
        type: 'context' as const,
        text: aLines[op.aIdx]!,
        oldIdx: op.aIdx,
        newIdx: op.bIdx,
      };
    }
    if (op.op === 'delete') {
      return { type: 'remove' as const, text: aLines[op.aIdx]!, oldIdx: op.aIdx };
    }
    return { type: 'add' as const, text: bLines[op.bIdx]!, newIdx: op.bIdx };
  });
}

/**
 * Count the total number of additions and deletions across a full diff.
 */
export function countChanges(rows: DiffRow[]): { adds: number; dels: number } {
  let adds = 0;
  let dels = 0;
  for (const row of rows) {
    if (row.type === 'add') adds++;
    else if (row.type === 'remove') dels++;
  }
  return { adds, dels };
}

/**
 * Select a preview window of `maxLines` rows anchored at the first changed line,
 * with `context` leading context lines before the first change.
 *
 * Returns an empty array when there are no changes.
 */
export function selectPreview(rows: DiffRow[], maxLines = 12, context = 1): DiffRow[] {
  const firstChange = rows.findIndex((r) => r.type !== 'context');
  if (firstChange === -1) return [];
  const start = Math.max(0, firstChange - context);
  return rows.slice(start, start + maxLines);
}
