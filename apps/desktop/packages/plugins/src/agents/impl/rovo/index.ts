import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import { buildStandardCommand } from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'rovo',
    name: 'Rovo Dev',
    description:
      'Atlassian Rovo Dev CLI integrates terminal assistance with Jira, Confluence, and Bitbucket workflows.',
    websiteUrl:
      'https://support.atlassian.com/rovo/docs/install-and-run-rovo-dev-cli-on-your-device/',
  },
  {
    autoApprove: {
      kind: 'supported',
    },
    hostDependency: {
      id: 'rovo',
      binaryNames: ['rovodev', 'acli'],
      installCommands: {
        macos: [
          {
            method: 'other',
            command: 'acli rovodev auth login',
          },
        ],
        linux: [
          {
            method: 'other',
            command: 'acli rovodev auth login',
          },
        ],
      },
      updates: {
        kind: 'none',
      },
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
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        autoApproveFlag: '--yolo',
      }),
  },
});
