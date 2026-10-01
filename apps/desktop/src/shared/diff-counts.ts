/**
 * Lines added and removed between two texts, as a multiset difference — a
 * badge, not a diff viewer. Main tallies a session's changes with it; the
 * renderer badges each edit (`renderer/features/session/diff-counts.ts`).
 */
export function diffCounts(oldText: string, newText: string): { insertions: number; deletions: number } {
  const count = (text: string) => {
    const map = new Map<string, number>();
    if (text === "") {
      return map;
    }
    // A trailing newline ends the last line; it does not start an empty one.
    for (const line of text.replace(/\n$/, "").split("\n")) {
      map.set(line, (map.get(line) ?? 0) + 1);
    }
    return map;
  };
  const before = count(oldText);
  const after = count(newText);
  let insertions = 0;
  let deletions = 0;
  for (const [line, n] of after) {
    insertions += Math.max(0, n - (before.get(line) ?? 0));
  }
  for (const [line, n] of before) {
    deletions += Math.max(0, n - (after.get(line) ?? 0));
  }
  return { insertions, deletions };
}
