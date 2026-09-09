import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  homebrewOption,
  passthroughMcpAdapter,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { connectStdioAcp } from '../../helpers/acp-stdio';
import { resolveAdapterAsset } from '../../helpers/adapter-assets';
import { enrichClaudeUpdate } from './acp-transform';
import { claudeAdapter } from './adapter';
import { claudeAuthStatus } from './auth';
import { buildClaudeHookConfig } from './hooks';
import { icon } from './icon';
import { buildClaudeTrustBehavior } from './trust';

export const plugin = definePlugin(
  {
    id: 'claude',
    name: 'Claude Code',
    description:
      'CLI that uses Anthropic Claude for code edits, explanations, and structured refactors in the terminal.',
    websiteUrl: 'https://code.claude.com/docs/en/quickstart',
  },
  {
    acp: {
      kind: 'supported',
    },
    autoApprove: {
      kind: 'supported',
    },
    auth: {
      kind: 'supported',
      methods: [
        {
          kind: 'cli-login',
          id: 'claude-login',
          name: 'Sign in with Claude Code',
          args: ['auth', 'login'],
          description: 'Open the Claude Code CLI sign-in flow in a terminal.',
        },
        {
          kind: 'api-key',
          id: 'anthropic-api-key',
          name: 'Use an Anthropic API key',
          envVars: [{ name: 'ANTHROPIC_API_KEY', label: 'Anthropic API key' }],
          helpUrl: 'https://docs.anthropic.com/en/api/admin-api/apikeys/get-api-key',
        },
      ],
    },
    models: {
      kind: 'selectable',
      modelOptions: {},
    },
    hooks: {
      kind: 'config',
      scope: 'global',
      supportedEvents: ['start', 'notification', 'stop'],
    },
    hostDependency: {
      id: 'claude',
      binaryNames: ['claude'],
      installCommands: {
        macos: [
          {
            method: 'curl',
            command: 'curl -fsSL https://claude.ai/install.sh | bash',
            uninstallCommand: 'claude uninstall',
            recommended: true,
          },
          homebrewOption({ formula: 'claude-code', cask: true }),
        ],
        linux: [
          {
            method: 'curl',
            command: 'curl -fsSL https://claude.ai/install.sh | bash',
            uninstallCommand: 'claude uninstall',
          },
        ],
        windows: [
          {
            method: 'curl',
            command:
              'curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd && del install.cmd',
            uninstallCommand: 'claude uninstall',
          },
        ],
      },
      updateCommand: {
        kind: 'self',
        args: ['install', 'latest'],
      },
    },
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
    trust: {
      kind: 'supported',
    },
  },
  { icon }
);

export const provider = registerPluginBehavior(plugin, {
  acp: {
    buildSpawn: (ctx) => ({
      // Run the adapter as plain Node inside the Electron binary.
      command: process.execPath,
      args: [resolveAdapterAsset(claudeAdapter)],
      env: {
        ELECTRON_RUN_AS_NODE: '1',
        // Point the adapter's Claude Agent SDK at the host-installed claude
        // binary instead of the SDK's auto-downloaded native binary.
        CLAUDE_CODE_EXECUTABLE: ctx.cli,
      },
    }),
    connect: (io, toClient) => {
      return connectStdioAcp(io, toClient);
    },
    enrich: enrichClaudeUpdate,
  },
  auth: {
    checkStatus: claudeAuthStatus,
  },
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        autoApproveFlag: '--dangerously-skip-permissions',
        initialPromptFlag: '',
        resumeFlag: '--resume',
        sessionIdFlag: '--session-id',
        modelFlag: '--model',
      }),
  },
  hooks: buildClaudeHookConfig(),
  mcp: passthroughMcpAdapter('.claude.json'),
  trust: buildClaudeTrustBehavior(),
});
