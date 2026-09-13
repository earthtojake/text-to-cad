import { eq, sql } from 'drizzle-orm';
import { mapTaskRowToTask } from '@core/features/tasks/api/node/utils/utils';
import type { Task } from '@core/primitives/tasks/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { tasks } from '@core/services/app-db/node/schema';

export async function restoreTask(db: AppDb, id: string): Promise<Task | undefined> {
  const [updatedRow] = await db
    .update(tasks)
    .set({
      archivedAt: null,
      updatedAt: sql`CURRENT_TIMESTAMP`,
    })
    .where(eq(tasks.id, id))
    .returning();

  if (updatedRow) appDbPokes.tasks.poke({ projectId: updatedRow.projectId, taskId: id });
  return updatedRow ? mapTaskRowToTask(updatedRow) : undefined;
}
