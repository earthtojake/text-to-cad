import type { CanonicalHookEvent } from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildNestedJsonHookConfig,
  configRoots,
  defaultHookEventParser,
  envConfigRoot,
  makeStdinHookCommand,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';

export const QWEN_HOOKS_PATH = 'settings.json';

/**
 * Qwen's permission-request hook fires as a notification with
 * `hook_event_name === 'PermissionRequest'` rather than the standard
 * `notification_type` field.
 */
function parseQwenHookEvent(eventType: string, body: Record<string, unknown>): CanonicalHookEvent {
  if (eventType === 'notification' && body.hook_event_name === 'PermissionRequest') {
    return {
      kind: 'status',
      type: 'notification',
      notificationType: 'permission_prompt',
      message: typeof body.message === 'string' ? body.message : undefined,
    };
  }
  return defaultHookEventParser(eventType, body);
}

export function buildQwenHookConfig() {
  return {
    ...buildNestedJsonHookConfig(QWEN_HOOKS_PATH, [
      { hookKey: 'SessionStart', command: makeStdinHookCommand('session') },
      { hookKey: 'PermissionRequest', command: makeStdinHookCommand('notification') },
      { hookKey: 'Stop', command: makeStdinHookCommand('stop') },
      { hookKey: 'SessionEnd', command: makeStdinHookCommand('stop') },
    ]),
    resolveConfigRoots: configRoots(envConfigRoot('QWEN_HOME', '.qwen')),
    parseHookEvent: parseQwenHookEvent,
  };
}
