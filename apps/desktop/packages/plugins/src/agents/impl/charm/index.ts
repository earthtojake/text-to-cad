import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import type { CommandContext } from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  crushMcpAdapter,
  npmDependency,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { icon } from './icon';

function buildCharmCommand(ctx: CommandContext) {
  return buildStandardCommand(ctx, {
    defaultArgs: ctx.initialPrompt && !ctx.isResuming ? ['run'] : undefined,
    initialPromptFlag: '',
  });
}

export const plugin = definePlugin(
  {
    id: 'charm',
    name: 'Charm',
    description: 'Charm Crush agent CLI providing terminal-first AI assistance for coding tasks.',
    websiteUrl: 'https://github.com/charmbracelet/crush',
  },
  {
    autoApprove: {
      kind: 'none',
    },
    hostDependency: npmDependency({
      id: 'charm',
      package: '@charmland/crush',
      binaryNames: ['crush'],
    }),
    mcp: {
      kind: 'supported',
      scope: 'global',
      supportedTransports: ['stdio', 'http'],
    },
    models: {
      kind: 'none',
    },
    plugins: {
      kind: 'none',
    },
    prompt: {
      kind: 'argv',
      flag: '',
    },
    sessions: {
      kind: 'stateless',
    },
  },
  { icon }
);

export const provider = registerPluginBehavior(plugin, {
  prompt: {
    buildCommand: buildCharmCommand,
  },
  mcp: crushMcpAdapter(),
});
