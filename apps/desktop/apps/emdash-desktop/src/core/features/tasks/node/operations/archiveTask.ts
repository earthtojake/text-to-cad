import { log } from '@emdash/shared/logger';
import { and, eq, isNull, sql } from 'drizzle-orm';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { tasks } from '@core/services/app-db/node/schema';

export async function archiveTask(
  db: AppDb,
  taskSessionManager: Pick<TaskSessionManager, 'forceRemoveTask' | 'teardownTask'>,
  projectId: string,
  taskId: string,
  telemetry: Pick<TelemetryService, 'capture'>
): Promise<void> {
  const [task] = await db
    .select()
    .from(tasks)
    .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)))
    .limit(1);
  if (!task) return;

  await db
    .update(tasks)
    .set({
      archivedAt: sql`CURRENT_TIMESTAMP`,
      updatedAt: sql`CURRENT_TIMESTAMP`,
    })
    .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)));
  appDbPokes.tasks.poke({ projectId, taskId });
  telemetry.capture('task_archived', { project_id: projectId, task_id: taskId });

  // 'archive' reaps the tmux session + agent process but keeps the worktree and the
  // persisted session id, so Restore can resume. Plain 'detach' would leak the tmux
  // session indefinitely (#2689).
  const teardownResult = await taskSessionManager.teardownTask(taskId, 'archive').catch((e) => {
    log.warn('archiveTask: teardown failed', { taskId, error: String(e) });
    return null;
  });

  if (teardownResult && !teardownResult.success) {
    log.warn('archiveTask: teardown failed', { taskId, error: teardownResult.error.message });
  }

  if (!teardownResult || !teardownResult.success) {
    await taskSessionManager.forceRemoveTask(
      taskId,
      'archiveTask continued after teardown failure'
    );
  }
}
