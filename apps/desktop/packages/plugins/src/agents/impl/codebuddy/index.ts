import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  createMcpAdapter,
  npmDependency,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { createNativeAcpBehavior } from '../../helpers/acp-stdio';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'codebuddy',
    name: 'CodeBuddy Code',
    description:
      "Tencent's terminal coding agent for repository-aware implementation, debugging, and code analysis.",
    websiteUrl: 'https://www.codebuddy.ai/docs/cli/README',
  },
  {
    acp: {
      kind: 'supported',
    },
    autoApprove: {
      kind: 'supported',
    },
    hostDependency: npmDependency({
      id: 'codebuddy',
      package: '@tencent-ai/codebuddy-code',
      binaryNames: ['codebuddy', 'cbc'],
      installDocs: 'https://www.codebuddy.ai/docs/cli/quickstart',
    }),
    mcp: {
      kind: 'supported',
      scope: 'global',
      supportedTransports: ['stdio', 'http'],
    },
    prompt: {
      kind: 'argv',
      flag: '',
    },
    sessions: {
      kind: 'resumable',
    },
  },
  { icon }
);

export const provider = registerPluginBehavior(plugin, {
  acp: createNativeAcpBehavior(() => ({
    args: ['--acp'],
  })),
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        autoApproveFlag: '--dangerously-skip-permissions',
        initialPromptFlag: '',
        modelFlag: '--model',
        resumeFlag: '--resume',
        sessionIdFlag: '--session-id',
      }),
  },
  mcp: createMcpAdapter({
    configPath: '.codebuddy/.mcp.json',
    format: 'json',
    serversKey: 'mcpServers',
    toNative(server) {
      const { name: _name, transport, ...entry } = server;
      if (!entry.type && transport) entry.type = transport;
      return entry;
    },
    fromNative(name, raw) {
      return { name, ...raw };
    },
  }),
});
