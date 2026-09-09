import type { CanonicalHookEvent } from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildNestedJsonHookConfig,
  configRoots,
  defaultHookEventParser,
  homeConfigRoot,
  makeStdinHookCommand,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';

export const QODER_SETTINGS_PATH = 'settings.json';

function parseQoderHookEvent(eventType: string, body: Record<string, unknown>): CanonicalHookEvent {
  if (eventType === 'notification' && body.hook_event_name === 'PermissionRequest') {
    return {
      kind: 'status',
      type: 'notification',
      notificationType: 'permission_prompt',
      title: 'Permission Required',
      message:
        typeof body.message === 'string'
          ? body.message
          : typeof body.tool_name === 'string'
            ? `Qoder CLI is requesting permission to use ${body.tool_name}.`
            : undefined,
    };
  }

  return defaultHookEventParser(eventType, body);
}

export function buildQoderHookConfig() {
  return {
    ...buildNestedJsonHookConfig(QODER_SETTINGS_PATH, [
      { hookKey: 'SessionStart', command: makeStdinHookCommand('session') },
      { hookKey: 'UserPromptSubmit', command: makeStdinHookCommand('start') },
      { hookKey: 'PreToolUse', command: makeStdinHookCommand('start') },
      { hookKey: 'PostToolUse', command: makeStdinHookCommand('tool-use') },
      { hookKey: 'PostToolUseFailure', command: makeStdinHookCommand('error') },
      { hookKey: 'PermissionRequest', command: makeStdinHookCommand('notification') },
      { hookKey: 'Notification', command: makeStdinHookCommand('notification') },
      { hookKey: 'Stop', command: makeStdinHookCommand('stop') },
      { hookKey: 'SessionEnd', command: makeStdinHookCommand('stop') },
      { hookKey: 'StopFailure', command: makeStdinHookCommand('error') },
    ]),
    resolveConfigRoots: configRoots(homeConfigRoot('.qoder')),
    parseHookEvent: parseQoderHookEvent,
  };
}
