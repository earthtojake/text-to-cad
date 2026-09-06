import { and, eq, isNull, sql } from 'drizzle-orm';
import { type TaskLifecycleStatus } from '@core/primitives/tasks/api';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { tasks } from '@core/services/app-db/node/schema';

export async function updateTaskStatus(
  db: AppDb,
  taskId: string,
  status: TaskLifecycleStatus,
  telemetry: Pick<TelemetryService, 'capture'>
): Promise<void> {
  const [row] = await db
    .select()
    .from(tasks)
    .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)))
    .limit(1);
  if (!row) throw new Error(`Task not found: ${taskId}`);
  if (row.status === status) return;

  await db
    .update(tasks)
    .set({
      status,
      updatedAt: sql`CURRENT_TIMESTAMP`,
      statusChangedAt: sql`CURRENT_TIMESTAMP`,
    })
    .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)));

  appDbPokes.tasks.poke({ projectId: row.projectId, taskId });
  telemetry.capture('task_status_changed', {
    from_status: row.status as TaskLifecycleStatus,
    to_status: status,
    project_id: row.projectId,
    task_id: row.id,
  });
}
