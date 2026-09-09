import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import type {
  CanonicalHookEvent,
  HookRegistration,
} from '@emdash/core/services/agent-plugins/api/plugins';
import {
  EMDASH_MARKER,
  buildNestedEntry,
  configRoots,
  defaultHookEventParser,
  envConfigRoot,
  filterUserHooks,
  hookMapFromConfig,
  makeHookPostCommand,
  makeNotificationHookCommand,
  readJsonConfig,
  readTomlConfig,
  writeJsonConfig,
  writeTomlConfig,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';
import * as toml from 'smol-toml';

export const CODEX_CONFIG_PATH = 'config.toml';
export const CODEX_LEGACY_HOOKS_PATH = 'hooks.json';

const LEGACY_CODEX_NOTIFY_COMMAND = [
  'bash',
  '-c',
  'curl -sf -X POST ' +
    "-H 'Content-Type: application/json' " +
    '-H "X-Emdash-Token: $EMDASH_HOOK_NONCE" ' +
    '-H "X-Emdash-Pty-Id: $EMDASH_PTY_ID" ' +
    '-H "X-Emdash-Event-Type: notification" ' +
    '-d "$1" ' +
    '"http://127.0.0.1:$EMDASH_HOOK_PORT/hook" || true',
  '_',
];

function isLegacyCodexNotify(value: unknown): boolean {
  if (!Array.isArray(value)) return false;
  if (JSON.stringify(value) === JSON.stringify(LEGACY_CODEX_NOTIFY_COMMAND)) return true;
  const [command, noProfile, fileFlag, scriptPath] = value.map((item) => String(item));
  return (
    command.toLowerCase() === 'powershell.exe' &&
    noProfile === '-NoProfile' &&
    fileFlag === '-File' &&
    typeof scriptPath === 'string' &&
    scriptPath.endsWith('emdash-codex-notify.ps1')
  );
}

async function removeLegacyCodexNotify(fs: PluginFs): Promise<void> {
  const raw = await fs.read(CODEX_CONFIG_PATH);
  if (!raw) return;

  let config: Record<string, unknown>;
  try {
    config = toml.parse(raw) as Record<string, unknown>;
  } catch {
    return;
  }

  if (!isLegacyCodexNotify(config.notify)) return;

  delete config.notify;
  await fs.write(CODEX_CONFIG_PATH, toml.stringify(config));
}

function isConfigObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getHooks(
  config: Record<string, unknown>,
  configPath: string
): Record<string, Record<string, unknown>[]> {
  if (configPath !== CODEX_CONFIG_PATH) return hookMapFromConfig(config, configPath);

  const hooks = config.hooks;
  if (hooks === undefined) return {};
  if (!isConfigObject(hooks)) {
    throw new Error(`Invalid ${configPath}: expected "hooks" to be an object`);
  }

  // Codex owns this map and updates it as hook definitions are reviewed or disabled.
  // It shares the `hooks` table with event arrays but is not itself an event.
  const { state, ...eventHooks } = hooks;
  if (state !== undefined && !isConfigObject(state)) {
    throw new Error(`Invalid ${configPath}: expected "hooks.state" to be an object`);
  }

  return hookMapFromConfig({ hooks: eventHooks }, configPath);
}

function configWithEventHooks(
  config: Record<string, unknown>,
  eventHooks: Record<string, Record<string, unknown>[]>
): Record<string, unknown> {
  const existingHooks = isConfigObject(config.hooks) ? config.hooks : {};
  return { ...config, hooks: { ...existingHooks, ...eventHooks } };
}

function hasCodexEmdashHooks(hooks: Record<string, unknown[]>, specs: [string, string][]): boolean {
  return specs.every(([key, command]) => {
    const entries = Array.isArray(hooks[key]) ? hooks[key] : [];
    return entries.some(
      (entry) => JSON.stringify(entry) === JSON.stringify(buildNestedEntry(command))
    );
  });
}

async function readLegacyHooks(fs: PluginFs): Promise<Record<string, unknown[]>> {
  const config = await readJsonConfig(fs, CODEX_LEGACY_HOOKS_PATH);
  return getHooks(config, CODEX_LEGACY_HOOKS_PATH);
}

async function migrateLegacyHooks(
  fs: PluginFs,
  hooks: Record<string, unknown[]>
): Promise<() => Promise<void>> {
  const legacyHooks = await readLegacyHooks(fs);

  for (const [key, entries] of Object.entries(legacyHooks)) {
    if (!Array.isArray(entries)) continue;

    const userEntries = filterUserHooks(entries);
    if (!userEntries.length) continue;

    const existing = Array.isArray(hooks[key]) ? hooks[key] : [];
    hooks[key] = [...filterUserHooks(existing), ...userEntries];
  }

  return async () => {
    await fs.delete(CODEX_LEGACY_HOOKS_PATH).catch(() => {});
  };
}

function makeCodexSessionStartCommand(): string {
  const post = makeHookPostCommand('session-start', 'stdin', {});
  if (process.platform === 'win32') return post;
  return `INPUT="\${1:-$(cat)}"; printf '%s' "$INPUT" | { ${post}; }`;
}

/**
 * Codex sends `{ type: 'agent-turn-complete' }` as its stop signal instead
 * of a plain 'stop' event type, and uses fixed `notification_type` values
 * in its hook payloads rather than piping JSON.
 */
function parseCodexHookEvent(eventType: string, body: Record<string, unknown>): CanonicalHookEvent {
  if (eventType === 'session-start') {
    const candidates = [body.session_id, body.resource_id, body.resourceId, body.sessionId];
    for (const candidate of candidates) {
      if (typeof candidate === 'string' && candidate.trim()) {
        return { kind: 'session', providerSessionId: candidate.trim() };
      }
    }
    return { kind: 'ignore' };
  }

  if (eventType === 'notification') {
    const nt = body.notification_type;
    if (nt === 'idle_prompt' || (typeof nt !== 'string' && body.type === 'agent-turn-complete')) {
      return { kind: 'status', type: 'stop' };
    }
    if (nt === 'permission_prompt') {
      return { kind: 'status', type: 'notification', notificationType: 'permission_prompt' };
    }
  }

  return defaultHookEventParser(eventType, body);
}

export function buildCodexHookConfig() {
  const stopCmd = makeNotificationHookCommand('idle_prompt');
  const permCmd = makeNotificationHookCommand('permission_prompt');
  const sessionCmd = makeCodexSessionStartCommand();
  const specs: [string, string][] = [
    ['Stop', stopCmd],
    ['PermissionRequest', permCmd],
    ['SessionStart', sessionCmd],
  ];

  return {
    resolveConfigRoots: configRoots(envConfigRoot('CODEX_HOME', '.codex')),
    async readHooks(fs: PluginFs): Promise<HookRegistration[]> {
      const config = await readTomlConfig(fs, CODEX_CONFIG_PATH);
      if (hasCodexEmdashHooks(getHooks(config, CODEX_CONFIG_PATH), specs)) {
        return [{ event: 'emdash', command: EMDASH_MARKER }];
      }

      return hasCodexEmdashHooks(await readLegacyHooks(fs), specs)
        ? [{ event: 'emdash', command: EMDASH_MARKER }]
        : [];
    },
    async writeHooks(fs: PluginFs, _hooks: HookRegistration[]): Promise<string[]> {
      const config = await readTomlConfig(fs, CODEX_CONFIG_PATH);
      const hooks = getHooks(config, CODEX_CONFIG_PATH);
      const cleanupLegacy = await migrateLegacyHooks(fs, hooks);

      for (const [key, cmd] of specs) {
        const existing = Array.isArray(hooks[key]) ? hooks[key] : [];
        hooks[key] = [...filterUserHooks(existing), buildNestedEntry(cmd)];
      }
      await writeTomlConfig(fs, CODEX_CONFIG_PATH, configWithEventHooks(config, hooks));
      await cleanupLegacy();
      await removeLegacyCodexNotify(fs).catch(() => {});
      return [CODEX_CONFIG_PATH];
    },
    async deleteHooks(fs: PluginFs): Promise<void> {
      const config = await readTomlConfig(fs, CODEX_CONFIG_PATH);
      const hooks = getHooks(config, CODEX_CONFIG_PATH);
      for (const key of Object.keys(hooks)) {
        hooks[key] = filterUserHooks(hooks[key]);
      }
      await writeTomlConfig(fs, CODEX_CONFIG_PATH, configWithEventHooks(config, hooks));

      const legacyConfig = await readJsonConfig(fs, CODEX_LEGACY_HOOKS_PATH);
      const legacyHooks = getHooks(legacyConfig, CODEX_LEGACY_HOOKS_PATH);
      for (const key of Object.keys(legacyHooks)) {
        legacyHooks[key] = filterUserHooks(legacyHooks[key]);
      }
      if (Object.values(legacyHooks).some((entries) => Array.isArray(entries) && entries.length)) {
        await writeJsonConfig(fs, CODEX_LEGACY_HOOKS_PATH, { ...legacyConfig, hooks: legacyHooks });
      } else {
        await fs.delete(CODEX_LEGACY_HOOKS_PATH).catch(() => {});
      }
    },
    async getHooksInstalled(fs: PluginFs): Promise<boolean> {
      const config = await readTomlConfig(fs, CODEX_CONFIG_PATH);
      return (
        hasCodexEmdashHooks(getHooks(config, CODEX_CONFIG_PATH), specs) ||
        hasCodexEmdashHooks(await readLegacyHooks(fs), specs)
      );
    },
    parseHookEvent: parseCodexHookEvent,
  };
}
