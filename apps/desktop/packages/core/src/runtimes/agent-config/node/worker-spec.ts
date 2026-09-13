import type { Logger } from '@emdash/shared/logger';
import type { PluginRegistry } from '@emdash/shared/plugins';
import type { ProvidedWireComponentRequirements } from '@emdash/wire/worker';
import type { WireComponentWorkerCreateOptions } from '@emdash/wire/worker';
import type { z } from 'zod';
import type { CLIAgentPluginProvider } from '#services/agent-plugins/api/plugins';
import { type agentConfigComponentConfigSchema, createAgentConfigComponent } from './component';

type AgentConfigComponent = ReturnType<typeof createAgentConfigComponent>;
type AgentConfigWorkerOptions = WireComponentWorkerCreateOptions<
  AgentConfigComponent['requirements'],
  z.infer<typeof agentConfigComponentConfigSchema>
>;

export type AgentConfigWorkerSpecInput = {
  pluginRegistry: PluginRegistry<CLIAgentPluginProvider>;
  executable: string;
  env: NodeJS.ProcessEnv;
  logger?: Logger;
  dependencies: ProvidedWireComponentRequirements<AgentConfigComponent['requirements']>;
};

/**
 * Spawn spec for the agent-config runtime worker. The plugin registry is
 * injected by the embedding app so core stays plugin-free.
 */
export function agentConfigWorkerSpec(
  input: AgentConfigWorkerSpecInput
): readonly [AgentConfigComponent, AgentConfigWorkerOptions] {
  return [
    createAgentConfigComponent({
      pluginRegistry: input.pluginRegistry,
      logger: input.logger,
    }),
    {
      name: 'agent-config',
      executable: input.executable,
      env: input.env,
      dependencies: input.dependencies,
      config: {},
    },
  ];
}
