import type Database from 'better-sqlite3';
import { and, eq, inArray, ne, or, sql } from 'drizzle-orm';
import {
  parsePortableRelativePath,
  portableRelativePathBasename,
  type PortableRelativePath,
} from '#primitives/path/api';
import type { StoreHandle } from '#primitives/sqlite-store/api';
import type { PathEntryKind, PathSearchHit } from '#runtimes/file-search/api';
import type {
  PathIndexBuild,
  PathIndexEntry,
  PathIndexPatch,
  PathIndexStore,
  PathIndexStoreSearchResult,
} from '../path/index/path-index-store';
import type { StoredFileSearchRoot } from '../root/registered-root';
import type { FileSearchRootUpsertResult, RootCatalogStore } from '../root/root-registry';
import { pathEntries, registeredRoots } from './schema';
import type { FileSearchDb } from './store';

type RootRow = typeof registeredRoots.$inferSelect;

type PathRow = {
  relativePath: string;
  kind: string;
};

/** Synchronous by design: this adapter runs inside the dedicated file-search worker. */
export class SqliteFileSearchStore implements RootCatalogStore, PathIndexStore {
  private readonly database: Database.Database;
  private readonly activeBuildRootIds = new Set<number>();

  constructor(private readonly handle: StoreHandle<FileSearchDb, Database.Database>) {
    this.database = handle.connection.native;
  }

  listRoots(): StoredFileSearchRoot[] {
    return this.handle.db
      .select()
      .from(registeredRoots)
      .orderBy(registeredRoots.id)
      .all()
      .map(toStoredRoot);
  }

  upsertRoot(input: { rootKey: string; rootPath: string }): FileSearchRootUpsertResult {
    const existing = this.rootByKey(input.rootKey);
    if (!existing) {
      const created = this.handle.db
        .insert(registeredRoots)
        .values({ rootKey: input.rootKey, rootPath: input.rootPath })
        .returning({ id: registeredRoots.id })
        .get();
      return { kind: 'created', root: { id: created.id, ...input } };
    }

    if (existing.rootPath === input.rootPath) {
      return { kind: 'unchanged', root: toStoredRoot(existing) };
    }
    throw new Error(`Corrupt file-search root identity: ${input.rootKey}`);
  }

  deleteRoot(rootKey: string): void {
    this.handle.db.delete(registeredRoots).where(eq(registeredRoots.rootKey, rootKey)).run();
  }

  beginBuild(rootId: number): PathIndexBuild {
    if (this.activeBuildRootIds.has(rootId)) {
      throw new Error(`File-search root already has an active build: ${rootId}`);
    }
    const root = this.rootById(rootId);
    if (!root) throw new Error(`Cannot build an unknown file-search root: ${rootId}`);
    this.activeBuildRootIds.add(rootId);

    const generation = (root.currentGeneration ?? 0) + 1;
    try {
      this.handle.db
        .delete(pathEntries)
        .where(
          root.currentGeneration === null
            ? eq(pathEntries.rootId, rootId)
            : and(
                eq(pathEntries.rootId, rootId),
                ne(pathEntries.generation, root.currentGeneration)
              )
        )
        .run();
    } catch (error) {
      this.activeBuildRootIds.delete(rootId);
      throw error;
    }

    let state: 'open' | 'published' | 'discarded' = 'open';
    const assertBuildOpen = (): void => {
      if (state !== 'open') throw new Error(`Path-index build is already ${state}`);
    };

    return {
      append: (entries) => {
        assertBuildOpen();
        this.handle.transaction(() => this.insertEntries(rootId, generation, entries));
      },
      publish: (finalPatches) => {
        assertBuildOpen();
        this.handle.transaction(() => {
          this.applyPatches(rootId, generation, finalPatches);
          const updated = this.handle.db
            .update(registeredRoots)
            .set({ currentGeneration: generation })
            .where(eq(registeredRoots.id, rootId))
            .run();
          if (changesAsNumber(updated.changes) !== 1) {
            throw new Error(`File-search root disappeared during build: ${rootId}`);
          }
          this.handle.db
            .delete(pathEntries)
            .where(and(eq(pathEntries.rootId, rootId), ne(pathEntries.generation, generation)))
            .run();
        });
        state = 'published';
        this.activeBuildRootIds.delete(rootId);
      },
      discard: () => {
        if (state !== 'open') return;
        try {
          this.handle.db
            .delete(pathEntries)
            .where(and(eq(pathEntries.rootId, rootId), eq(pathEntries.generation, generation)))
            .run();
        } finally {
          state = 'discarded';
          this.activeBuildRootIds.delete(rootId);
        }
      },
    };
  }

  applyPublishedPatches(rootId: number, patches: readonly PathIndexPatch[]): void {
    if (patches.length === 0) return;
    const root = this.rootById(rootId);
    if (!root) throw new Error(`Cannot patch an unknown file-search root: ${rootId}`);
    if (root.currentGeneration === null) {
      throw new Error(`Cannot patch file-search root ${rootId} before its first generation`);
    }
    this.handle.transaction(() => this.applyPatches(rootId, root.currentGeneration!, patches));
  }

  searchPaths(
    rootKey: string,
    query: string,
    kinds: readonly PathEntryKind[],
    limit: number
  ): PathIndexStoreSearchResult {
    assertPathKinds(kinds);
    const root = this.rootByKey(rootKey);
    if (!root || root.currentGeneration === null) return { kind: 'not-ready' };

    const normalizedQuery = query.trim();
    const rows = normalizedQuery
      ? this.searchMatchingPaths(root, normalizedQuery, kinds, limit)
      : this.listPaths(root, kinds, limit);
    return { kind: 'ready', hits: rows.map(toPathSearchHit) };
  }

  private listPaths(root: RootRow, kinds: readonly PathEntryKind[], limit: number): PathRow[] {
    return this.handle.db
      .select({ relativePath: pathEntries.relativePath, kind: pathEntries.kind })
      .from(pathEntries)
      .where(
        and(
          eq(pathEntries.rootId, root.id),
          eq(pathEntries.generation, root.currentGeneration!),
          inArray(pathEntries.kind, [...kinds])
        )
      )
      .orderBy(sql`${pathEntries.relativePath} COLLATE NOCASE`, pathEntries.relativePath)
      .limit(limit)
      .all();
  }

  private searchMatchingPaths(
    root: RootRow,
    query: string,
    kinds: readonly PathEntryKind[],
    limit: number
  ): PathRow[] {
    const terms = pathSearchTerms(query);
    if (terms.length === 0) return this.searchPathsBySubstring(root, [query], kinds, limit);
    if (terms.some((term) => term.length < 3)) {
      return this.searchPathsBySubstring(root, terms, kinds, limit);
    }

    const kindClause = placeholders(kinds.length);
    const matchExpression = terms.map(quoteFtsTerm).join(' AND ');
    return this.database
      .prepare(
        `SELECT relative_path AS relativePath, kind
         FROM path_entries_fts
         WHERE path_entries_fts MATCH ?
           AND root_id = ?
           AND generation = ?
           AND kind IN (${kindClause})
         ORDER BY bm25(path_entries_fts, 0, 0, 0, 1, 2), relative_path COLLATE NOCASE
         LIMIT ?`
      )
      .all(matchExpression, root.id, root.currentGeneration, ...kinds, limit) as PathRow[];
  }

  private searchPathsBySubstring(
    root: RootRow,
    terms: readonly string[],
    kinds: readonly PathEntryKind[],
    limit: number
  ): PathRow[] {
    const termConditions = terms.map((term) =>
      or(
        sql<boolean>`instr(lower(${pathEntries.name}), lower(${term})) > 0`,
        sql<boolean>`instr(lower(${pathEntries.relativePath}), lower(${term})) > 0`
      )
    );
    return this.handle.db
      .select({ relativePath: pathEntries.relativePath, kind: pathEntries.kind })
      .from(pathEntries)
      .where(
        and(
          eq(pathEntries.rootId, root.id),
          eq(pathEntries.generation, root.currentGeneration!),
          inArray(pathEntries.kind, [...kinds]),
          ...termConditions
        )
      )
      .orderBy(
        sql`length(${pathEntries.name})`,
        sql`${pathEntries.relativePath} COLLATE NOCASE`,
        pathEntries.relativePath
      )
      .limit(limit)
      .all();
  }

  private applyPatches(
    rootId: number,
    generation: number,
    patches: readonly PathIndexPatch[]
  ): void {
    for (const patch of patches) {
      switch (patch.kind) {
        case 'upsert':
          this.insertEntries(rootId, generation, [patch.entry]);
          break;
        case 'delete-subtree':
          this.deleteSubtree(rootId, generation, patch.path);
          break;
        case 'replace-subtree':
          this.assertReplacementEntries(patch.path, patch.entries);
          this.deleteSubtree(rootId, generation, patch.path);
          this.insertEntries(rootId, generation, patch.entries);
          break;
      }
    }
  }

  private insertEntries(
    rootId: number,
    generation: number,
    entries: readonly PathIndexEntry[]
  ): void {
    if (entries.length === 0) return;
    this.handle.db
      .insert(pathEntries)
      .values(
        entries.map((entry) => ({
          rootId,
          generation,
          relativePath: entry.path,
          name: portableRelativePathBasename(entry.path),
          kind: entry.kind,
        }))
      )
      .onConflictDoUpdate({
        target: [pathEntries.rootId, pathEntries.generation, pathEntries.relativePath],
        set: { name: sql`excluded.name`, kind: sql`excluded.kind` },
      })
      .run();
  }

  private deleteSubtree(rootId: number, generation: number, subtree: PortableRelativePath): void {
    const pathCondition =
      subtree === ''
        ? undefined
        : or(
            eq(pathEntries.relativePath, subtree),
            sql<boolean>`${pathEntries.relativePath} LIKE ${`${escapeLike(subtree)}/%`} ESCAPE '\\'`
          );
    this.handle.db
      .delete(pathEntries)
      .where(
        and(eq(pathEntries.rootId, rootId), eq(pathEntries.generation, generation), pathCondition)
      )
      .run();
  }

  private assertReplacementEntries(
    subtree: PortableRelativePath,
    entries: readonly PathIndexEntry[]
  ): void {
    const prefix = subtree ? `${subtree}/` : '';
    for (const entry of entries) {
      if (subtree === '' || entry.path === subtree || entry.path.startsWith(prefix)) continue;
      throw new Error(`Replacement entry '${entry.path}' is outside subtree '${subtree}'`);
    }
  }

  private rootByKey(rootKey: string): RootRow | undefined {
    return this.handle.db
      .select()
      .from(registeredRoots)
      .where(eq(registeredRoots.rootKey, rootKey))
      .get();
  }

  private rootById(rootId: number): RootRow | undefined {
    return this.handle.db
      .select()
      .from(registeredRoots)
      .where(eq(registeredRoots.id, rootId))
      .get();
  }
}

function toStoredRoot(row: RootRow): StoredFileSearchRoot {
  return { id: row.id, rootKey: row.rootKey, rootPath: row.rootPath };
}

function toPathSearchHit(row: PathRow): PathSearchHit {
  const parsed = parsePortableRelativePath(row.relativePath);
  if (!parsed.success || (row.kind !== 'file' && row.kind !== 'directory')) {
    throw new Error(`Corrupt path-index row: ${row.relativePath}`);
  }
  return { path: parsed.data, kind: row.kind };
}

function pathSearchTerms(query: string): string[] {
  return query
    .split(/[\s\-_/]+/u)
    .map((term) => term.trim())
    .filter(Boolean);
}

function quoteFtsTerm(term: string): string {
  return `"${term.replace(/"/g, '""')}"`;
}

function placeholders(count: number): string {
  return Array.from({ length: count }, () => '?').join(', ');
}

function assertPathKinds(kinds: readonly PathEntryKind[]): void {
  if (kinds.length < 1) throw new Error('At least one path kind is required');
}

function escapeLike(value: string): string {
  return value.replace(/[\\%_]/g, (character) => `\\${character}`);
}

function changesAsNumber(changes: number | bigint): number {
  return typeof changes === 'bigint' ? Number(changes) : changes;
}
