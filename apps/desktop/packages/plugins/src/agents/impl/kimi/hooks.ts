import {
  buildFlatTomlHookConfig,
  configRoots,
  envConfigRoot,
  filterUserHooks,
  homeConfigRoot,
  hookEntriesFromConfig,
  makeStdinHookCommand,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import { parse as parseTOML, stringify as stringifyTOML } from 'smol-toml';

export const KIMI_CONFIG_PATH = 'config.toml';

const KIMI_HOOK_SPECS = [
  { hookKey: 'SessionStart', command: makeStdinHookCommand('session') },
  { hookKey: 'UserPromptSubmit', command: makeStdinHookCommand('start') },
  { hookKey: 'PostToolUse', command: makeStdinHookCommand('start') },
  { hookKey: 'PostToolUseFailure', command: makeStdinHookCommand('start') },
  { hookKey: 'Notification', command: makeStdinHookCommand('notification') },
  { hookKey: 'Stop', command: makeStdinHookCommand('stop') },
  { hookKey: 'StopFailure', command: makeStdinHookCommand('stop') },
  { hookKey: 'SessionEnd', command: makeStdinHookCommand('stop') },
];

function buildKimiHookEntries(existing: unknown[]): unknown[] {
  const userEntries = filterUserHooks(existing as Record<string, unknown>[]);
  const emdashEntries = KIMI_HOOK_SPECS.map(({ hookKey, command }) => ({
    event: hookKey,
    command,
  }));
  return [...userEntries, ...emdashEntries];
}

/**
 * Inject kimi hooks into an inline --config JSON/TOML text string.
 * Used by the kimi buildCommand to patch the --config= flag value on the fly.
 */
export function addKimiHooksToConfigText(content: string): string {
  try {
    const config = JSON.parse(content) as Record<string, unknown>;
    const hooks = hookEntriesFromConfig(config, 'inline Kimi config');
    config.hooks = buildKimiHookEntries(hooks);
    return JSON.stringify(config);
  } catch {
    /* fall through to TOML */
  }
  try {
    const config = parseTOML(content) as Record<string, unknown>;
    const hooks = hookEntriesFromConfig(config, 'inline Kimi config');
    config.hooks = buildKimiHookEntries(hooks);
    return stringifyTOML(config);
  } catch {
    return content;
  }
}

export function buildKimiHookConfig() {
  const legacyRoot = homeConfigRoot('.kimi');
  const behavior = buildFlatTomlHookConfig(
    KIMI_CONFIG_PATH,
    KIMI_HOOK_SPECS.map(({ hookKey, command }) => ({ event: hookKey, command }))
  );
  return {
    ...behavior,
    resolveConfigRoots: configRoots(envConfigRoot('KIMI_CODE_HOME', '.kimi-code'), legacyRoot),
  };
}
