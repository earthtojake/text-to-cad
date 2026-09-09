import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  npmDependency,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'letta',
    name: 'Letta',
    description:
      'Memory-first coding agent CLI with persistent agents that learn across sessions and portable memory across models.',
    websiteUrl: 'https://docs.letta.com/letta-code/cli',
  },
  {
    autoApprove: {
      kind: 'supported',
    },
    hostDependency: npmDependency({
      id: 'letta',
      package: '@letta-ai/letta-code',
      skipVersionProbe: true,
    }),
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
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        autoApproveFlag: '--yolo',
        newConversationFlag: '--new',
      }),
  },
});
