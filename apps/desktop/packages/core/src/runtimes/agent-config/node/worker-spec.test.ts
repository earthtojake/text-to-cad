import { createPluginRegistry } from '@emdash/shared/plugins';
import { describe, expect, it } from 'vitest';
import type { CLIAgentPluginProvider } from '#services/agent-plugins/api/plugins';
import { agentConfigWorkerSpec, type AgentConfigWorkerSpecInput } from './worker-spec';

describe('agentConfigWorkerSpec', () => {
  it('produces the agent-config spec with default supervision and empty config', () => {
    const env = { PATH: '/usr/bin' };
    const [component, options] = agentConfigWorkerSpec({
      pluginRegistry: createPluginRegistry<CLIAgentPluginProvider>(),
      executable: '/w/agent-config.mjs',
      env,
      dependencies: {} as AgentConfigWorkerSpecInput['dependencies'],
    });
    expect(component.id).toBe('agent-config');
    expect(options.name).toBe('agent-config');
    expect(options.env).toBe(env);
    expect(component.requirements).toHaveProperty('userEnv');
    expect(options.supervision).toBeUndefined();
    expect(options.shutdownGraceMs).toBeUndefined();
    expect(component.configSchema.parse(options.config)).toEqual({});
  });
});
