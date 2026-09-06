import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  createFileDropPlugin,
  envConfigRoot,
  npmDependency,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { PI_EXTENSION_CONTENT } from './plugin-file';

const PI_EXTENSION_PATH = 'extensions/emdash-hook.ts';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'pi',
    name: 'Pi',
    description:
      'Minimal terminal coding agent with multi-provider model support and extensible custom tools.',
    websiteUrl: 'https://github.com/earendil-works/pi/tree/main/packages/coding-agent',
  },
  {
    hooks: {
      kind: 'plugin',
      scope: 'global',
      supportedEvents: ['session', 'stop'],
    },
    hostDependency: npmDependency({
      id: 'pi',
      package: '@earendil-works/pi-coding-agent',
      installFlags: '--ignore-scripts',
    }),
    plugins: {
      kind: 'file-drop',
      scope: 'global',
    },
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
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        initialPromptFlag: '',
        resumeFlag: '--session',
        sessionIdFlag: '--session',
        sessionIdOnResumeOnly: true,
      }),
  },
  plugins: createFileDropPlugin({
    resolveConfigRoot: envConfigRoot('PI_CODING_AGENT_DIR', '.pi/agent'),
    relativePath: PI_EXTENSION_PATH,
    content: PI_EXTENSION_CONTENT,
  }),
});
