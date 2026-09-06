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
    id: 'zero',
    name: 'Zero',
    description:
      'Terminal coding agent with multi-provider model support, local-first configuration, and terminal-first coding workflows.',
    websiteUrl: 'https://zero.gitlawb.com/',
  },
  {
    autoApprove: {
      kind: 'supported',
    },
    hostDependency: npmDependency({ id: 'zero', package: '@gitlawb/zero' }),
    prompt: {
      kind: 'pty-only',
    },
    sessions: {
      kind: 'stateless',
    },
  },
  { icon }
);

export const provider = registerPluginBehavior(plugin, {
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        autoApproveFlag: '--skip-permissions-unsafe',
      }),
  },
});
