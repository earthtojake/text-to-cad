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
    id: 'autohand',
    name: 'Autohand Code',
    description:
      'Terminal coding agent with auto-commit, dry-run previews, community skills, and headless automation modes.',
    websiteUrl: 'https://autohand.ai/code/',
  },
  {
    autoApprove: {
      kind: 'supported',
    },
    hostDependency: npmDependency({ id: 'autohand', package: 'autohand-cli' }),
    prompt: {
      kind: 'argv',
      flag: '-p',
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
        autoApproveFlag: '--unrestricted',
        initialPromptFlag: '-p',
      }),
  },
});
