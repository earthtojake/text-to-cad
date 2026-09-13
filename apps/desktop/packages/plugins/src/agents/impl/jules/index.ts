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
    id: 'jules',
    name: 'Jules',
    description:
      "Google's Jules CLI for managing asynchronous remote coding sessions and a terminal dashboard.",
    websiteUrl: 'https://jules.google/docs/cli/reference/',
  },
  {
    hostDependency: npmDependency({
      id: 'jules',
      package: '@google/jules',
      versionArgs: ['version'],
    }),
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
    // Jules is PTY-only for prompts: `jules <text>` is parsed as an unknown subcommand,
    // so Emdash opens the TUI and lets the user type manually.
    buildCommand: (ctx) => buildStandardCommand(ctx, {}),
  },
});
