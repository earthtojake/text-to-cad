import { createPluginRegistry } from '@emdash/shared/plugins';
import { describe, expect, it } from 'vitest';
import type { CLIAgentPluginProvider } from '#services/agent-plugins/api/plugins';
import { SESSION_IDLE_MS } from '#services/session-lifecycle/api';
import { ACP_CONNECTION_IDLE_TTL_MS, acpWorkerSpec, type AcpWorkerSpecInput } from './worker-spec';

describe('acpWorkerSpec', () => {
  it('bakes the session idle window and connection TTL into the config', () => {
    const env = { PATH: '/usr/bin' };
    const [component, options] = acpWorkerSpec({
      pluginRegistry: createPluginRegistry<CLIAgentPluginProvider>(),
      executable: '/w/acp.mjs',
      env,
      dependencies: {} as AcpWorkerSpecInput['dependencies'],
      attachmentsDir: '/data/attachments',
      intentsFilePath: '/data/acp-intents.json',
    });
    expect(component.id).toBe('acp');
    expect(options.name).toBe('acp');
    expect(options.env).toBe(env);
    expect(component.requirements).toHaveProperty('userEnv');
    expect(options.supervision).toBeUndefined();
    expect(component.configSchema.parse(options.config)).toEqual({
      attachmentsDir: '/data/attachments',
      intentsFilePath: '/data/acp-intents.json',
      lifecycle: {
        session: { kind: 'idle-after', outputMs: SESSION_IDLE_MS },
        connectionIdleTtlMs: ACP_CONNECTION_IDLE_TTL_MS,
      },
    });
    expect(SESSION_IDLE_MS).toBe(60 * 60_000);
    expect(ACP_CONNECTION_IDLE_TTL_MS).toBe(120_000);
  });
});
