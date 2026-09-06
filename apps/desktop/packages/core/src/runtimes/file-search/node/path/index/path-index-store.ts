import type { PortableRelativePath } from '#primitives/path/api';
import type { PathEntryKind, PathSearchHit } from '#runtimes/file-search/api';

export type PathIndexEntry = Readonly<{
  path: PortableRelativePath;
  kind: PathEntryKind;
}>;

export type PathIndexPatch =
  | Readonly<{ kind: 'upsert'; entry: PathIndexEntry }>
  | Readonly<{ kind: 'delete-subtree'; path: PortableRelativePath }>
  | Readonly<{
      kind: 'replace-subtree';
      path: PortableRelativePath;
      entries: readonly PathIndexEntry[];
    }>;

export type PathIndexStoreSearchResult =
  | Readonly<{ kind: 'ready'; hits: PathSearchHit[] }>
  | Readonly<{ kind: 'not-ready' }>;

/** An unpublished generation being populated by one full-root scan. */
export interface PathIndexBuild {
  append(entries: readonly PathIndexEntry[]): void;
  publish(finalPatches: readonly PathIndexPatch[]): void;
  discard(): void;
}

/** Persistence view owned by path-index maintenance and queries. */
export interface PathIndexStore {
  beginBuild(rootId: number): PathIndexBuild;
  applyPublishedPatches(rootId: number, patches: readonly PathIndexPatch[]): void;

  /**
   * Treats `query` as literal user text and returns relevance-ordered hits. The adapter owns
   * FTS escaping and the non-FTS fallback needed for queries shorter than three characters.
   */
  searchPaths(
    rootKey: string,
    query: string,
    kinds: readonly PathEntryKind[],
    limit: number
  ): PathIndexStoreSearchResult;
}
