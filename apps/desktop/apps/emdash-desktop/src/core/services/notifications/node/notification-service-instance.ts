import type { AgentEvent } from '@core/primitives/agents/api';
import type { NotificationSettings } from '@core/primitives/app-settings/api';
import type { AppDb } from '@core/services/app-db/node/db';
import type { EmitNotificationDelivery, NotificationSink } from '../api/ports';
import { NotificationService, type NotificationServiceDeps } from './notification-service';
import { installAgentStatusNotificationProducer } from './producers';
import { createSoundNotificationSink } from './sinks';
import { SqliteNotificationStore } from './sqlite-store';

export type CreateNotificationServiceDeps = {
  db: AppDb;
  settings: {
    get(key: 'notifications'): Promise<NotificationSettings>;
  };
  resolveProviderName(providerId: string): string;
  isAppFocused(): boolean;
  onAgentEvent(handler: (event: AgentEvent) => void): () => void;
  logger?: NotificationServiceDeps['logger'];
  createSystemSink?: (emitDelivery: EmitNotificationDelivery) => NotificationSink;
};

export function createNotificationService(
  deps: CreateNotificationServiceDeps
): NotificationService {
  const service = new NotificationService({
    store: new SqliteNotificationStore(deps.db),
    logger: deps.logger,
    async routingContext() {
      return {
        appFocused: deps.isAppFocused(),
        settings: await deps.settings.get('notifications'),
      };
    },
  });

  if (deps.createSystemSink) {
    service.registerSink(deps.createSystemSink((event) => service.emitDelivery(event)));
  }
  service.registerSink(createSoundNotificationSink((event) => service.emitDelivery(event)));
  service.registerDisposer(
    installAgentStatusNotificationProducer(service, {
      db: deps.db,
      onAgentEvent: deps.onAgentEvent,
      resolveProviderName: deps.resolveProviderName,
    })
  );

  return service;
}
