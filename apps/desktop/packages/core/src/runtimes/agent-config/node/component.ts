import os from 'node:os';
import type { Logger } from '@emdash/shared/logger';
import type { PluginRegistry } from '@emdash/shared/plugins';
import { defineWireComponent, requireContract } from '@emdash/wire/worker';
import { z } from 'zod';
import { agentConfigContract } from '#runtimes/agent-config/api';
import { createAgentConfigController } from '#runtimes/agent-config/node/api/controller';
import { AgentConfigRuntime } from '#runtimes/agent-config/node/runtime/runtime';
import { AgentPluginHost, type CLIAgentPluginProvider } from '#services/agent-plugins/api/plugins';
import { createLocalPluginFs } from '#services/agent-plugins/api/plugins/helpers';
import { NodeExecutionContext } from '#services/exec/api';
import {
  createHostDependencyResolverFromDependency,
  hostDependencyResolverContract,
} from '#services/host-dependencies/node';
import { NodePtySpawner } from '#services/pty/node';
import { userShellEnvContract } from '#services/shell-env/api';

export const agentConfigComponentConfigSchema = z.object({});

export type CreateAgentConfigComponentOptions = {
  pluginRegistry: PluginRegistry<CLIAgentPluginProvider>;
  logger?: Logger;
};

export function createAgentConfigComponent(options: CreateAgentConfigComponentOptions) {
  return defineWireComponent({
    id: 'agent-config',
    contract: agentConfigContract,
    requirements: {
      hostDependencies: requireContract(hostDependencyResolverContract),
      userEnv: requireContract(userShellEnvContract),
    },
    configSchema: agentConfigComponentConfigSchema,
    create: ({ dependencies, instance, logger, scope }) => {
      const env = () => dependencies.userEnv.get();
      const runtimeLogger = options.logger ?? logger;
      const homeDir = os.homedir();
      const spawner = new NodePtySpawner();
      const exec = new NodeExecutionContext({ env });
      const dependencyResolver = createHostDependencyResolverFromDependency(
        dependencies.hostDependencies
      );
      const agentHost = new AgentPluginHost({
        scope,
        registry: options.pluginRegistry,
        exec,
        dependencies: dependencyResolver,
        fs: createLocalPluginFs(homeDir),
        env,
        homeDir,
      });
      const runtime = new AgentConfigRuntime({
        scope,
        agentHost,
        ptySpawner: spawner,
        logger: runtimeLogger,
      });

      return instance({
        scope,
        controller: createAgentConfigController(runtime),
      });
    },
  });
}
