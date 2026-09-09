import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildStandardCommand,
  npmDependency,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { createNativeAcpBehavior } from '../../helpers/acp-stdio';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'cline',
    name: 'Cline',
    description:
      'Cline CLI runs coding agents directly in your terminal with multi-provider model support.',
    websiteUrl: 'https://docs.cline.bot/cline-cli/overview',
  },
  {
    acp: {
      kind: 'supported',
    },
    autoApprove: {
      kind: 'supported',
    },
    hostDependency: npmDependency({ id: 'cline', package: 'cline' }),
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
  acp: createNativeAcpBehavior(() => ({
    args: ['--acp'],
  })),
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        autoApproveFlag: '--yolo',
        initialPromptFlag: '',
      }),
  },
});
