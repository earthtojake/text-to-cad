import {
  buildNestedJsonHookConfig,
  configRoots,
  makeNotificationHookCommand,
  makeStdinHookCommand,
  xdgConfigRoot,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';

export const DEVIN_HOOKS_PATH = 'config.json';

export function buildDevinHookConfig() {
  return {
    ...buildNestedJsonHookConfig(DEVIN_HOOKS_PATH, [
      { hookKey: 'Stop', command: makeStdinHookCommand('stop') },
      { hookKey: 'SessionEnd', command: makeStdinHookCommand('stop') },
      { hookKey: 'PermissionRequest', command: makeNotificationHookCommand('permission_prompt') },
    ]),
    resolveConfigRoots: configRoots(xdgConfigRoot('devin')),
  };
}
