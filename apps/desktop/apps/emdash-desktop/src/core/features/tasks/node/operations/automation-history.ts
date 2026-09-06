// Read-only history for tasks created by the retired scheduler.
import { inArray } from 'drizzle-orm';
import type { AppDb } from '@core/services/app-db/node/db';
import { automationRuns, type AutomationRunRow } from '@core/services/app-db/node/schema';

export async function getRunProjectionsByRunIds(
  db: AppDb,
  runIds: readonly string[]
): Promise<AutomationRunRow[]> {
  const uniqueRunIds = [...new Set(runIds)];
  if (uniqueRunIds.length === 0) return [];
  return db.select().from(automationRuns).where(inArray(automationRuns.id, uniqueRunIds));
}
