import type { SqliteConnection } from '#primitives/sqlite-store/api';

const ftsSchemaSql = `
  CREATE VIRTUAL TABLE path_entries_fts USING fts5(
    root_id UNINDEXED,
    generation UNINDEXED,
    kind UNINDEXED,
    relative_path,
    name,
    content = 'path_entries',
    content_rowid = 'id',
    tokenize = 'trigram case_sensitive 0'
  );

  CREATE TRIGGER path_entries_after_insert AFTER INSERT ON path_entries BEGIN
    INSERT INTO path_entries_fts(rowid, root_id, generation, kind, relative_path, name)
    VALUES (new.id, new.root_id, new.generation, new.kind, new.relative_path, new.name);
  END;

  CREATE TRIGGER path_entries_after_delete AFTER DELETE ON path_entries BEGIN
    INSERT INTO path_entries_fts(
      path_entries_fts, rowid, root_id, generation, kind, relative_path, name
    )
    VALUES (
      'delete', old.id, old.root_id, old.generation, old.kind, old.relative_path, old.name
    );
  END;

  CREATE TRIGGER path_entries_after_update AFTER UPDATE ON path_entries BEGIN
    INSERT INTO path_entries_fts(
      path_entries_fts, rowid, root_id, generation, kind, relative_path, name
    )
    VALUES (
      'delete', old.id, old.root_id, old.generation, old.kind, old.relative_path, old.name
    );

    INSERT INTO path_entries_fts(rowid, root_id, generation, kind, relative_path, name)
    VALUES (new.id, new.root_id, new.generation, new.kind, new.relative_path, new.name);
  END;
`;

export function ensureFileSearchFtsSchema(connection: SqliteConnection): void {
  const existing = connection.get(
    `SELECT 1
     FROM sqlite_schema
     WHERE type = 'table' AND name = 'path_entries_fts'`
  );
  if (existing) return;

  connection.exec('BEGIN IMMEDIATE');
  try {
    connection.exec(ftsSchemaSql);
    connection.exec(`INSERT INTO path_entries_fts(path_entries_fts) VALUES ('rebuild')`);
    connection.exec('COMMIT');
  } catch (error) {
    try {
      connection.exec('ROLLBACK');
    } catch (rollbackError) {
      throw new AggregateError([error, rollbackError], 'File-search FTS schema rollback failed');
    }
    throw error;
  }
}
