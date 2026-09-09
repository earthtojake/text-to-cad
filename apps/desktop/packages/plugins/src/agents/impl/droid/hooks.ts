import {
  buildNestedJsonHookConfig,
  configRoots,
  homeConfigRoot,
  makeStdinHookCommand,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';

export const DROID_HOOKS_PATH = 'settings.json';

export function buildDroidHookConfig() {
  return {
    ...buildNestedJsonHookConfig(DROID_HOOKS_PATH, [
      { hookKey: 'UserPromptSubmit', command: makeStdinHookCommand('start') },
      { hookKey: 'Notification', command: makeStdinHookCommand('notification') },
      { hookKey: 'Stop', command: makeStdinHookCommand('stop') },
      { hookKey: 'SessionStart', command: makeStdinHookCommand('session') },
    ]),
    resolveConfigRoots: configRoots(homeConfigRoot('.factory')),
  };
}
