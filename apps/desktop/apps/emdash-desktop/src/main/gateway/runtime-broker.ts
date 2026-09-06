import {
  hostRefEquals,
  LOCAL_HOST_REF,
  sshConnectionIdOf,
  type HostRef,
} from '@emdash/core/primitives/host/api';
import {
  RuntimeBroker,
  runtimeHostNotConfigured,
  runtimeHostUnavailable,
  type RuntimeClientSource,
  type RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import { translateHostPreparationError, type HostService } from '@core/services/hosts/node';
import {
  WorkspaceServerProtocolError,
  WorkspaceServerProvisionError,
} from '@core/services/hosts/node/workspace-server';
import type { DesktopRuntimeClients } from './desktop-workers';

export function createDesktopRuntimeBroker(
  clients: DesktopRuntimeClients,
  hosts: HostService
): RuntimeBroker {
  return new RuntimeBroker({
    resolve: (host) => resolveDesktopRuntimeClient(host, clients, hosts),
  });
}

async function resolveDesktopRuntimeClient(
  host: HostRef,
  clients: DesktopRuntimeClients,
  hosts: HostService
): Promise<Result<RuntimeClientSource, RuntimeResolveError>> {
  if (!hostRefEquals(host, LOCAL_HOST_REF)) {
    const connectionId = sshConnectionIdOf(host);
    if (connectionId) {
      try {
        const connection = await hosts.client(connectionId);
        return ok(
          connection.connection
            ? { client: connection.client, connection: connection.connection }
            : connection.client
        );
      } catch (error) {
        if (
          error instanceof WorkspaceServerProvisionError ||
          error instanceof WorkspaceServerProtocolError
        ) {
          return err(translateHostPreparationError(host, 'handshaking', error));
        }
        return err(
          runtimeHostUnavailable(
            host,
            error instanceof Error ? error.message : 'Remote workspace server is unavailable'
          )
        );
      }
    }
    return err(
      host.type === 'remote'
        ? runtimeHostUnavailable(host, 'Remote runtime sessions are not enabled')
        : runtimeHostNotConfigured(host, `Local runtime host '${host.id}' is not configured`)
    );
  }

  return ok({
    git: clients.git,
    fileSearch: clients.fileSearch,
    files: clients.files,
    acp: clients.acp,
    conversations: clients.conversations,
    tuiAgents: clients.tuiAgents,
    agentConfig: clients.agentConfig,
    terminals: clients.terminals,
    workspaceRegistry: clients.workspaceRegistry,
    resourceUsage: clients.resourceUsage,
    hostDependencies: clients.hostDependencies,
    hostSettings: clients.hostSettings,
    scripts: clients.scripts,
  });
}
