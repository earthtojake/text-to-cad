import type { PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import type { HookRegistration } from '@emdash/core/services/agent-plugins/api/plugins';
import {
  EMDASH_MARKER,
  buildNestedEntry,
  configRoots,
  filterUserHooks,
  homeConfigRoot,
  hookMapFromConfig,
  makeStdinHookCommand,
  readJsonConfig,
  writeJsonConfig,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';

export const GOOSE_PLUGIN_MANIFEST_PATH = 'plugins/hardcore/plugin.json';
export const GOOSE_HOOKS_PATH = 'plugins/hardcore/hooks/hooks.json';

const GOOSE_PLUGIN_MANIFEST = {
  name: 'hardcore',
  version: '0.1.0',
  description: 'Hardcore lifecycle hooks for Goose sessions',
};

const GOOSE_HOOK_SPECS = [
  { hookKey: 'SessionStart', command: makeStdinHookCommand('session') },
  { hookKey: 'UserPromptSubmit', command: makeStdinHookCommand('start') },
  { hookKey: 'PreToolUse', command: makeStdinHookCommand('start') },
  { hookKey: 'PostToolUse', command: makeStdinHookCommand('tool-use') },
  { hookKey: 'PostToolUseFailure', command: makeStdinHookCommand('error') },
  { hookKey: 'Stop', command: makeStdinHookCommand('stop') },
  { hookKey: 'SessionEnd', command: makeStdinHookCommand('stop') },
];

const specsByHookKey = new Map<string, typeof GOOSE_HOOK_SPECS>();
for (const spec of GOOSE_HOOK_SPECS) {
  specsByHookKey.set(spec.hookKey, [...(specsByHookKey.get(spec.hookKey) ?? []), spec]);
}

function hasAllManagedHooks(hooks: Record<string, unknown[]>): boolean {
  return [...specsByHookKey].every(([hookKey, specs]) => {
    const entries = Array.isArray(hooks[hookKey]) ? hooks[hookKey] : [];
    const serializedEntries = entries.map((entry) => JSON.stringify(entry));
    return specs.every(({ command }) =>
      serializedEntries.includes(JSON.stringify(buildNestedEntry(command)))
    );
  });
}

export function buildGooseHookConfig() {
  return {
    resolveConfigRoots: configRoots(homeConfigRoot('.agents')),
    async readHooks(fs: PluginFs): Promise<HookRegistration[]> {
      const config = await readJsonConfig(fs, GOOSE_HOOKS_PATH);
      return hasAllManagedHooks(hookMapFromConfig(config, GOOSE_HOOKS_PATH))
        ? [{ event: 'emdash', command: EMDASH_MARKER }]
        : [];
    },
    async writeHooks(fs: PluginFs, _hooks: HookRegistration[]): Promise<string[]> {
      await writeJsonConfig(fs, GOOSE_PLUGIN_MANIFEST_PATH, GOOSE_PLUGIN_MANIFEST);

      const config = await readJsonConfig(fs, GOOSE_HOOKS_PATH);
      const hooks = hookMapFromConfig(config, GOOSE_HOOKS_PATH);

      for (const [hookKey, specs] of specsByHookKey) {
        const existing = Array.isArray(hooks[hookKey]) ? hooks[hookKey] : [];
        hooks[hookKey] = [
          ...filterUserHooks(existing),
          ...specs.map(({ command }) => buildNestedEntry(command)),
        ];
      }

      await writeJsonConfig(fs, GOOSE_HOOKS_PATH, { ...config, hooks });
      return [GOOSE_PLUGIN_MANIFEST_PATH, GOOSE_HOOKS_PATH];
    },
    async deleteHooks(fs: PluginFs): Promise<void> {
      const config = await readJsonConfig(fs, GOOSE_HOOKS_PATH);
      const hooks = hookMapFromConfig(config, GOOSE_HOOKS_PATH);
      for (const key of Object.keys(hooks)) {
        hooks[key] = filterUserHooks(hooks[key]);
      }
      await writeJsonConfig(fs, GOOSE_HOOKS_PATH, { ...config, hooks });
    },
    async getHooksInstalled(fs: PluginFs): Promise<boolean> {
      const config = await readJsonConfig(fs, GOOSE_HOOKS_PATH);
      return hasAllManagedHooks(hookMapFromConfig(config, GOOSE_HOOKS_PATH));
    },
  };
}
