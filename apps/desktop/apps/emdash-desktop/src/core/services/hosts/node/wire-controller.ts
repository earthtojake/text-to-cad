import { sshConnectionIdOf } from '@emdash/core/primitives/host/api';
import { createController, type Controller } from '@emdash/wire/rpc';
import type { SshService } from '@core/primitives/ssh/api';
import { hostsContract } from '../api';
import type { HostAvailabilityService } from './availability';
import type { HostService } from './host-service';

export function createHostsWireController(
  service: HostService,
  availability: HostAvailabilityService,
  ssh: Pick<SshService, 'disconnect'>
): Controller {
  return createController(hostsContract, {
    availability: availability.host,
    disconnect: async ({ host }) => {
      const connectionId = sshConnectionIdOf(host);
      if (!connectionId) throw new Error('Local Host does not support SSH Disconnect');
      availability.suspend(host);
      await ssh.disconnect(connectionId);
    },
    requestReady: ({ host, cause }) => availability.requestReady(host, cause),
    wake: ({ cause }) => availability.wakeDemanded(cause),
    serverStates: service.stateModel.host,
    refreshServerState: ({ connectionId, force }) =>
      service.refreshServerState(connectionId, { force }),
    installServer: ({ connectionId }) => service.installServer(connectionId),
    startServer: ({ connectionId }) => service.startServer(connectionId),
    stopServer: ({ connectionId }) => service.stopServer(connectionId),
    restartServer: ({ connectionId }) => service.restartServer(connectionId),
    updateServer: ({ connectionId }) => service.updateServer(connectionId),
  });
}
