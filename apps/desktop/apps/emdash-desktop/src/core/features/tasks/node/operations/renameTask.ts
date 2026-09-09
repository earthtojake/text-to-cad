import { err, ok, type Result } from '@emdash/shared';
import { and, eq, isNull, sql } from 'drizzle-orm';
import { mapTaskRowToTask } from '@core/features/tasks/api/node/utils/utils';
import type { RenameTaskError, RenameTaskSuccess } from '@core/primitives/tasks/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { tasks } from '@core/services/app-db/node/schema';

export async function renameTask(
  db: AppDb,
  projectId: string,
  taskId: string,
  newName: string
): Promise<Result<RenameTaskSuccess, RenameTaskError>> {
  const [row] = await db
    .select()
    .from(tasks)
    .where(and(eq(tasks.id, taskId), eq(tasks.projectId, projectId), isNull(tasks.deletedAt)))
    .limit(1);
  if (!row) return err({ type: 'task-not-found', taskId });

  const [updatedRow] = await db
    .update(tasks)
    .set({ name: newName, updatedAt: sql`CURRENT_TIMESTAMP` })
    .where(and(eq(tasks.id, taskId), eq(tasks.projectId, projectId), isNull(tasks.deletedAt)))
    .returning();

  appDbPokes.tasks.poke({ projectId, taskId });
  return ok({ task: mapTaskRowToTask(updatedRow ?? { ...row, name: newName }) });
}
