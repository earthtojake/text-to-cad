import type { MachinesService } from '@core/features/machines/api/node/machines-service';
import type { SshService } from '@core/primitives/ssh/api';
import type { SshConnectionManager } from '@core/primitives/ssh/api/node/ssh-connection-manager';
import type { SshConnectionsModel } from '@core/services/ssh/node/connections-model';

export interface SshServiceHandle {
  readonly ssh: SshService;
  readonly machines: MachinesService;
  readonly manager: SshConnectionManager;
  readonly connections: SshConnectionsModel;
  dispose(): Promise<void>;
}
