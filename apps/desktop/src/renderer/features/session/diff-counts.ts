/**
 * Lines added and removed, as a multiset difference — a badge, not a diff
 * viewer. A module of its own so a test can count how often the transcript
 * asks for it: `view.ts` remembers the answer per tool call part.
 */
export function diffCounts(oldText: string, newText: string): { insertions: number; deletions: number } {
  const count = (text: string) => {
    const map = new Map<string, number>();
    if (text === "") {
      return map;
    }
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
