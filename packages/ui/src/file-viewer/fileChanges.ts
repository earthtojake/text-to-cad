import type { FileChange, FileEntry } from "./types.js";

export const isSameOrUnder = (path: string, ancestor: string) => path === ancestor || path.startsWith(`${ancestor}/`);
export const movedFilePath = (path: string, from: string, to: string) => isSameOrUnder(path, from) ? to + path.slice(from.length) : path;

/** A committed move preserves expanded subtrees; deletion removes every cached descendant. */
export function reconcileFileTree<T extends FileEntry>(
  listings: Record<string, readonly T[]>, expanded: readonly string[], changes: readonly FileChange[],
) {
  let nextListings = listings, nextExpanded = expanded;
  for (const change of changes) {
    if (change.kind === "moved") {
      const move = (path: string) => movedFilePath(path, change.from, change.to);
      nextListings = Object.fromEntries(Object.entries(nextListings).map(([directory, entries]) => [move(directory), entries.map(entry => {
        const path = move(entry.path);
        return path === entry.path ? entry : { ...entry, path, name: path.split("/").pop() || path };
      })]));
      nextExpanded = nextExpanded.map(move);
    } else if (change.kind === "deleted") {
      nextListings = Object.fromEntries(Object.entries(nextListings)
        .filter(([directory]) => !isSameOrUnder(directory, change.path))
        .map(([directory, entries]) => [directory, entries.filter(entry => !isSameOrUnder(entry.path, change.path))]));
      nextExpanded = nextExpanded.filter(directory => !isSameOrUnder(directory, change.path));
    }
  }
  return { listings: nextListings, expanded: [...new Set(nextExpanded)] };
}
