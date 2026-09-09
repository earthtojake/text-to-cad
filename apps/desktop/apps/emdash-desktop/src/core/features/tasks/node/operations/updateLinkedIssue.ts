import { and, eq, isNull } from 'drizzle-orm';
import { mapTaskRowToTask } from '@core/features/tasks/api/node/utils/utils';
import type { LinkedIssue } from '@core/primitives/linked-issues/api';
import type { Task } from '@core/primitives/tasks/api';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { tasks } from '@core/services/app-db/node/schema';

export async function updateLinkedIssue(
  db: AppDb,
  taskId: string,
  issue: LinkedIssue | undefined,
  telemetry: Pick<TelemetryService, 'capture'>
): Promise<Task | undefined> {
  const [existingRow] = await db
    .select({ id: tasks.id, projectId: tasks.projectId })
    .from(tasks)
    .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)))
    .limit(1);
  if (!existingRow) return undefined;

  const [updatedRow] = await db
    .update(tasks)
    .set({
      linkedIssue: issue ?? null,
    })
    .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)))
    .returning();

  if (issue) {
    telemetry.capture('issue_linked_to_task', {
      provider: issue.provider,
      project_id: existingRow.projectId,
      task_id: existingRow.id,
    });
  }

  if (updatedRow) appDbPokes.tasks.poke({ projectId: existingRow.projectId, taskId });
  return updatedRow ? mapTaskRowToTask(updatedRow) : undefined;
}
