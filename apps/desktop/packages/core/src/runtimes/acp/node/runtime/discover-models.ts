import type { Client } from '@agentclientprotocol/sdk';
import { type Scope } from '@emdash/shared/concurrency';
import { runWithTimeout } from '@emdash/shared/scheduling';
import { z } from 'zod';
import type { ModelChoice } from '#runtimes/acp/api/models/config';
import { deriveConfigGroups } from '#runtimes/acp/api/reducer/config-derive';
import { createAcpAgentConnection } from '../connection/acp-agent-connection';
import type { AcpRuntimeDeps } from './types';

/** Read the installed provider's catalog without sending a prompt or creating an app task. */
export async function discoverModels(
  deps: Pick<AcpRuntimeDeps, 'agentHost' | 'host' | 'logger'>,
  parentScope: Scope,
  input: { providerId: string; env?: Record<string, string> },
  timeoutMs = 15_000
): Promise<ModelChoice[]> {
  const scope = parentScope.child('model-discovery');
  try {
    return await runWithTimeout(
      async () => {
        const binding = deps.agentHost.resolveAcp(input.providerId);
        if (!binding) throw new Error('This provider does not support model discovery');
        const cwd = deps.agentHost.homeDir;
        const spawn = await deps.agentHost.buildAcpSpawn(input.providerId, { cwd, env: input.env });
        if (!spawn.success) throw new Error(`Could not start provider: ${spawn.error.type}`);
        if (scope.disposed) throw new Error('Model discovery cancelled');
        const client: Client = {
          sessionUpdate: async () => {},
          requestPermission: async () => ({ outcome: { outcome: 'cancelled' } }),
        };
        const connection = await createAcpAgentConnection(
          { host: deps.host, behavior: binding.behavior, logger: deps.logger },
          {
            providerId: input.providerId,
            spawn: spawn.data,
            scope,
            clientCapabilities: {},
            buildClient: () => client,
            onClosed: () => {},
          }
        );
        if (!connection.success)
          throw new Error('Could not connect to provider for model discovery');
        if (scope.disposed) throw new Error('Model discovery cancelled');
        const response = await connection.data.agent.newSession({ cwd, mcpServers: [] });
        const models = deriveConfigGroups(response.configOptions ?? []).modelOptions;
        // Older ACP adapters expose models on the session response instead of configOptions.
        const legacy = z
          .object({
            models: z.object({
              availableModels: z.array(
                z.object({
                  modelId: z.string(),
                  name: z.string(),
                  description: z.string().nullish(),
                })
              ),
            }),
          })
          .safeParse(response);
        return (
          models?.available ??
          (legacy.success
            ? legacy.data.models.availableModels.map((model) => ({
                id: model.modelId,
                name: model.name,
                ...(model.description ? { description: model.description } : {}),
              }))
            : [])
        );
      },
      { timeoutMs, signal: scope.signal }
    );
  } finally {
    await scope.dispose();
  }
}
