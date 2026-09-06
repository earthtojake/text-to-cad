import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import { createNativeAcpBehavior } from '../../helpers/acp-stdio';
import { buildGooseHookConfig } from './hooks';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'goose',
    name: 'Goose',
    description: 'Goose CLI that routes tasks to tools and models for coding workflows.',
    websiteUrl: 'https://goose-docs.ai/docs/quickstart/',
  },
  {
    acp: {
      kind: 'supported',
    },
    autoApprove: {
      kind: 'none',
    },
    effort: {
      kind: 'none',
    },
    hooks: {
      kind: 'config',
      scope: 'global',
      supportedEvents: ['session', 'start', 'stop', 'tool-use', 'tool-use-failure'],
    },
    hostDependency: {
      id: 'goose',
      binaryNames: ['goose'],
      installCommands: {
        macos: [
          {
            method: 'curl',
            command:
              'curl -fsSL https://github.com/aaif-goose/goose/releases/download/stable/download_cli.sh | bash',
          },
        ],
        linux: [
          {
            method: 'curl',
            command:
              'curl -fsSL https://github.com/aaif-goose/goose/releases/download/stable/download_cli.sh | bash',
          },
        ],
      },
      updates: {
        kind: 'supported',
        releaseSource: {
          kind: 'github',
          repo: 'aaif-goose/goose',
        },
        update: {
          kind: 'package-manager',
        },
      },
    },
    mcp: {
      kind: 'none',
    },
    models: {
      kind: 'none',
    },
    plugins: {
      kind: 'none',
    },
    prompt: {
      kind: 'argv',
      flag: '-t',
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
    buildCommand: (ctx) => {
      if (ctx.isResuming) {
        const resumeSessionId = ctx.providerSessionId?.trim();
        if (!resumeSessionId) {
          const args = ['session'];

          if (ctx.sessionId) {
            args.push('-n', ctx.sessionId);
          }

          if (ctx.extraArgs?.length) {
            args.push(...ctx.extraArgs);
          }

          return { command: ctx.cli, args, env: {} };
        }

        const args = ['session', '--resume', '--session-id', resumeSessionId];

        if (ctx.extraArgs?.length) {
          args.push(...ctx.extraArgs);
        }

        return { command: ctx.cli, args, env: {} };
      }

      if (!ctx.initialPrompt?.trim()) {
        const args = ['session'];

        if (ctx.sessionId) {
          args.push('-n', ctx.sessionId);
        }

        if (ctx.extraArgs?.length) {
          args.push(...ctx.extraArgs);
        }

        return { command: ctx.cli, args, env: {} };
      }

      const args = ['run', '-s'];

      if (ctx.sessionId) {
        args.push('-n', ctx.sessionId);
      }

      args.push('-t', ctx.initialPrompt);

      if (ctx.extraArgs?.length) {
        args.push(...ctx.extraArgs);
      }

      return { command: ctx.cli, args, env: {} };
    },
  },
  hooks: buildGooseHookConfig(),
});
