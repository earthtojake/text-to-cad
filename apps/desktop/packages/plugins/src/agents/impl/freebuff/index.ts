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
    id: 'freebuff',
    name: 'Freebuff',
    description:
      'Freebuff is a standalone Codebuff package for project-directory assistance and day-to-day development tasks.',
    websiteUrl: 'https://freebuff.com',
  },
  {
    hostDependency: npmDependency({ id: 'freebuff', package: 'freebuff' }),
    prompt: {
      // The freebuff CLI takes no prompt positional/flag (its only positional is
      // the `login` command); prompts are entered manually in the interactive TUI.
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
    buildCommand: (ctx) => buildStandardCommand(ctx, {}),
  },
});
