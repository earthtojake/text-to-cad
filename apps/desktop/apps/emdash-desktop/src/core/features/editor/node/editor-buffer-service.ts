import { basename, dirname, extname, join } from 'node:path';
import {
  decodeResourceUri,
  encodeResourceUri,
  type ResourceUri,
} from '@emdash/core/primitives/path/api';
import type { SqliteConnection, StoreHandle } from '@emdash/core/primitives/sqlite-store/api';
import {
  betterSqlite3Driver,
  defineDerivedSqliteStore,
  fingerprintDerivedSchema,
} from '@emdash/core/primitives/sqlite-store/node';

const BUFFER_STALE_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

/**
 * Crash-recovery buffers live in their own SQLite database, independent of the
 * app DB and deliberately outside its Drizzle migration machinery: rows are
 * disposable crash-recovery artifacts, so the schema is self-managed as a
 * derived store — created on open and stamped via `PRAGMA user_version` with
 * this SQL's fingerprint; on any mismatch the database is dropped and
 * recreated wholesale (decided in the file-content-stack spec §8/§11).
 *
 * Keys are serialized ResourceUris (`emdash-file://v2/...`), so workspace
 * membership is not part of buffer identity and files outside any workspace
 * root are first-class rows.
 */
const schemaSql = `
  CREATE TABLE editor_buffers (
    uri TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    updated_at INTEGER NOT NULL
  ) STRICT;
`;

export const editorBufferSqliteStore = defineDerivedSqliteStore({
  name: 'editor-buffers',
  driver: betterSqlite3Driver,
  version: fingerprintDerivedSchema(schemaSql),
  createSchema(connection) {
    connection.exec(schemaSql);
  },
});

/**
 * Resolves the buffer store's database file as a sibling of the app database
 * (mirrors the automations/file-search convention), so `EMDASH_DB_FILE`-style
 * overrides isolate this store together with the app DB.
 */
export function editorBufferDatabasePath(appDatabasePath: string): string {
  const extension = extname(appDatabasePath);
  const base = basename(appDatabasePath, extension);
  return join(dirname(appDatabasePath), `${base}-editor-buffers${extension || '.db'}`);
}

export type EditorBufferServiceDeps = {
  handle: StoreHandle<SqliteConnection>;
  logger?: {
    error(message: string, error: unknown): void;
  };
};

export type EditorBufferEntry = { uri: ResourceUri; content: string };

/**
 * Crash-recovery buffer store keyed by ResourceUri. Keys are canonicalized
 * (decoded and re-encoded) on every write and query so prefix enumeration
 * never depends on the caller's encoding.
 */
export class EditorBufferService {
  constructor(private readonly deps: EditorBufferServiceDeps) {}

  async saveBuffer(uri: ResourceUri, content: string): Promise<void> {
    this.deps.handle.connection.run(
      `INSERT INTO editor_buffers (uri, content, updated_at) VALUES (?, ?, ?)
       ON CONFLICT (uri) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at`,
      [canonicalResourceUri(uri), content, Date.now()]
    );
  }

  async clearBuffer(uri: ResourceUri): Promise<void> {
    this.deps.handle.connection.run(`DELETE FROM editor_buffers WHERE uri = ?`, [
      canonicalResourceUri(uri),
    ]);
  }

  /**
   * Lists persisted buffers. With `root`, returns only buffers for files
   * strictly under that root ResourceUri (same host, path prefix on segment
   * boundaries); without it, returns every buffer — including files outside
   * any workspace root.
   */
  async listBuffers(root?: ResourceUri): Promise<EditorBufferEntry[]> {
    if (root === undefined) {
      return this.deps.handle.connection.all<EditorBufferEntry>(
        `SELECT uri, content FROM editor_buffers`
      );
    }
    // ResourceUri segments are percent-encoded, so `/` only occurs as the
    // segment separator and a `<root>/` prefix match is boundary-safe. Uses
    // substr() rather than LIKE because percent-encoding puts `%` in keys.
    const prefix = `${canonicalResourceUri(root)}/`;
    return this.deps.handle.connection.all<EditorBufferEntry>(
      `SELECT uri, content FROM editor_buffers WHERE substr(uri, 1, ?) = ?`,
      [prefix.length, prefix]
    );
  }

  async pruneStale(): Promise<void> {
    try {
      const cutoff = Date.now() - BUFFER_STALE_MS;
      this.deps.handle.connection.run(`DELETE FROM editor_buffers WHERE updated_at < ?`, [cutoff]);
    } catch (e) {
      this.deps.logger?.error('Failed to prune stale editor buffers:', e);
    }
  }

  dispose(): void {
    this.deps.handle.close();
  }
}

function canonicalResourceUri(uri: ResourceUri): ResourceUri {
  const decoded = decodeResourceUri(uri);
  if (!decoded.success) throw new Error(decoded.error.message);
  return encodeResourceUri(decoded.data);
}

export function createEditorBufferService(options: {
  databasePath: string;
  logger?: EditorBufferServiceDeps['logger'];
}): EditorBufferService {
  return new EditorBufferService({
    handle: editorBufferSqliteStore.open(options.databasePath),
    logger: options.logger,
  });
}
