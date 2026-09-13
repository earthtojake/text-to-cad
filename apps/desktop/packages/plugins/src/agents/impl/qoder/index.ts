import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  npmDependency,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { createNativeAcpBehavior } from '../../helpers/acp-stdio';
import { buildQoderHookConfig } from './hooks';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'qoder',
    name: 'Qoder CLI',
    description:
      'Qoder terminal agent for code review, implementation, debugging, and repository-aware automation.',
    websiteUrl: 'https://qoder.com/en/cli',
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
      supportedEvents: ['notification', 'stop', 'session', 'start', 'tool-use', 'tool-use-failure'],
    },
    hostDependency: npmDependency({
      id: 'qoder',
      package: '@qoder-ai/qodercli',
      binaryNames: ['qodercli'],
      installDocs: 'https://qoder.com/en/cli',
      extraOptions: {
        macos: [
          {
            method: 'curl',
            command: 'curl -fsSL https://qoder.com/install | bash',
          },
        ],
        linux: [
          {
            method: 'curl',
            command: 'curl -fsSL https://qoder.com/install | bash',
          },
        ],
        windows: [
          {
            method: 'powershell',
            command: 'irm https://qoder.com/install.ps1 | iex',
          },
        ],
      },
    }),
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
        autoApproveFlag: '--yolo',
        initialPromptFlag: '',
        resumeFlag: '-r',
        sessionIdFlag: '-r',
        sessionIdOnResumeOnly: true,
        resumeWithoutSessionFlag: '-c',
      }),
  },
  hooks: buildQoderHookConfig(),
});
