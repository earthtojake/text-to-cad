import { createScope } from '@emdash/shared/concurrency';
import { describe, expect, it, vi } from 'vitest';
import type { EnvSource, IExecutionContext } from '#primitives/exec/api';
import type { HostDependencyResolver } from '#primitives/host-dependencies/api';
import type { IAcpBehavior } from '#services/agent-plugins/api/plugins/capabilities/acp';
import type { IAgentAuthBehavior } from '#services/agent-plugins/api/plugins/capabilities/auth';
import type { CanonicalHookEvent } from '#services/agent-plugins/api/plugins/capabilities/hooks';
import type { McpServerRegistration } from '#services/agent-plugins/api/plugins/capabilities/mcp';
import type {
  AgentCommand,
  CommandContext,
} from '#services/agent-plugins/api/plugins/capabilities/prompt';
import { AgentPluginHost, createPluginRegistry, type CLIAgentPluginProvider } from './index';

describe('AgentPluginHost', () => {
  it('resolves supported ACP providers', () => {
    const acpBehavior = {} as IAcpBehavior;
    const host = createHost([
      plugin({
        acp: { kind: 'supported' },
        behavior: { acp: acpBehavior },
      }),
    ]);

    expect(host.resolveAcp('test')).toEqual({ behavior: acpBehavior });
  });

  it('returns null when a provider does not support ACP', () => {
    const host = createHost([plugin()]);

    expect(host.resolveAcp('test')).toBeNull();
  });

  it('resolves auth providers with metadata and behavior', () => {
    const authBehavior: IAgentAuthBehavior = {
      checkStatus: async () => ({ kind: 'unknown' }),
    };
    const host = createHost([
      plugin({
        auth: {
          kind: 'supported',
          methods: [
            {
              kind: 'api-key',
              id: 'api-key',
              name: 'API Key',
              envVars: [{ name: 'TEST_API_KEY', label: 'API key' }],
            },
          ],
        },
        behavior: { auth: authBehavior },
      }),
    ]);

    expect(host.resolveAuthProvider('test')).toEqual({
      name: 'Test Agent',
      auth: {
        kind: 'supported',
        methods: [
          {
            kind: 'api-key',
            id: 'api-key',
            name: 'API Key',
            envVars: [{ name: 'TEST_API_KEY', label: 'API key' }],
          },
        ],
      },
      behavior: authBehavior,
    });
  });

  it('resolves TUI providers with prompt and hook behavior', () => {
    const buildCommand = (_ctx: CommandContext): AgentCommand => ({
      command: 'test',
      args: [],
      env: {},
    });
    const parseHookEvent = (): CanonicalHookEvent => ({ kind: 'ignore' });
    const host = createHost([
      plugin({
        prompt: { kind: 'pty-only' },
        hooks: { kind: 'config', scope: 'workspace', supportedEvents: ['start'] },
        behavior: {
          prompt: { buildCommand },
          hooks: {
            resolveConfigRoots: ({ homeDir }) => [`${homeDir}/.test`],
            readHooks: async () => [],
            writeHooks: async () => [],
            deleteHooks: async () => {},
            getHooksInstalled: async () => false,
            parseHookEvent,
          },
        },
      }),
    ]);

    expect(host.resolveTuiProvider('test')).toEqual({
      name: 'Test Agent',
      prompt: { kind: 'pty-only' },
      hooks: { kind: 'config', scope: 'workspace', supportedEvents: ['start'] },
      buildCommand,
      parseHookEvent,
    });
  });

  it('returns null when a provider has no TUI prompt behavior', () => {
    const host = createHost([plugin()]);

    expect(host.resolveTuiProvider('test')).toBeNull();
  });

  it('builds prompt commands with resolved cli and allowlisted env', async () => {
    const buildCommand = vi.fn(
      (ctx: CommandContext): AgentCommand => ({
        command: ctx.cli,
        args: [ctx.model],
        env: { COMMAND_ENV: '1' },
      })
    );
    const host = createHost([
      plugin({
        behavior: { prompt: { buildCommand } },
      }),
    ]);

    const result = await host.buildPromptCommand('test', {
      autoApprove: false,
      model: 'sonnet',
    });

    expect(result).toMatchObject({
      success: true,
      data: {
        command: 'test',
        args: ['sonnet'],
        env: expect.objectContaining({
          HOME: '/home/test',
          PATH: '/bin',
          COMMAND_ENV: '1',
        }),
      },
    });
  });

  it('builds ACP spawn with allowlisted env merged under caller env', async () => {
    const buildSpawn = vi.fn(({ cwd, cli }: { cwd: string; cli: string }) => ({
      command: cli,
      args: [],
      cwd,
      env: { SPAWN_ENV: 'base', ANTHROPIC_API_KEY: 'plugin-default' },
    }));
    const host = createHost([
      plugin({
        acp: { kind: 'supported' },
        behavior: { acp: { buildSpawn } as unknown as IAcpBehavior },
      }),
    ]);

    const result = await host.buildAcpSpawn('test', {
      cwd: '/work',
      env: { ANTHROPIC_API_KEY: 'user-key', ANTHROPIC_BASE_URL: 'https://proxy' },
    });

    expect(result).toMatchObject({
      success: true,
      data: {
        cwd: '/work',
        env: expect.objectContaining({
          HOME: '/home/test',
          PATH: '/bin',
          SPAWN_ENV: 'base',
          ANTHROPIC_BASE_URL: 'https://proxy',
          // caller (user settings) env wins over allowlist and plugin defaults
          ANTHROPIC_API_KEY: 'user-key',
        }),
      },
    });
  });

  it('binds machine dependencies for auth status checks', async () => {
    const checkStatus = vi.fn(async () => ({ kind: 'authenticated' as const, account: 'ada' }));
    const host = createHost([
      plugin({
        auth: {
          kind: 'supported',
          methods: [
            {
              kind: 'api-key',
              id: 'api-key',
              name: 'API Key',
              envVars: [{ name: 'TEST_API_KEY', label: 'API key' }],
            },
          ],
        },
        behavior: { auth: { checkStatus } },
      }),
    ]);

    await expect(host.checkAuthStatus('test')).resolves.toEqual({
      success: true,
      data: { kind: 'authenticated', account: 'ada' },
    });
    expect(checkStatus).toHaveBeenCalledWith({
      cli: 'test',
      exec: expect.any(Function),
      fs: expect.any(Object),
      env: expect.objectContaining({
        HOME: '/home/test',
        PATH: '/bin',
      }),
    });
  });

  it('binds plugin fs for MCP server reads', async () => {
    const servers: McpServerRegistration[] = [{ name: 'server', command: 'node' }];
    const readServers = vi.fn(async () => servers);
    const host = createHost([
      plugin({
        mcp: { kind: 'supported', scope: 'global', supportedTransports: ['stdio'] },
        behavior: {
          mcp: {
            readServers,
            writeServers: async () => {},
            removeServer: async () => {},
          },
        },
      }),
    ]);

    await expect(host.readMcpServers('test')).resolves.toEqual({ success: true, data: servers });
    expect(readServers).toHaveBeenCalledWith(expect.any(Object));
  });

  it('loads the current user environment for each agent spawn context', async () => {
    let env = { HOME: '/home/test', PATH: '/tools/old' };
    const host = createHost([plugin()], async () => env);

    const before = await host.resolveSpawnContext('test');
    env = { HOME: '/home/test', PATH: '/tools/new' };
    const after = await host.resolveSpawnContext('test');

    expect(before).toMatchObject({ success: true, data: { agentEnv: { PATH: '/tools/old' } } });
    expect(after).toMatchObject({ success: true, data: { agentEnv: { PATH: '/tools/new' } } });
  });
});

function createHost(
  plugins: CLIAgentPluginProvider[],
  env: EnvSource = async () => ({ HOME: '/home/test', PATH: '/bin', UNSAFE_ENV: 'nope' })
): AgentPluginHost {
  const registry = createPluginRegistry<CLIAgentPluginProvider>();
  for (const item of plugins) registry.register(item);
  return new AgentPluginHost({
    scope: createScope({ label: 'test' }),
    registry,
    exec: fakeExec(),
    dependencies: fakeDependencies(),
    fs: memoryFs(),
    env,
    homeDir: '/home/test',
  });
}

function fakeDependencies(): HostDependencyResolver {
  return {
    resolve: async (id) => ({
      success: true,
      data: {
        id,
        command: id,
        path: id,
        realpath: id,
        source: { kind: 'auto' },
      },
    }),
  };
}

function plugin(
  overrides: {
    acp?: { kind: 'none' } | { kind: 'supported' };
    auth?:
      | { kind: 'none' }
      | {
          kind: 'supported';
          methods: [
            {
              kind: 'api-key';
              id: string;
              name: string;
              envVars: [{ name: string; label: string }];
            },
          ];
        };
    prompt?: CLIAgentPluginProvider['capabilities']['prompt'];
    hooks?: CLIAgentPluginProvider['capabilities']['hooks'];
    mcp?: CLIAgentPluginProvider['capabilities']['mcp'];
    behavior?: Partial<CLIAgentPluginProvider['behavior']>;
  } = {}
): CLIAgentPluginProvider {
  return {
    metadata: {
      id: 'test',
      name: 'Test Agent',
      description: 'Test agent',
      websiteUrl: 'https://example.com',
    },
    capabilities: {
      acp: overrides.acp ?? { kind: 'none' },
      auth: overrides.auth ?? { kind: 'none' },
      prompt: overrides.prompt ?? { kind: 'argv' },
      hooks: overrides.hooks ?? { kind: 'none' },
      mcp: overrides.mcp ?? { kind: 'none' },
      hostDependency: {
        binaryNames: ['test'],
        installCommands: {},
        updates: { kind: 'none' },
      },
    },
    behavior: overrides.behavior ?? {},
  } as unknown as CLIAgentPluginProvider;
}

function fakeExec(): IExecutionContext {
  return {
    supportsLocalSpawn: false,
    async exec() {
      throw new Error('missing');
    },
    async execStreaming() {
      return { exitCode: 0 };
    },
    dispose() {},
  };
}

function memoryFs() {
  return {
    async read() {
      return null;
    },
    async write() {},
    async delete() {},
    async exists() {
      return false;
    },
    async list() {
      return [];
    },
  };
}
