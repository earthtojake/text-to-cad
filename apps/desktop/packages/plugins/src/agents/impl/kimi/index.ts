import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import type { AgentCommand, CommandContext } from '@emdash/core/services/agent-plugins/api/plugins';
import { buildStandardCommand } from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { createNativeAcpBehavior } from '../../helpers/acp-stdio';
import { addKimiHooksToConfigText, buildKimiHookConfig } from './hooks';

function injectKimiHooksIntoInlineConfig(args: string[]): string[] {
  return args.map((arg, index) => {
    if (arg === '--config' && args[index + 1] !== undefined) return arg;
    if (index > 0 && args[index - 1] === '--config') return addKimiHooksToConfigText(arg);
    if (arg.startsWith('--config='))
      return `--config=${addKimiHooksToConfigText(arg.slice('--config='.length))}`;
    return arg;
  });
}

function buildKimiCommand(ctx: CommandContext): AgentCommand {
  const cmd = buildStandardCommand(ctx, {
    autoApproveFlag: '--yolo',
    resumeFlag: '-S',
    sessionIdFlag: '-S',
    sessionIdOnResumeOnly: true,
    resumeWithoutSessionFlag: '-C',
    omitAutoApproveOnResume: true,
  });
  return { ...cmd, args: injectKimiHooksIntoInlineConfig(cmd.args) };
}
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'kimi',
    name: 'Kimi',
    description:
      'Kimi CLI by Moonshot AI, with shell execution, Zsh integration, ACP, and MCP support.',
    websiteUrl: 'https://moonshotai.github.io/kimi-cli/en/guides/getting-started.html',
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
      id: 'kimi',
      binaryNames: ['kimi'],
      installCommands: {
        macos: [
          {
            method: 'curl',
            command: 'curl -LsSf https://code.kimi.com/install.sh | bash',
          },
        ],
        linux: [
          {
            method: 'curl',
            command: 'curl -LsSf https://code.kimi.com/install.sh | bash',
          },
        ],
      },
      updates: {
        kind: 'supported',
        releaseSource: {
          kind: 'github',
          repo: 'moonshotai/kimi-cli',
        },
        update: {
          kind: 'package-manager',
        },
      },
    },
    prompt: {
      kind: 'pty-only',
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
    buildCommand: buildKimiCommand,
  },
  hooks: buildKimiHookConfig(),
  sessions: {
    validateSessionId: undefined,
  },
});
