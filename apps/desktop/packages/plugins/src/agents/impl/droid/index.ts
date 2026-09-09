import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  droidMcpAdapter,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { createNativeAcpBehavior } from '../../helpers/acp-stdio';
import { buildDroidHookConfig } from './hooks';
import { icon } from './icon';

// Droid reports its own UUID-based session ids; only accept well-formed UUIDs for resume.
const DROID_SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const validateSessionId = (id: string) => DROID_SESSION_ID_PATTERN.test(id);

export const plugin = definePlugin(
  {
    id: 'droid',
    name: 'Droid',
    description: "Factory AI's agent CLI for running multi-step coding tasks from the terminal.",
    websiteUrl: 'https://docs.factory.ai/cli/getting-started/quickstart',
  },
  {
    acp: {
      kind: 'supported',
    },
    autoApprove: {
      kind: 'supported',
    },
    hooks: {
      kind: 'config',
      scope: 'global',
      supportedEvents: ['notification', 'stop', 'session', 'start'],
    },
    hostDependency: {
      id: 'droid',
      binaryNames: ['droid'],
      installCommands: {
        macos: [
          {
            method: 'curl',
            command: 'curl -fsSL https://app.factory.ai/cli | sh',
          },
        ],
        linux: [
          {
            method: 'curl',
            command: 'curl -fsSL https://app.factory.ai/cli | sh',
          },
        ],
      },
      updates: {
        kind: 'supported',
        releaseSource: {
          kind: 'none',
        },
        update: {
          kind: 'package-manager',
        },
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
  },
  { icon }
);

export const provider = registerPluginBehavior(plugin, {
  acp: createNativeAcpBehavior(() => ({
    args: ['exec', '--output-format', 'acp-daemon'],
    env: {
      DROID_DISABLE_AUTO_UPDATE: 'true',
      FACTORY_DROID_AUTO_UPDATE_ENABLED: 'false',
    },
  })),
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        // Interactive `droid` only exposes `--auto <level>`; `--skip-permissions-unsafe`
        // is exclusive to `droid exec`. `high` grants the broadest autonomy the
        // interactive TUI supports (edits, installs, git push, deploys).
        autoApproveFlag: '--auto high',
        initialPromptFlag: '',
        resumeFlag: '--resume',
        sessionIdFlag: '--resume',
        sessionIdOnResumeOnly: true,
      }),
  },
  hooks: buildDroidHookConfig(),
  mcp: droidMcpAdapter(),
  sessions: { validateSessionId },
});
