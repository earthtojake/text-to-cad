import { conversationEvents } from '@core/features/conversations/api/node/conversation-events';
import { conversationWireEvents } from '@core/features/conversations/node/event-host';
import { loadActiveAgentStatusConversationIds } from '@core/features/conversations/node/load-active-agent-status-conversation-ids';
import { renameConversation } from '@core/features/conversations/node/renameConversation';
import { acpAgentStatusBridge } from '@main/core/acp/agent-status-bridge';
import { setAgentStatusConversationEventPublisher } from '@main/core/agent-status/agent-status-service';
import { tuiAgentStatusBridge } from '@main/core/agent-status/tui-agent-status-bridge';
import type { DesktopRuntimes } from '@main/gateway/desktop-runtimes';
import { installDesktopWire, registerDesktopWireControllers } from '@main/gateway/desktop-wire';
import { appScope } from '../../core/app-scope';
import type { ControllersBundle } from './controllers';
import type { DatabaseBundle } from './database';
import type { ServicesBundle } from './services';

export function installGateway(
  controllers: ControllersBundle,
  database: DatabaseBundle,
  services: ServicesBundle,
  runtimes: DesktopRuntimes
): void {
  installDesktopWire();
  registerDesktopWireControllers(controllers);
  acpAgentStatusBridge.initialize(
    (handler) => conversationEvents.on('conversation:created', handler),
    {
      runtimes: runtimes.broker,
      onLocalWorkerStateChanged: runtimes.workers.acp.onStateChanged.bind(runtimes.workers.acp),
      loadActiveConversationIds: (host) =>
        loadActiveAgentStatusConversationIds(database.db, host, 'acp'),
      renameConversation: (conversationId, name) =>
        renameConversation(
          {
            db: database.db,
            runtimes: runtimes.broker,
            hostIsReachable: services.hostIsReachable,
          },
          conversationId,
          name
        ),
    }
  );
  const publishConversationEvent = (event: Parameters<typeof conversationWireEvents.emit>[1]) =>
    conversationWireEvents.emit(undefined, event);
  setAgentStatusConversationEventPublisher(publishConversationEvent);
  tuiAgentStatusBridge.initialize({
    runtimes: runtimes.broker,
    onLocalWorkerStateChanged: runtimes.workers.tuiAgents.onStateChanged.bind(
      runtimes.workers.tuiAgents
    ),
    loadActiveConversationIds: (host) =>
      loadActiveAgentStatusConversationIds(database.db, host, 'pty'),
  });
  appScope.add(
    services.hostAttachments.register({
      label: 'acp-agent-status',
      attach: (host) => acpAgentStatusBridge.attachHost(host),
      detach: (host) => acpAgentStatusBridge.detachHost(host),
    })
  );
  appScope.add(
    services.hostAttachments.register({
      label: 'tui-agent-status',
      attach: (host) => tuiAgentStatusBridge.attachHost(host),
      detach: (host) => tuiAgentStatusBridge.detachHost(host),
    })
  );
}
