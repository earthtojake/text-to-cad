/**
 * Subsequence matching for the tree's `Filter files…` box.
 *
 * Not a general fuzzy matcher: the corpus is file paths, and the only thing a
 * person typing into that box wants is for `srexfs` to find
 * `src/main/explorer/fs.ts`. So the score rewards exactly what makes that
 * work — matches on a path segment's first character, runs of consecutive
 * characters, and a match late in the path (the filename) over one early in it
 * (a directory nobody was thinking about).
 *
 * Pure, and exported, because it is the part with edge cases worth a test.
 */

export type FuzzyMatch = {
  /** Higher is better. */
  score: number;
  /** Indices in the haystack that the needle matched, for highlighting. */
  indices: number[];
};

const BOUNDARIES = new Set(["/", "-", "_", ".", " "]);

/**
 * Match `needle` against `haystack`, case-insensitively.
 *
 * Greedy left-to-right: for file paths the first subsequence found is the one
 * a person means, and an optimal search over a 20 000-path corpus on every
 * keystroke is not worth the milliseconds.
 */
export function fuzzyMatch(needle: string, haystack: string): FuzzyMatch | null {
  if (needle === "") {
    return { score: 0, indices: [] };
  }
  const lowerNeedle = needle.toLowerCase();
  const lowerHaystack = haystack.toLowerCase();

  const indices: number[] = [];
  let score = 0;
  let cursor = 0;
  let previousIndex = -2;

  for (const character of lowerNeedle) {
    if (character === " ") {
      continue;
    }
    const at = lowerHaystack.indexOf(character, cursor);
    if (at < 0) {
      return null;
    }
    indices.push(at);

    // Consecutive characters are the strongest signal that this is the word
    // being typed and not three letters scattered through a path.
    if (at === previousIndex + 1) {
      score += 8;
    }
    const before = at > 0 ? lowerHaystack[at - 1] : "/";
    if (before !== undefined && BOUNDARIES.has(before)) {
      score += 6;
    }
    // An uppercase letter after a lowercase one is a camelCase boundary.
    // Tested against the previous character rather than against `at > 0`: the
    // looser rule scored the `R` of `models/README.md` and not the `R` of
    // `README.md`, which is exactly backwards.
    const previous = at > 0 ? haystack[at - 1] : undefined;
    if (
      haystack[at] !== lowerHaystack[at] &&
      previous !== undefined &&
      previous === previous.toLowerCase() &&
      previous !== previous.toUpperCase()
    ) {
      score += 3;
    }
    score += 1;
    previousIndex = at;
    cursor = at + 1;
  }

  const lastSlash = lowerHaystack.lastIndexOf("/");
  const firstIndex = indices[0] ?? 0;
  if (firstIndex > lastSlash) {
    // Everything matched inside the filename.
    score += 12;
  }
  // Shallower and shorter wins a tie: `index.ts` before
  // `a/b/c/d/e/index.ts`. Depth carries most of it because it is the better
  // signal — a file near the root of a project is the one a person means —
  // and both penalties are capped so a deep path with a much better match
  // still comes first.
  const depth = lowerHaystack.split("/").length - 1;
  score -= Math.min(10, depth * 2);
  score -= Math.min(6, Math.floor(haystack.length / 16));

  return { score, indices };
}

/** Rank `paths` against `query`, best first, capped at `limit`. */
export function fuzzyFilter(
  paths: readonly string[],
  query: string,
  limit = 300,
): { path: string; indices: number[] }[] {
  const trimmed = query.trim();
  if (trimmed === "") {
    return paths.slice(0, limit).map((path) => ({ path, indices: [] }));
  }
  const scored: { path: string; score: number; indices: number[] }[] = [];
  for (const path of paths) {
    const match = fuzzyMatch(trimmed, path);
    if (match) {
      scored.push({ path, score: match.score, indices: match.indices });
    }
  }
  scored.sort((left, right) => right.score - left.score || left.path.localeCompare(right.path));
  return scored.slice(0, limit).map(({ path, indices }) => ({ path, indices }));
}
