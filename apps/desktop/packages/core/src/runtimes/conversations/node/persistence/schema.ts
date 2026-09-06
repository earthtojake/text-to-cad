import { integer, sqliteTable, text } from 'drizzle-orm/sqlite-core';

/**
 * One row per conversation record (spec §3.2). Plain columns for immutable identity fields
 * and index-maintained timestamps; versioned house-pattern JSON (see payload-codecs.ts) for
 * `config` and the provider-linkage sub-record.
 */
export const conversationRecords = sqliteTable('conversation_records', {
  id: text('id').primaryKey(),
  provider: text('provider').notNull(),
  type: text('type', { enum: ['pty', 'acp'] }).notNull(),
  cwd: text('cwd').notNull(),
  workspacePath: text('workspace_path').notNull(),
  createdAt: integer('created_at').notNull(),
  title: text('title').notNull(),
  /** Versioned JSON envelope around the opaque client config payload. */
  config: text('config').notNull(),
  /** Versioned JSON: providerSessionId + id regime + last-observed stamp (spec §3.1). */
  providerLink: text('provider_link').notNull(),
  lastSessionActivityAt: integer('last_session_activity_at'),
  lastSpawnedAt: integer('last_spawned_at'),
  lastResumeOutcome: text('last_resume_outcome', {
    enum: ['loaded', 'replaced-by-new', 'never-resumed'],
  }).notNull(),
  updatedAt: integer('updated_at').notNull(),
});
