import type { Scope } from '@emdash/shared/concurrency';
import type { Logger } from '@emdash/shared/logger';
import { MachinesService } from '@core/features/machines/api/node/machines-service';
import type { SshServiceHandle } from '@core/manifests/node/ssh-service-handle';
import type { AppDb } from '@core/services/app-db/node/db';
import { resolveSshConfig } from '@core/services/ssh/node/config/resolve-ssh-config';
import { parseSshConfigFile } from '@core/services/ssh/node/config/sshConfigParser';
import { createProductionSshConnectConfigResolver } from '@core/services/ssh/node/connect/production-connect-config';
import { SshConnectionsModel } from '@core/services/ssh/node/connections-model';
import type { SshCredentialService } from '@core/services/ssh/node/credentials/ssh-credential-service';
import { SshConnectionManager } from '@core/services/ssh/node/lifecycle/ssh-connection-manager';
import { SshService, type SshServiceDeps } from '@core/services/ssh/node/ssh-service';

export interface CreateSshServiceDeps {
  scope: Scope;
  db: AppDb;
  credentials: SshCredentialService;
  logger: Logger;
  telemetry: SshServiceDeps['telemetry'];
}

export function createSshService(deps: CreateSshServiceDeps): SshServiceHandle {
  const scope = deps.scope.child('ssh-service');
  const connections = scope.use(new SshConnectionsModel());
  const resolveConnectConfig = createProductionSshConnectConfigResolver(deps.credentials);
  const manager = new SshConnectionManager({
    publishEvent: (event) => connections.publishEvent(event),
    log: deps.logger,
  });
  const ssh = new SshService({
    db: deps.db,
    manager,
    runtime: connections,
    resolveConnectConfig,
    parseSshConfigFile,
    resolveSshConfig,
    telemetry: deps.telemetry,
    log: deps.logger,
  });
  const machines = new MachinesService({
    db: deps.db,
    credentials: deps.credentials,
    ssh,
    log: deps.logger,
  });

  scope.add(() => manager.disconnectAll());

  let disposePromise: Promise<void> | undefined;
  return {
    ssh,
    machines,
    manager,
    connections,
    dispose() {
      disposePromise ??= scope.dispose();
      return disposePromise;
    },
  };
}
