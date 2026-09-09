import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import { buildStandardCommand } from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { createNativeAcpBehavior } from '../../helpers/acp-stdio';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'junie',
    name: 'Junie',
    description:
      'JetBrains agentic coding CLI for interactive terminal and headless project workflows.',
    websiteUrl: 'https://junie.jetbrains.com/docs/junie-cli.html',
  },
  {
    acp: {
      kind: 'supported',
    },
    hostDependency: {
      id: 'junie',
      binaryNames: ['junie'],
      installCommands: {
        macos: [
          {
            method: 'curl',
            command: 'curl -fsSL https://junie.jetbrains.com/install.sh | bash',
          },
        ],
        linux: [
          {
            method: 'curl',
            command: 'curl -fsSL https://junie.jetbrains.com/install.sh | bash',
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
    prompt: {
      kind: 'argv',
      flag: '--task',
    },
    sessions: {
      kind: 'resumable',
    },
  },
  { icon }
);

export const provider = registerPluginBehavior(plugin, {
  acp: createNativeAcpBehavior(() => ({
    args: ['--acp=true'],
  })),
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        initialPromptFlag: '--task',
        sessionIdFlag: '--session-id',
      }),
  },
});
