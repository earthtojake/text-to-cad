import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import { buildStandardCommand } from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'continue',
    name: 'Continue',
    description:
      'Continue CLI is a modular coding agent with configurable models, rules, and MCP tool support.',
    websiteUrl: 'https://docs.continue.dev/guides/cli',
  },
  {
    autoApprove: {
      kind: 'supported',
    },
    hostDependency: {
      id: 'continue',
      binaryNames: ['cn'],
      installCommands: {
        macos: [
          {
            method: 'npm',
            command: 'npm i -g @continuedev/cli',
            elevation: 'on-failure',
          },
        ],
        linux: [
          {
            method: 'npm',
            command: 'npm i -g @continuedev/cli',
            elevation: 'on-failure',
          },
        ],
        windows: [
          {
            method: 'npm',
            command: 'npm i -g @continuedev/cli',
            elevation: 'on-failure',
          },
        ],
      },
      updates: {
        kind: 'supported',
        releaseSource: {
          kind: 'npm',
          package: '@continuedev/cli',
        },
        update: {
          kind: 'package-manager',
        },
      },
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
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        autoApproveFlag: '--auto',
        initialPromptFlag: '',
        resumeFlag: '--resume',
      }),
  },
});
