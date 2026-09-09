import {
  buildFlatTomlHookConfig,
  configRoots,
  envConfigRoot,
  makeNotificationHookCommand,
  makeStdinHookCommand,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';

export const MISTRAL_HOOKS_PATH = 'hooks.toml';

const MISTRAL_HOOK_ENTRIES = [
  {
    name: 'emdash-post-agent-turn',
    type: 'post_agent_turn',
    command: makeStdinHookCommand('stop'),
    timeout: 10,
    strict: false,
    description: 'Notify Hardcore when Mistral Vibe finishes an agent turn.',
  },
  {
    name: 'emdash-ask-user-question',
    type: 'before_tool',
    match: 'ask_user_question',
    command: makeNotificationHookCommand('permission_prompt'),
    timeout: 10,
    strict: false,
    description: 'Notify Hardcore when Mistral Vibe asks for user input.',
  },
];

export function buildMistralHookConfig() {
  return {
    ...buildFlatTomlHookConfig(MISTRAL_HOOKS_PATH, MISTRAL_HOOK_ENTRIES),
    resolveConfigRoots: configRoots(envConfigRoot('VIBE_HOME', '.vibe')),
  };
}
