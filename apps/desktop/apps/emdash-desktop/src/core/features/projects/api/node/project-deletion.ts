import { and, eq, isNull } from 'drizzle-orm';
import type { AppDb, DrizzleTx } from '@core/services/app-db/node/db';
import { projects } from '@core/services/app-db/node/schema';

/**
 * The "project is being deleted" precondition shared by the deletion cascades. The
 * project row tombstones first when a project delete starts (spec §3), so a tombstoned
 * — or already purged — row refuses new deletes racing the cascade. Callable on the
 * plain handle or inside a transaction, so tombstone writes can re-check atomically.
 */
export function projectIsBeingDeleted(db: AppDb | DrizzleTx, projectId: string): boolean {
  return (
    db
      .select({ id: projects.id })
      .from(projects)
      .where(and(eq(projects.id, projectId), isNull(projects.deletedAt)))
      .limit(1)
      .get() === undefined
  );
}
