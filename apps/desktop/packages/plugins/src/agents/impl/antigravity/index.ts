import {
  definePlugin,
  registerPluginBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';
import { buildStandardCommand } from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { icon } from './icon';

export const plugin = definePlugin(
  {
    id: 'antigravity',
    name: 'Antigravity',
    description:
      'Google Antigravity CLI for terminal-first agent sessions with shared Antigravity settings and conversation history.',
    websiteUrl: 'https://antigravity.google/docs/cli-overview',
  },
  {
    autoApprove: {
      kind: 'supported',
    },
    models: {
      kind: 'selectable',
      modelOptions: {
        'Gemini 3.5 Flash (Medium)': {
          name: 'Gemini 3.5 Flash (Medium)',
          modelFeatures: { intelligence: 3, speed: 4 },
        },
        'Gemini 3.5 Flash (High)': {
          name: 'Gemini 3.5 Flash (High)',
          modelFeatures: { intelligence: 4, speed: 3 },
        },
        'Gemini 3.5 Flash (Low)': {
          name: 'Gemini 3.5 Flash (Low)',
          modelFeatures: { intelligence: 2, speed: 5 },
        },
        'Gemini 3.1 Pro (Low)': {
          name: 'Gemini 3.1 Pro (Low)',
          modelFeatures: { intelligence: 4, speed: 3 },
        },
        'Gemini 3.1 Pro (High)': {
          name: 'Gemini 3.1 Pro (High)',
          modelFeatures: { intelligence: 5, speed: 2 },
        },
        'Claude Sonnet 4.6 (Thinking)': {
          name: 'Claude Sonnet 4.6 (Thinking)',
          modelFeatures: { intelligence: 4, speed: 3 },
        },
        'Claude Opus 4.6 (Thinking)': {
          name: 'Claude Opus 4.6 (Thinking)',
          modelFeatures: { intelligence: 5, speed: 2 },
        },
        'GPT-OSS 120B (Medium)': {
          name: 'GPT-OSS 120B (Medium)',
          modelFeatures: { intelligence: 3, speed: 3 },
        },
      },
    },
    hostDependency: {
      id: 'antigravity',
      binaryNames: ['agy', 'antigravity'],
      installCommands: {
        macos: [
          {
            method: 'curl',
            command: 'curl -fsSL https://antigravity.google/cli/install.sh | bash',
          },
        ],
        linux: [
          {
            method: 'curl',
            command: 'curl -fsSL https://antigravity.google/cli/install.sh | bash',
          },
        ],
      },
      updates: {
        kind: 'supported',
        releaseSource: {
          kind: 'none',
        },
        update: {
          kind: 'package-manager',
        },
      },
    },
    prompt: {
      kind: 'argv',
      flag: '-i',
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
        autoApproveFlag: '--dangerously-skip-permissions',
        initialPromptFlag: '-i',
        sessionIdFlag: '--conversation=',
        sessionIdAlways: true,
        modelFlag: '--model',
      }),
  },
});
