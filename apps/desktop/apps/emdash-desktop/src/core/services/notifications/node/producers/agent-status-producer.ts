import { eq } from 'drizzle-orm';
import type { AgentEvent } from '@core/primitives/agents/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { tasks } from '@core/services/app-db/node/schema';
import type { NotificationService } from '../notification-service';
import { agentNotificationInputFromEvent, notificationMapping } from './agent-status-mapping';

export function installAgentStatusNotificationProducer(
  service: NotificationService,
  deps: {
    db: AppDb;
    onAgentEvent(handler: (event: AgentEvent) => void): () => void;
    resolveProviderName(providerId: string): string;
  }
): () => void {
  return deps.onAgentEvent((event) => {
    void publishAgentNotification(service, event, deps.db, deps.resolveProviderName);
  });
}

export async function publishAgentNotification(
  service: Pick<NotificationService, 'publish'>,
  event: AgentEvent,
  db: AppDb,
  resolveProviderName: (providerId: string) => string
): Promise<string | null> {
  const mapping = notificationMapping(event);
  if (!mapping) return null;

  const providerName = event.providerId ? resolveProviderName(event.providerId) : 'Agent';
  const taskName = await getTaskName(db, event.taskId);
  return service.publish(agentNotificationInputFromEvent(event, providerName, taskName, mapping));
}

async function getTaskName(db: AppDb, taskId: string | undefined): Promise<string | null> {
  if (!taskId) return null;
  const [row] = await db
    .select({ name: tasks.name })
    .from(tasks)
    .where(eq(tasks.id, taskId))
    .limit(1);
  return row?.name ?? null;
}
