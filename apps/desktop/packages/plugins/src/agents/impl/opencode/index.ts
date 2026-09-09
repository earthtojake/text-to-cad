import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  createFileDropPlugin,
  npmDependency,
  opencodeMcpAdapter,
  xdgConfigRoot,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { connectStdioAcp } from '../../helpers/acp-stdio';
import { opencodeAuthStatus } from './auth';
import { OPENCODE_PLUGIN_CONTENT } from './plugin-file';

const OPENCODE_PLUGIN_PATH = 'plugins/emdash-notifications.js';
const validateSessionId = (id: string) => id.startsWith('ses');
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'opencode',
    name: 'OpenCode',
    description:
      'OpenCode CLI that interfaces with models for code generation and edits from the shell.',
    websiteUrl: 'https://opencode.ai/docs/cli/',
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
          id: 'opencode-login',
          name: 'Sign in with OpenCode',
          args: ['auth', 'login'],
          description: 'Open the OpenCode CLI sign-in flow in a terminal.',
        },
        {
          kind: 'api-key',
          id: 'provider-api-key',
          name: 'Use provider API keys',
          envVars: [
            { name: 'ANTHROPIC_API_KEY', label: 'Anthropic API key' },
            { name: 'OPENAI_API_KEY', label: 'OpenAI API key' },
            { name: 'GEMINI_API_KEY', label: 'Gemini API key' },
          ],
        },
      ],
    },
    hooks: {
      kind: 'plugin',
      scope: 'global',
      supportedEvents: ['notification', 'stop', 'session'],
    },
    hostDependency: npmDependency({ id: 'opencode', package: 'opencode-ai' }),
    mcp: {
      kind: 'supported',
      scope: 'global',
      supportedTransports: ['stdio', 'http'],
    },
    plugins: {
      kind: 'file-drop',
      scope: 'global',
    },
    prompt: {
      kind: 'argv',
      flag: '--prompt',
    },
    sessions: {
      kind: 'resumable',
    },
  },
  { icon }
);

export const provider = registerPluginBehavior(plugin, {
  auth: {
    checkStatus: opencodeAuthStatus,
  },
  acp: {
    buildSpawn: (ctx) => ({
      command: ctx.cli,
      args: ['acp'],
    }),
    connect: (io, toClient) => {
      return connectStdioAcp(io, toClient);
    },
  },
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        extraEnv: ctx.autoApprove ? { OPENCODE_PERMISSION: '{"*":"allow"}' } : {},
        initialPromptFlag: '--prompt',
        modelFlag: '--model',
        resumeFlag: '--session',
        sessionIdFlag: '--session',
        sessionIdOnResumeOnly: true,
        resumeWithoutSessionFlag: '--continue',
        validateSessionId,
      }),
  },
  sessions: { validateSessionId },
  mcp: opencodeMcpAdapter(),
  plugins: createFileDropPlugin({
    resolveConfigRoot: xdgConfigRoot('opencode', { overrideEnvVar: 'OPENCODE_CONFIG_DIR' }),
    relativePath: OPENCODE_PLUGIN_PATH,
    content: OPENCODE_PLUGIN_CONTENT,
  }),
});
