import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  createFileDropPlugin,
  mimocodeMcpAdapter,
  npmDependency,
  xdgConfigRoot,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { createNativeAcpBehavior } from '../../helpers/acp-stdio';
import { icon } from './icon';
import { MIMOCODE_PLUGIN_CONTENT } from './plugin-file';

const MIMOCODE_PLUGIN_PATH = 'plugins/emdash-notifications.js';

// MiMoCode session ids match `^ses.*` (inherited from its OpenCode base). The
// guard prevents resuming with the emdash conversation UUID that
// `conversation.sessionId` is seeded with before the first native id is captured.
const validateSessionId = (id: string) => id.startsWith('ses');

export const plugin = definePlugin(
  {
    id: 'mimocode',
    name: 'MiMo Code',
    description:
      "Xiaomi's terminal-native coding agent with persistent cross-session memory and OpenAI-compatible provider support.",
    websiteUrl: 'https://github.com/XiaomiMiMo/MiMo-Code',
  },
  {
    acp: {
      kind: 'supported',
    },
    autoApprove: {
      kind: 'supported',
    },
    hooks: {
      kind: 'plugin',
      scope: 'global',
      supportedEvents: ['notification', 'stop', 'session'],
    },
    hostDependency: npmDependency({
      id: 'mimo',
      package: '@mimo-ai/cli',
      recommended: false,
      installDocs: 'https://github.com/XiaomiMiMo/MiMo-Code#quick-start',
      extraOptions: {
        macos: [
          {
            method: 'curl',
            command: 'curl -fsSL https://mimo.xiaomi.com/install | bash',
            uninstallCommand: 'mimo uninstall --keep-config --keep-data --force',
            recommended: true,
          },
        ],
        linux: [
          {
            method: 'curl',
            command: 'curl -fsSL https://mimo.xiaomi.com/install | bash',
            uninstallCommand: 'mimo uninstall --keep-config --keep-data --force',
            recommended: true,
          },
        ],
        windows: [
          {
            method: 'powershell',
            command: 'powershell -ep Bypass -c "irm https://mimo.xiaomi.com/install.ps1 | iex"',
            uninstallCommand: 'mimo uninstall --keep-config --keep-data --force',
            recommended: true,
          },
        ],
      },
    }),
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
  acp: createNativeAcpBehavior(() => ({
    args: ['acp'],
  })),
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        extraEnv: ctx.autoApprove ? { MIMOCODE_PERMISSION: '{"*":"allow"}' } : {},
        initialPromptFlag: '--prompt',
        resumeFlag: '--session',
        sessionIdFlag: '--session',
        sessionIdOnResumeOnly: true,
        resumeWithoutSessionFlag: '--continue',
        validateSessionId,
      }),
  },
  sessions: { validateSessionId },
  mcp: mimocodeMcpAdapter(),
  plugins: createFileDropPlugin({
    resolveConfigRoot: xdgConfigRoot('mimocode', { overrideEnvVar: 'MIMOCODE_HOME' }),
    relativePath: MIMOCODE_PLUGIN_PATH,
    content: MIMOCODE_PLUGIN_CONTENT,
  }),
});
