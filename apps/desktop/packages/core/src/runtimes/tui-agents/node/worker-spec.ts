import type { Logger } from '@emdash/shared/logger';
import type { PluginRegistry } from '@emdash/shared/plugins';
import type { ProvidedWireComponentRequirements } from '@emdash/wire/worker';
import type { WireComponentWorkerCreateOptions } from '@emdash/wire/worker';
import type { z } from 'zod';
import type { CLIAgentPluginProvider } from '#services/agent-plugins/api/plugins';
import { SESSION_IDLE_MS } from '#services/session-lifecycle/api';
import { createTuiAgentsComponent, type tuiAgentsComponentConfigSchema } from './component';

type TuiAgentsComponent = ReturnType<typeof createTuiAgentsComponent>;
type TuiAgentsWorkerOptions = WireComponentWorkerCreateOptions<
  TuiAgentsComponent['requirements'],
  z.infer<typeof tuiAgentsComponentConfigSchema>
>;

export type TuiAgentsWorkerSpecInput = {
  pluginRegistry: PluginRegistry<CLIAgentPluginProvider>;
  executable: string;
  env: NodeJS.ProcessEnv;
  logger?: Logger;
  dependencies: ProvidedWireComponentRequirements<TuiAgentsComponent['requirements']>;
  intentsFilePath: string;
};

/**
 * Spawn spec for the TUI agents session runtime worker. Sessions idle out after
 * SESSION_IDLE_MS without output. The plugin registry is injected by the
 * embedding app so core stays plugin-free.
 */
export function tuiAgentsWorkerSpec(
  input: TuiAgentsWorkerSpecInput
): readonly [TuiAgentsComponent, TuiAgentsWorkerOptions] {
  return [
    createTuiAgentsComponent({
      pluginRegistry: input.pluginRegistry,
      logger: input.logger,
    }),
    {
      name: 'tui-agents',
      executable: input.executable,
      env: input.env,
      dependencies: input.dependencies,
      config: {
        intentsFilePath: input.intentsFilePath,
        lifecycle: {
          session: { kind: 'idle-after', outputMs: SESSION_IDLE_MS },
        },
      },
    },
  ];
}
