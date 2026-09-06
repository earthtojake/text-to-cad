import { sql } from 'drizzle-orm';
import { check, integer, sqliteTable, text, uniqueIndex } from 'drizzle-orm/sqlite-core';
import { automationRunStatuses } from '../../api/run';

export const automationDeployments = sqliteTable('automation_deployments', {
  automationId: text('automation_id').primaryKey(),
  enabled: integer('enabled', { mode: 'boolean' }).notNull(),
  payload: text('payload').notNull(),
  deployedAt: integer('deployed_at').notNull(),
});

export const automationRuns = sqliteTable(
  'automation_runs',
  {
    id: text('id').primaryKey(),
    seq: integer('seq').notNull(),
    automationId: text('automation_id').notNull(),
    status: text('status', { enum: automationRunStatuses }).notNull(),
    scheduledAt: integer('scheduled_at'),
    deadlineAt: integer('deadline_at'),
    payload: text('payload').notNull(),
  },
  (t) => [
    uniqueIndex('automation_runs_seq_idx').on(t.seq),
    uniqueIndex('automation_runs_one_scheduled_idx')
      .on(t.automationId)
      .where(sql`${t.status} = 'scheduled'`),
  ]
);

export const automationJournal = sqliteTable(
  'automation_journal',
  {
    singleton: integer('singleton').primaryKey(),
    nextSeq: integer('next_seq').notNull(),
  },
  (t) => [check('automation_journal_singleton_check', sql`${t.singleton} = 1`)]
);
