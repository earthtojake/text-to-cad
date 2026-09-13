import crypto from 'node:crypto';
import net from 'node:net';
import type { HostDependenciesContract } from '@emdash/core/services/host-dependencies/api';
import {
  negotiateProtocol,
  PROTOCOL_VERSION,
  workspaceWireContract,
} from '@emdash/core/workspace-server';
import { err, ok } from '@emdash/shared';
import { createController, forwardContractImpl, type ContractImpl } from '@emdash/wire/rpc';
import type { ContractClient } from '@emdash/wire/rpc';
import type { WorkspaceServerRuntimeClients } from '../gateway/workspace-workers';

export type WorkspaceWireControllerDeps = {
  runtimes: WorkspaceServerRuntimeClients;
  hostDependencies: ContractClient<HostDependenciesContract>;
  appVersion?: string;
  daemonId?: string;
  startedAt?: number;
};

const defaultStartedAt = Date.now();
const defaultDaemonId = crypto.randomUUID();
export function createWorkspaceWireController(deps: WorkspaceWireControllerDeps) {
  const appVersion = deps.appVersion ?? '0.0.0';
  const daemonId = deps.daemonId ?? defaultDaemonId;
  const startedAt = deps.startedAt ?? defaultStartedAt;

  return createController(workspaceWireContract, {
    health: () => ({
      status: 'ok' as const,
      version: appVersion,
      uptimeMs: Date.now() - startedAt,
      protocolVersion: PROTOCOL_VERSION,
    }),
    initialize: ({ protocolVersion }) => {
      const result = negotiateProtocol(protocolVersion, PROTOCOL_VERSION);
      if (!result.compatible) {
        return err({
          type: 'protocol-incompatible' as const,
          action: result.action,
          clientProtocolVersion: result.clientProtocolVersion,
          serverProtocolVersion: result.serverProtocolVersion,
        });
      }
      return ok({
        protocolVersion: PROTOCOL_VERSION,
        agreedVersion: result.agreedVersion,
        agreedMinor: result.agreedMinor,
        server: {
          appVersion,
          daemonId,
          startedAt,
        },
      });
    },
    acp: forwardContractImpl(workspaceWireContract.acp, deps.runtimes.acp),
    agentConfig: forwardContractImpl(workspaceWireContract.agentConfig, deps.runtimes.agentConfig),
    conversations: forwardContractImpl(
      workspaceWireContract.conversations,
      deps.runtimes.conversations
    ),
    fileSearch: forwardContractImpl(workspaceWireContract.fileSearch, deps.runtimes.fileSearch),
    files: forwardContractImpl(workspaceWireContract.files, deps.runtimes.files),
    git: forwardContractImpl(workspaceWireContract.git, deps.runtimes.git),
    hostSettings: forwardContractImpl(
      workspaceWireContract.hostSettings,
      deps.runtimes.hostSettings
    ),
    scripts: forwardContractImpl(workspaceWireContract.scripts, deps.runtimes.scripts),
    resourceUsage: forwardContractImpl(
      workspaceWireContract.resourceUsage,
      deps.runtimes.resourceUsage
    ),
    terminals: forwardContractImpl(workspaceWireContract.terminals, deps.runtimes.terminals),
    tuiAgents: forwardContractImpl(workspaceWireContract.tuiAgents, deps.runtimes.tuiAgents),
    workspaceRegistry: forwardContractImpl(
      workspaceWireContract.workspaceRegistry,
      deps.runtimes.workspaceRegistry
    ),
    hostDependencies: forwardContractImpl(
      workspaceWireContract.hostDependencies,
      deps.hostDependencies
    ),
    portForwards: createPortForwardsController(),
  });
}

function createPortForwardsController(): NonNullable<
  ContractImpl<typeof workspaceWireContract>['portForwards']
> {
  return {
    inspect: async ({ port }) => {
      try {
        const results = await Promise.all([
          probeLoopbackPort('127.0.0.1', port),
          probeLoopbackPort('::1', port),
        ]);
        const families = results.flatMap((result, index) =>
          result ? ([index === 0 ? 'ipv4' : 'ipv6'] as const) : []
        );
        return ok({
          listening: families.length > 0,
          families,
        });
      } catch (error) {
        return err({
          type: 'io' as const,
          message: error instanceof Error ? error.message : String(error),
        });
      }
    },
  };
}

function probeLoopbackPort(host: string, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    const timeout = setTimeout(() => finish(false), 500);
    const finish = (listening: boolean) => {
      clearTimeout(timeout);
      socket.removeAllListeners();
      socket.destroy();
      resolve(listening);
    };

    socket.once('connect', () => finish(true));
    socket.once('error', () => finish(false));
  });
}
