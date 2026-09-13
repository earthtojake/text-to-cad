import { sql } from 'drizzle-orm';
import { check, integer, sqliteTable, text, uniqueIndex } from 'drizzle-orm/sqlite-core';
import { pathEntryKinds } from '../../api/path-entry-kind';

export const registeredRoots = sqliteTable(
  'registered_roots',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    rootKey: text('root_key').notNull(),
    rootPath: text('root_path').notNull(),
    currentGeneration: integer('current_generation'),
  },
  (t) => [
    uniqueIndex('registered_roots_root_key_idx').on(t.rootKey),
    check('registered_roots_root_key_check', sql`length(${t.rootKey}) > 0`),
    check('registered_roots_root_path_check', sql`length(${t.rootPath}) > 0`),
    check('registered_roots_current_generation_check', sql`${t.currentGeneration} >= 1`),
  ]
);

export const pathEntries = sqliteTable(
  'path_entries',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    rootId: integer('root_id')
      .notNull()
      .references(() => registeredRoots.id, { onDelete: 'cascade' }),
    generation: integer('generation').notNull(),
    relativePath: text('relative_path').notNull(),
    name: text('name').notNull(),
    kind: text('kind', { enum: pathEntryKinds }).notNull(),
  },
  (t) => [
    uniqueIndex('path_entries_root_generation_path_idx').on(t.rootId, t.generation, t.relativePath),
    check('path_entries_generation_check', sql`${t.generation} >= 1`),
    check('path_entries_relative_path_check', sql`length(${t.relativePath}) > 0`),
    check('path_entries_name_check', sql`length(${t.name}) > 0`),
    check('path_entries_kind_check', sql`${t.kind} IN ('file', 'directory')`),
  ]
);
