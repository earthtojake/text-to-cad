import { dirname, extname, join } from 'node:path';
import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import { buildStandardCommand } from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { createNativeAcpBehavior } from '../../helpers/acp-stdio';
import { buildMistralHookConfig } from './hooks';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'mistral',
    name: 'Mistral Vibe',
    description:
      'Mistral AI terminal coding assistant with conversational codebase help, execution tools, and file operations.',
    websiteUrl: 'https://github.com/mistralai/mistral-vibe',
  },
  {
    acp: {
      kind: 'supported',
    },
    autoApprove: {
      kind: 'supported',
    },
    hooks: {
      kind: 'config',
      scope: 'global',
      supportedEvents: ['notification', 'stop'],
    },
    models: {
      kind: 'selectable',
      modelOptions: {
        'mistral-medium-3.5': {
          name: 'Mistral Medium 3.5',
          description: 'Default hosted Mistral Vibe model with high thinking and image support.',
          modelFeatures: { intelligence: 5, speed: 4 },
        },
        'devstral-small': {
          name: 'Devstral Small',
          description: 'Lower-cost hosted Devstral model for faster coding tasks.',
          modelFeatures: { intelligence: 3, speed: 5 },
        },
        local: {
          name: 'Local Devstral',
          description: 'Local llama.cpp Devstral model configured by Mistral Vibe.',
          modelFeatures: { intelligence: 3, speed: 3 },
        },
      },
    },
    hostDependency: {
      id: 'mistral',
      binaryNames: ['vibe'],
      installCommands: {
        macos: [
          {
            method: 'curl',
            command: 'curl -LsSf https://mistral.ai/vibe/install.sh | bash',
          },
        ],
        linux: [
          {
            method: 'curl',
            command: 'curl -LsSf https://mistral.ai/vibe/install.sh | bash',
          },
        ],
      },
      updates: {
        kind: 'supported',
        releaseSource: {
          kind: 'github',
          repo: 'mistralai/mistral-vibe',
        },
        update: {
          kind: 'package-manager',
        },
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
  acp: createNativeAcpBehavior((ctx) => {
    const ext = extname(ctx.cli);
    const acpExt = ['.exe', '.cmd', '.bat', '.ps1'].includes(ext.toLowerCase()) ? ext : '';
    return {
      command: join(dirname(ctx.cli), `vibe-acp${acpExt}`),
      args: [],
    };
  }),
  hooks: buildMistralHookConfig(),
  prompt: {
    buildCommand: (ctx) =>
      buildStandardCommand(ctx, {
        autoApproveFlag: '--agent auto-approve',
        initialPromptFlag: '',
        extraEnv: ctx.model ? { VIBE_ACTIVE_MODEL: ctx.model } : undefined,
      }),
  },
});
