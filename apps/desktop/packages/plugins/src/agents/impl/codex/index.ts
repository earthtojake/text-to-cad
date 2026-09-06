import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  codexMcpAdapter,
  homebrewOption,
  npmDependency,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { connectStdioAcp } from '../../helpers/acp-stdio';
import { resolveAdapterAsset } from '../../helpers/adapter-assets';
import { authenticatedFromEnv, commandAuthStatus } from '../../helpers/auth';
import { enrichCodexUpdate } from './acp-transform';
import { codexAdapter } from './adapter';
import { buildCodexHookConfig } from './hooks';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'codex',
    name: 'Codex',
    description:
      'CLI that connects to OpenAI models for project-aware code assistance and terminal workflows.',
    websiteUrl: 'https://github.com/openai/codex',
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
          id: 'codex-login',
          name: 'Sign in with Codex',
          args: ['login', '--device-auth'],
          description: 'Open the Codex CLI sign-in flow in a terminal.',
        },
        {
          kind: 'api-key',
          id: 'openai-api-key',
          name: 'Use an OpenAI API key',
          envVars: [{ name: 'OPENAI_API_KEY', label: 'OpenAI API key' }],
          helpUrl: 'https://platform.openai.com/api-keys',
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
      supportedEvents: ['notification', 'stop', 'session'],
    },
    hostDependency: npmDependency({
      id: 'codex',
      package: '@openai/codex',
      extraOptions: {
        macos: [homebrewOption({ formula: 'codex', cask: true })],
        linux: [homebrewOption({ formula: 'codex', cask: true })],
        windows: [
          {
            method: 'powershell',
            command:
              'powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"',
            updateCommand:
              'powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"',
          },
        ],
      },
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
  acp: {
    buildSpawn: (ctx) => ({
      command: process.execPath,
      args: [resolveAdapterAsset(codexAdapter)],
      env: {
        ELECTRON_RUN_AS_NODE: '1',
        CODEX_PATH: ctx.cli,
      },
    }),
    connect: (io, toClient) => {
      return connectStdioAcp(io, toClient);
    },
    enrich: enrichCodexUpdate,
  },
  auth: {
    checkStatus: async (ctx) => {
      const envStatus = authenticatedFromEnv(ctx, ['OPENAI_API_KEY']);
      if (envStatus.kind === 'authenticated') return envStatus;
      return commandAuthStatus(ctx, ['login', 'status'], {
        authenticatedPattern: /authenticated|logged in|signed in/i,
        unauthenticatedPattern: /not authenticated|not logged in|not signed in|login required/i,
      });
    },
  },
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        autoApproveFlag:
          '-c approval_policy="never" -c sandbox_mode="danger-full-access" --dangerously-bypass-hook-trust',
        initialPromptFlag: '',
        resumeFlag: 'resume',
        sessionIdFlag: ' ',
        sessionIdOnResumeOnly: true,
        resumeWithoutSessionFlag: 'resume --last',
        deduplicateFlags: ['--dangerously-bypass-approvals-and-sandbox'],
        modelFlag: '-m',
      }),
  },
  hooks: buildCodexHookConfig(),
  mcp: codexMcpAdapter(),
});
