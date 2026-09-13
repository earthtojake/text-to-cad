import { sshConnectionIdOf, type HostRef } from '@emdash/core/primitives/host/api';
import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { err, ok, type Result } from '@emdash/shared';
import type { LiveModelProvider, LiveSource } from '@emdash/wire/rpc';
import { createController, type CallMeta, type Controller } from '@emdash/wire/rpc';
import type { AgentOperations } from '@core/features/agents/node/controller';
import { forwardLiveModel } from '@core/services/runtime-clients/node/forward-live-model';
import { agentsContract } from '../api';
import {
  throwAgentsRuntimeResolveError,
  type AgentsDependencyId as DependencyId,
  type AgentsHostRuntimesClient as HostRuntimesClient,
  type AgentsRuntimeBroker,
  type AgentsRuntimeResolveError as RuntimeResolveError,
} from '../api/runtime-adapter';

export type CreateAgentsWireControllerOptions = Readonly<{
  operations: AgentOperations;
  runtimes: AgentsRuntimeBroker;
}>;

export function createAgentsWireController(options: CreateAgentsWireControllerOptions): Controller {
  const agentOperations = options.operations;
  return createController(agentsContract, {
    discoverModels: ({ host, providerId }, meta) =>
      withHostRuntime(options.runtimes, host, async (runtime) => {
        const settings = await agentOperations.getSettings(providerId);
        return runtime.acp.discoverModels(
          { providerId, env: settings.value.env },
          callOptions(meta)
        );
      }),
    listMetadata: () => agentOperations.listMetadata(),
    list: ({ host }) =>
      withHostRuntime(options.runtimes, host, (runtime) =>
        agentOperations.list(sshConnectionIdOf(host), runtime.hostDependencies)
      ),
    get: ({ host, id }) =>
      withHostRuntime(options.runtimes, host, (runtime) =>
        agentOperations.get(id, sshConnectionIdOf(host), runtime.hostDependencies)
      ),
    listAgentInstallationStatus: ({ host }) =>
      withHostRuntime(options.runtimes, host, (runtime) =>
        agentOperations.listAgentInstallationStatus(
          sshConnectionIdOf(host),
          runtime.hostDependencies
        )
      ),
    install: {
      run: async ({ host, id, method, elevate }, context) => {
        const runtime = await options.runtimes.client(host);
        if (!runtime.success) return err(runtime.error);
        return await agentOperations.install(
          id as AgentProviderId,
          sshConnectionIdOf(host),
          method,
          elevate,
          runtime.data.hostDependencies,
          context
        );
      },
      toError: toAgentOperationError,
    },
    update: {
      run: async ({ host, id, method, elevate }, context) => {
        const runtime = await options.runtimes.client(host);
        if (!runtime.success) return err(runtime.error);
        return await agentOperations.update(
          id as AgentProviderId,
          sshConnectionIdOf(host),
          method,
          elevate,
          runtime.data.hostDependencies,
          context
        );
      },
      toError: toAgentOperationError,
    },
    uninstall: ({ host, id, method }) =>
      withHostRuntime(options.runtimes, host, () =>
        agentOperations.uninstall(id as AgentProviderId, sshConnectionIdOf(host), method)
      ),
    getDefaultSettings: ({ host, id }) =>
      withHostRuntime(options.runtimes, host, () => agentOperations.getDefaultSettings(id)),
    getSettings: ({ host, id }) =>
      withHostRuntime(options.runtimes, host, () => agentOperations.getSettings(id)),
    updateSettings: ({ host, id, config }) =>
      withHostRuntime(options.runtimes, host, () => agentOperations.updateSettings(id, config)),
    setUsedInstallation: ({ host, id, selection }) =>
      withHostRuntime(options.runtimes, host, (runtime) =>
        agentOperations.setUsedInstallation(
          id as DependencyId,
          sshConnectionIdOf(host),
          selection,
          runtime.hostDependencies
        )
      ),
    probeOverride: ({ host, id, selection }) =>
      withHostRuntime(options.runtimes, host, () =>
        agentOperations.probeOverride(id as DependencyId, selection, sshConnectionIdOf(host))
      ),
    refreshLatestVersion: ({ host, id }) =>
      withHostRuntime(options.runtimes, host, () =>
        agentOperations.refreshLatestVersion(id as DependencyId, sshConnectionIdOf(host))
      ),
    probeAll: ({ host }) =>
      withHostRuntime(options.runtimes, host, (runtime) =>
        agentOperations.probeAll(sshConnectionIdOf(host), runtime.hostDependencies)
      ),

    auth: createAuthModelProvider(options.runtimes),
    hooksStatus: ({ host, providerId }, meta) =>
      withHostRuntime(options.runtimes, host, (runtime) =>
        runtime.agentConfig.hooksStatus({ providerId }, callOptions(meta))
      ),
    startLogin: (input, meta) =>
      withAgentConfigResult(options.runtimes, input.host, (client) =>
        client.startLogin(withoutHost(input), callOptions(meta))
      ),
    cancelLogin: (input, meta) =>
      withAgentConfigResult(options.runtimes, input.host, (client) =>
        client.cancelLogin(withoutHost(input), callOptions(meta))
      ),
    sendLoginInput: (input, meta) =>
      withAgentConfigResult(options.runtimes, input.host, (client) =>
        client.sendLoginInput(withoutHost(input), callOptions(meta))
      ),
    resizeLogin: (input, meta) =>
      withAgentConfigResult(options.runtimes, input.host, (client) =>
        client.resizeLogin(withoutHost(input), callOptions(meta))
      ),
    markUrlHandled: (input, meta) =>
      withAgentConfigResult(options.runtimes, input.host, (client) =>
        client.markUrlHandled(withoutHost(input), callOptions(meta))
      ),
    refreshAuthStatus: (input, meta) =>
      withAgentConfigResult(options.runtimes, input.host, (client) =>
        client.refreshAuthStatus(withoutHost(input), callOptions(meta))
      ),
    loginOutput: async ({ host, providerId }) =>
      resolveRuntimeSource(options.runtimes, host, (runtime) =>
        runtime.agentConfig.loginOutput.handle({ providerId }).asLiveSource()
      ),
  });
}

function createAuthModelProvider(
  runtimes: AgentsRuntimeBroker
): LiveModelProvider<typeof agentsContract.auth> {
  return forwardLiveModel(agentsContract.auth, (key, name) =>
    resolveRuntimeSource(runtimes, key.host, (runtime) =>
      runtime.agentConfig.agents.state(undefined, name).asLiveSource()
    )
  );
}

async function withHostRuntime<T>(
  runtimes: AgentsRuntimeBroker,
  host: HostRef,
  work: (client: HostRuntimesClient) => Promise<T> | T
): Promise<Result<T, RuntimeResolveError>> {
  const runtime = await runtimes.client(host);
  if (!runtime.success) return err(runtime.error);
  return ok(await work(runtime.data));
}

async function withAgentConfigResult<T, E>(
  runtimes: AgentsRuntimeBroker,
  host: HostRef,
  work: (client: HostRuntimesClient['agentConfig']) => Promise<Result<T, E>>
): Promise<Result<T, E | RuntimeResolveError>> {
  const runtime = await runtimes.client(host);
  if (!runtime.success) return err(runtime.error);
  return await work(runtime.data.agentConfig);
}

async function resolveRuntimeSource(
  runtimes: AgentsRuntimeBroker,
  host: HostRef,
  source: (client: HostRuntimesClient) => LiveSource
): Promise<LiveSource> {
  const runtime = await runtimes.client(host);
  if (!runtime.success) throwAgentsRuntimeResolveError(runtime.error);
  return source(runtime.data);
}

function withoutHost<T extends { host: HostRef }>(input: T): Omit<T, 'host'> {
  const { host: _, ...rest } = input;
  return rest;
}

function callOptions(meta: CallMeta): { signal?: AbortSignal } {
  return meta.signal ? { signal: meta.signal } : {};
}

function toAgentOperationError(error: unknown) {
  return {
    type: 'command-failed' as const,
    message: error instanceof Error ? error.message : String(error),
    output: '',
  };
}
