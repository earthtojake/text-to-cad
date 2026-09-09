import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  npmDependency,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { createNativeAcpBehavior } from '../../helpers/acp-stdio';
import { buildAuggieHookConfig } from './hooks';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'auggie',
    name: 'Auggie',
    description:
      'Augment Code CLI to run an agent against your repository for code changes and reviews.',
    websiteUrl: 'https://docs.augmentcode.com/cli/overview',
  },
  {
    acp: {
      kind: 'supported',
    },
    hooks: {
      kind: 'config',
      scope: 'global',
      supportedEvents: ['notification', 'stop', 'session', 'start'],
    },
    hostDependency: npmDependency({ id: 'auggie', package: '@augmentcode/auggie' }),
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
    env: {
      AUGMENT_DISABLE_AUTO_UPDATE: '1',
    },
  })),
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        defaultArgs: ['--allow-indexing'],
        initialPromptFlag: '',
        resumeFlag: '--resume',
        sessionIdFlag: '--resume',
        sessionIdOnResumeOnly: true,
        resumeWithoutSessionFlag: '--continue',
      }),
  },
  hooks: buildAuggieHookConfig(),
});
