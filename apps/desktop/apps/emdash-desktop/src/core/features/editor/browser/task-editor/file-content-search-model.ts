import type { ContentSearchFileResult } from '@emdash/core/runtimes/file-search/api';

/** Content-search progress is append-only, grouped into occurrence batches. */
export function mergeContentSearchFiles(
  current: readonly ContentSearchFileResult[],
  incoming: readonly ContentSearchFileResult[]
): ContentSearchFileResult[] {
  const merged = new Map(current.map((file) => [file.path, [...file.matches]]));
  for (const file of incoming) {
    const matches = merged.get(file.path);
    if (matches) matches.push(...file.matches);
    else merged.set(file.path, [...file.matches]);
  }
  return [...merged].map(([path, matches]) => ({ path, matches }));
}

export function countContentSearchOccurrences(files: readonly ContentSearchFileResult[]): number {
  return files.reduce(
    (total, file) =>
      total + file.matches.reduce((fileTotal, match) => fileTotal + match.locations.length, 0),
    0
  );
}
