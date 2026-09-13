import type { CommandContext, PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import { describe, expect, it } from 'vitest';
import { provider } from './index';

const baseContext: CommandContext = {
  cli: 'codebuddy',
  autoApprove: false,
  initialPrompt: undefined,
  sessionId: '550e8400-e29b-41d4-a716-446655440000',
  providerSessionId: undefined,
  isResuming: false,
  model: '',
};

function build(context: Partial<CommandContext> = {}) {
  return provider.behavior.prompt!.buildCommand({ ...baseContext, ...context });
}

function createMemoryFs(files = new Map<string, string>()): PluginFs {
  return {
    read: async (path) => files.get(path) ?? null,
    write: async (path, content) => {
      files.set(path, content);
    },
    delete: async (path) => {
      files.delete(path);
    },
    exists: async (path) => files.has(path),
    list: async () => [],
  };
}

describe('codebuddy provider', () => {
  it('registers the documented npm package, binary aliases, and capabilities', () => {
    expect(provider.capabilities.hostDependency.binaryNames).toEqual(['codebuddy', 'cbc']);
    expect(provider.capabilities.hostDependency.installDocs).toBe(
      'https://www.codebuddy.ai/docs/cli/quickstart'
    );
    expect(provider.capabilities.acp.kind).toBe('supported');
    expect(provider.capabilities.autoApprove.kind).toBe('supported');
    expect(provider.capabilities.mcp).toEqual({
      kind: 'supported',
      scope: 'global',
      supportedTransports: ['stdio', 'http'],
    });
    expect(provider.capabilities.sessions.kind).toBe('resumable');
  });

  it('starts the documented stdio ACP transport', () => {
    expect(
      provider.behavior.acp!.buildSpawn({
        cli: 'codebuddy',
        cwd: '/tmp/project',
        env: {},
      })
    ).toEqual({
      command: 'codebuddy',
      args: ['--acp'],
    });
  });

  it('starts a deterministic session with an initial prompt, model, and auto-approval', () => {
    expect(
      build({
        autoApprove: true,
        initialPrompt: 'Fix the bug',
        model: 'gpt-5.5',
      })
    ).toEqual({
      command: 'codebuddy',
      args: [
        '--session-id',
        '550e8400-e29b-41d4-a716-446655440000',
        '--dangerously-skip-permissions',
        '--model',
        'gpt-5.5',
        'Fix the bug',
      ],
      env: {},
    });
  });

  it('resumes the deterministic session without replaying its initial prompt', () => {
    expect(
      build({
        cli: 'cbc',
        autoApprove: true,
        initialPrompt: 'Do not replay this prompt',
        isResuming: true,
      })
    ).toEqual({
      command: 'cbc',
      args: ['--resume', '550e8400-e29b-41d4-a716-446655440000', '--dangerously-skip-permissions'],
      env: {},
    });
  });

  it('writes stdio and HTTP MCP servers using CodeBuddy native transport fields', async () => {
    const files = new Map<string, string>();
    const fs = createMemoryFs(files);

    await provider.behavior.mcp!.writeServers(fs, [
      {
        name: 'local-tools',
        transport: 'stdio',
        command: 'node',
        args: ['server.js'],
      },
      {
        name: 'docs',
        transport: 'http',
        type: 'http',
        url: 'https://example.com/mcp',
        headers: { Authorization: 'Bearer token' },
      },
    ]);

    expect(JSON.parse(files.get('.codebuddy/.mcp.json')!)).toEqual({
      mcpServers: {
        'local-tools': { type: 'stdio', command: 'node', args: ['server.js'] },
        docs: {
          type: 'http',
          url: 'https://example.com/mcp',
          headers: { Authorization: 'Bearer token' },
        },
      },
    });
  });
});
