import type { HookRegistration, PluginFs } from '@emdash/core/services/agent-plugins/api/plugins';
import {
  EMDASH_MARKER,
  buildMinimalJsonHookConfig,
  configRoots,
  envConfigRoot,
  filterUserHooks,
  hookEntriesFromConfig,
  makeStdinHookCommand,
  readJsonConfig,
  writeJsonConfig,
} from '@emdash/core/services/agent-plugins/api/plugins/helpers';

export const KIRO_CLASSIC_HOOKS_PATH = 'agents/emdash.json';
export const KIRO_V3_HOOKS_PATH = 'hooks/emdash.json';

const KIRO_CLASSIC_SPECS = [
  { hookKey: 'agentSpawn', command: makeStdinHookCommand('session') },
  { hookKey: 'userPromptSubmit', command: makeStdinHookCommand('start') },
  { hookKey: 'preToolUse', command: makeStdinHookCommand('start') },
  { hookKey: 'postToolUse', command: makeStdinHookCommand('start') },
  { hookKey: 'stop', command: makeStdinHookCommand('stop') },
];

const KIRO_V3_SPECS = [
  {
    name: 'emdash-session-start',
    trigger: 'SessionStart',
    command: makeStdinHookCommand('session'),
  },
  {
    name: 'emdash-user-prompt-submit',
    trigger: 'UserPromptSubmit',
    command: makeStdinHookCommand('start'),
  },
  { name: 'emdash-pre-tool-use', trigger: 'PreToolUse', command: makeStdinHookCommand('start') },
  {
    name: 'emdash-post-tool-use',
    trigger: 'PostToolUse',
    command: makeStdinHookCommand('start'),
  },
  { name: 'emdash-stop', trigger: 'Stop', command: makeStdinHookCommand('stop') },
];

const classicBehavior = buildMinimalJsonHookConfig(KIRO_CLASSIC_HOOKS_PATH, KIRO_CLASSIC_SPECS, {
  name: 'emdash',
  description: 'Hardcore-managed Kiro agent configuration for lifecycle hooks.',
});

function buildV3Entry(spec: (typeof KIRO_V3_SPECS)[number]): Record<string, unknown> {
  return {
    name: spec.name,
    trigger: spec.trigger,
    action: { type: 'command', command: spec.command },
    timeout: 10,
    enabled: true,
  };
}

function hasAllV3Hooks(entries: unknown[]): boolean {
  const serialized = entries.map((entry) => JSON.stringify(entry));
  return KIRO_V3_SPECS.every((spec) => serialized.includes(JSON.stringify(buildV3Entry(spec))));
}

export function buildKiroHookConfig() {
  return {
    resolveConfigRoots: configRoots(envConfigRoot('KIRO_HOME', '.kiro')),
    async readHooks(fs: PluginFs): Promise<HookRegistration[]> {
      const classicHooks = await classicBehavior.readHooks(fs);
      const config = await readJsonConfig(fs, KIRO_V3_HOOKS_PATH);
      const v3Installed = hasAllV3Hooks(hookEntriesFromConfig(config, KIRO_V3_HOOKS_PATH));
      return classicHooks.length > 0 && v3Installed
        ? [{ event: 'emdash', command: EMDASH_MARKER }]
        : [];
    },
    async writeHooks(fs: PluginFs, hooks: HookRegistration[]): Promise<string[]> {
      const v3Config = await readJsonConfig(fs, KIRO_V3_HOOKS_PATH);
      const v3Hooks = hookEntriesFromConfig(v3Config, KIRO_V3_HOOKS_PATH);
      const classicPaths = await classicBehavior.writeHooks(fs, hooks);
      await writeJsonConfig(fs, KIRO_V3_HOOKS_PATH, {
        ...v3Config,
        version: 'v1',
        hooks: [...filterUserHooks(v3Hooks), ...KIRO_V3_SPECS.map(buildV3Entry)],
      });

      return [...classicPaths, KIRO_V3_HOOKS_PATH];
    },
    async deleteHooks(fs: PluginFs): Promise<void> {
      const v3Config = await readJsonConfig(fs, KIRO_V3_HOOKS_PATH);
      const v3Hooks = hookEntriesFromConfig(v3Config, KIRO_V3_HOOKS_PATH);
      await classicBehavior.deleteHooks(fs);
      await writeJsonConfig(fs, KIRO_V3_HOOKS_PATH, {
        ...v3Config,
        hooks: filterUserHooks(v3Hooks),
      });
    },
    async getHooksInstalled(fs: PluginFs): Promise<boolean> {
      const classicInstalled = await classicBehavior.getHooksInstalled(fs);
      const v3Config = await readJsonConfig(fs, KIRO_V3_HOOKS_PATH);
      const v3Installed = hasAllV3Hooks(hookEntriesFromConfig(v3Config, KIRO_V3_HOOKS_PATH));
      return classicInstalled && v3Installed;
    },
  };
}
