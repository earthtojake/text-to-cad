import { and, eq } from 'drizzle-orm';
import { conversationRegistryTable as conversations } from '@core/features/conversations/api/node/registry';
import type { AppDb } from '@core/services/app-db/node/db';
import { terminals } from '@core/services/app-db/node/schema';

export type TaskSessionLeafIds = {
  conversationIds: string[];
  terminalIds: string[];
};

export async function getTaskSessionLeafIds(
  db: AppDb,
  projectId: string,
  taskId: string
): Promise<TaskSessionLeafIds> {
  const [conversationRows, terminalRows] = await Promise.all([
    db
      .select({ id: conversations.id })
      .from(conversations)
      .where(and(eq(conversations.projectId, projectId), eq(conversations.taskId, taskId))),
    db
      .select({ id: terminals.id })
      .from(terminals)
      .where(and(eq(terminals.projectId, projectId), eq(terminals.taskId, taskId))),
  ]);

  return {
    conversationIds: conversationRows.map((row) => row.id),
    terminalIds: terminalRows.map((row) => row.id),
  };
}

/**
 * All conversation and terminal leaf ids for a project, across every task.
 * Used by the tmux reaper to compute the set of PTY sessions that are still
 * "wanted" — a tmux session whose leaf id is absent here no longer maps to any
 * DB-tracked entity and is safe to reap. No archived filter on purpose: keep the
 * wanted set as broad as possible so a still-resumable session is never reaped.
 */
export async function getProjectSessionLeafIds(
  db: AppDb,
  projectId: string
): Promise<TaskSessionLeafIds> {
  const [conversationRows, terminalRows] = await Promise.all([
    db
      .select({ id: conversations.id })
      .from(conversations)
      .where(eq(conversations.projectId, projectId)),
    db.select({ id: terminals.id }).from(terminals).where(eq(terminals.projectId, projectId)),
  ]);

  return {
    conversationIds: conversationRows.map((row) => row.id),
    terminalIds: terminalRows.map((row) => row.id),
  };
}
