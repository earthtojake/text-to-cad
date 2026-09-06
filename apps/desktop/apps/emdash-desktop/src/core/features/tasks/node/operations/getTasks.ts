import { and, count, desc, eq, inArray, isNull } from 'drizzle-orm';
import { conversationRegistryTable as conversations } from '@core/features/conversations/api/node/registry';
import {
  mapAutomationRunRowToMeta,
  mapTaskRowToTask,
} from '@core/features/tasks/api/node/utils/utils';
import {
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import { type Task } from '@core/primitives/tasks/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { tasks } from '@core/services/app-db/node/schema';
import { getRunProjectionsByRunIds } from './automation-history';

export async function getTasks(db: AppDb, projectId?: string): Promise<Task[]> {
  const rows = projectId
    ? await db
        .select()
        .from(tasks)
        .where(and(eq(tasks.projectId, projectId), isNull(tasks.deletedAt)))
        .orderBy(desc(tasks.updatedAt))
    : await db.select().from(tasks).where(isNull(tasks.deletedAt)).orderBy(desc(tasks.updatedAt));

  if (rows.length === 0) return [];

  const taskIds = rows.map((r) => r.id);
  const runIds = rows.flatMap((row) => (row.automationRunId ? [row.automationRunId] : []));

  const convRows = await db
    .select({
      taskId: conversations.taskId,
      provider: conversations.provider,
      count: count(),
    })
    .from(conversations)
    .where(inArray(conversations.taskId, taskIds))
    .groupBy(conversations.taskId, conversations.provider);

  const convByTask = new Map<string, Record<string, number>>();
  for (const { taskId, provider, count: c } of convRows) {
    if (taskId === null) continue;
    const rec = convByTask.get(taskId) ?? {};
    rec[provider ?? 'unknown'] = c;
    convByTask.set(taskId, rec);
  }

  const wsIds = rows.map((r) => r.workspaceId).filter((id): id is string => id != null);
  const wsRows = wsIds.length
    ? await db
        .select({
          id: workspaces.id,
          observedGit: workspaces.observedGit,
        })
        .from(workspaces)
        .where(and(inArray(workspaces.id, wsIds), liveWorkspaces()))
    : [];
  const wsByWsId = new Map(wsRows.map((r) => [r.id, r]));
  const runProjections = await getRunProjectionsByRunIds(db, runIds);
  const runMetaByRunId = new Map(
    runProjections.map((row) => [row.id, mapAutomationRunRowToMeta(row)])
  );

  return rows.map((row) => {
    const ws = row.workspaceId ? wsByWsId.get(row.workspaceId) : undefined;
    return {
      ...mapTaskRowToTask(
        row,
        [],
        convByTask.get(row.id) ?? {},
        row.automationRunId ? runMetaByRunId.get(row.automationRunId) : undefined
      ),
      workspaceGit: workspaceGitStats(ws),
    };
  });
}

function workspaceGitStats(
  workspace:
    | { observedGit: { diffStats: { added: number; deleted: number } | null } | null }
    | undefined
): Task['workspaceGit'] {
  const diffStats = workspace?.observedGit?.diffStats;
  return diffStats ? { linesAdded: diffStats.added, linesDeleted: diffStats.deleted } : undefined;
}
