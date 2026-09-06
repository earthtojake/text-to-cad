import type { CanonicalHookEvent } from '@emdash/core/services/agent-plugins/api/plugins';
import {
  buildNestedJsonHookConfig,
  configRoots,
  defaultHookEventParser,
  envConfigRoot,
  makeStdinHookCommand,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';

export const CLAUDE_SETTINGS_PATH = 'settings.json';

/**
 * Claude's Notification events carry no `notification_type` field.
 * Classify by examining the message text:
 *   /permission|approval/i → permission_prompt
 *   everything else        → idle_prompt (agent waiting / done)
 */
function parseClaudeHookEvent(
  eventType: string,
  body: Record<string, unknown>
): CanonicalHookEvent {
  if (eventType === 'notification') {
    const message = typeof body.message === 'string' ? body.message : '';
    const notificationType = /permission|approval/i.test(message)
      ? ('permission_prompt' as const)
      : ('idle_prompt' as const);
    return {
      kind: 'status',
      type: 'notification',
      notificationType,
      message: message || undefined,
      title: typeof body.title === 'string' ? body.title : undefined,
    };
  }

  return defaultHookEventParser(eventType, body);
}

export function buildClaudeHookConfig() {
  return {
    ...buildNestedJsonHookConfig(CLAUDE_SETTINGS_PATH, [
      { hookKey: 'UserPromptSubmit', command: makeStdinHookCommand('start') },
      { hookKey: 'Notification', command: makeStdinHookCommand('notification') },
      { hookKey: 'Stop', command: makeStdinHookCommand('stop') },
    ]),
    resolveConfigRoots: configRoots(envConfigRoot('CLAUDE_CONFIG_DIR', '.claude')),
    parseHookEvent: parseClaudeHookEvent,
  };
}
