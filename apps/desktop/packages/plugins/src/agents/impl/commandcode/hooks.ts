import {
  buildNestedJsonHookConfig,
  configRoots,
  homeConfigRoot,
  makeStdinHookCommand,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';

export const COMMANDCODE_SETTINGS_PATH = 'settings.json';

export function buildCommandCodeHookConfig() {
  return {
    ...buildNestedJsonHookConfig(COMMANDCODE_SETTINGS_PATH, [
      { hookKey: 'Stop', command: makeStdinHookCommand('session') },
      { hookKey: 'Stop', command: makeStdinHookCommand('stop') },
    ]),
    resolveConfigRoots: configRoots(homeConfigRoot('.commandcode')),
  };
}
