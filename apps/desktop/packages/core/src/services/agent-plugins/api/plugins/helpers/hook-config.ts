import * as toml from 'smol-toml';
import type { PluginFs } from '#primitives/plugin-fs/api';
import type { HookRegistration } from '#services/agent-plugins/api/plugins/capabilities/hooks';
import { EMDASH_MARKER, filterUserHooks } from './hooks';

export type { HookCommandOptions } from './hooks';

// ── JSON config helpers ────────────────────────────────────────────────────

export async function readJsonConfig(fs: PluginFs, path: string): Promise<Record<string, unknown>> {
  const content = await fs.read(path);
  if (!content || content.trim() === '') return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch (error) {
    throw new Error(`Failed to parse ${path}: ${String(error)}`);
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error(`Failed to parse ${path}: expected an object at the config root`);
  }
  return parsed as Record<string, unknown>;
}

export async function writeJsonConfig(
  fs: PluginFs,
  path: string,
  config: Record<string, unknown>
): Promise<void> {
  await fs.write(path, JSON.stringify(config, null, 2) + '\n');
}

// ── TOML config helpers ────────────────────────────────────────────────────

export async function readTomlConfig(fs: PluginFs, path: string): Promise<Record<string, unknown>> {
  const content = await fs.read(path);
  if (!content) return {};
  try {
    return (toml.parse(content) as Record<string, unknown>) ?? {};
  } catch (error) {
    throw new Error(`Failed to parse ${path}: ${String(error)}`);
  }
}

export async function writeTomlConfig(
  fs: PluginFs,
  path: string,
  config: Record<string, unknown>
): Promise<void> {
  await fs.write(path, toml.stringify(config));
}

function isConfigObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Read a root-level `hooks` array without replacing structurally incompatible user config. */
export function hookEntriesFromConfig(
  config: Record<string, unknown>,
  configPath: string
): Record<string, unknown>[] {
  const hooks = config.hooks;
  if (hooks === undefined) return [];
  if (!Array.isArray(hooks) || !hooks.every(isConfigObject)) {
    throw new Error(`Invalid ${configPath}: expected "hooks" to be an array of objects`);
  }
  return hooks;
}

/** Read an event-keyed `hooks` object without replacing structurally incompatible user config. */
export function hookMapFromConfig(
  config: Record<string, unknown>,
  configPath: string
): Record<string, Record<string, unknown>[]> {
  const hooks = config.hooks;
  if (hooks === undefined) return {};
  if (!isConfigObject(hooks)) {
    throw new Error(`Invalid ${configPath}: expected "hooks" to be an object`);
  }
  for (const [hookKey, entries] of Object.entries(hooks)) {
    if (!Array.isArray(entries) || !entries.every(isConfigObject)) {
      throw new Error(
        `Invalid ${configPath}: expected "hooks.${hookKey}" to be an array of objects`
      );
    }
  }
  return hooks as Record<string, Record<string, unknown>[]>;
}

// ── Entry builders ─────────────────────────────────────────────────────────

/** Claude/Codex-style nested entry: `{ hooks: [{ type: 'command', command }] }` */
export function buildNestedEntry(command: string): Record<string, unknown> {
  return { hooks: [{ type: 'command', command }] };
}

/** Copilot-style flat entry: `{ type: 'command', command }` */
export function buildFlatEntry(command: string): Record<string, unknown> {
  return { type: 'command', command };
}

/** Kiro-style minimal entry: `{ command }` */
export function buildMinimalEntry(command: string): Record<string, unknown> {
  return { command };
}

// ── Merge helpers ───────────────────────────────────────────────────────────

export function mergeNestedEntries(
  existing: Record<string, unknown>[],
  command: string
): Record<string, unknown>[] {
  return [...filterUserHooks(existing), buildNestedEntry(command)];
}

export function mergeFlatEntries(
  existing: Record<string, unknown>[],
  command: string
): Record<string, unknown>[] {
  return [...filterUserHooks(existing), buildFlatEntry(command)];
}

export function mergeMinimalEntries(
  existing: Record<string, unknown>[],
  command: string
): Record<string, unknown>[] {
  return [...filterUserHooks(existing), buildMinimalEntry(command)];
}

// ── Generic hook config builders ────────────────────────────────────────────

type HookSpec = { hookKey: string; command: string };
type FlatTomlHookConfigOptions = {
  beforeWrite?: (fs: PluginFs) => Promise<void>;
  afterWrite?: (fs: PluginFs) => Promise<string[]>;
  afterDelete?: (fs: PluginFs) => Promise<void>;
  stringifyEntry?: (entry: Record<string, unknown>) => string;
};

/**
 * Build an `IHooksBehavior` for agents that store hooks as a flat TOML array:
 *   `[[hooks]]` / `{ hooks = [{ ... }] }`
 */
export function buildFlatTomlHookConfig(
  configPath: string,
  entries: Record<string, unknown>[],
  options: FlatTomlHookConfigOptions = {}
) {
  const stringifyEntry = options.stringifyEntry ?? JSON.stringify;
  const hasEmdashHook = (config: Record<string, unknown>) => {
    const serializedEntries = hookEntriesFromConfig(config, configPath).map((entry) =>
      stringifyEntry(entry)
    );
    return entries.every((entry) => serializedEntries.includes(stringifyEntry(entry)));
  };

  return {
    async readHooks(fs: PluginFs): Promise<HookRegistration[]> {
      const config = await readTomlConfig(fs, configPath);
      return hasEmdashHook(config) ? [{ event: 'emdash', command: EMDASH_MARKER }] : [];
    },
    async writeHooks(fs: PluginFs, _hooks: HookRegistration[]): Promise<string[]> {
      const config = await readTomlConfig(fs, configPath);
      await options.beforeWrite?.(fs);
      const userHooks = filterUserHooks(hookEntriesFromConfig(config, configPath), stringifyEntry);
      await writeTomlConfig(fs, configPath, { ...config, hooks: [...userHooks, ...entries] });
      const extraPaths = (await options.afterWrite?.(fs)) ?? [];
      return [configPath, ...extraPaths];
    },
    async deleteHooks(fs: PluginFs): Promise<void> {
      const config = await readTomlConfig(fs, configPath);
      await writeTomlConfig(fs, configPath, {
        ...config,
        hooks: filterUserHooks(hookEntriesFromConfig(config, configPath), stringifyEntry),
      });
      await options.afterDelete?.(fs);
    },
    async getHooksInstalled(fs: PluginFs): Promise<boolean> {
      const config = await readTomlConfig(fs, configPath);
      return hasEmdashHook(config);
    },
  };
}

/**
 * Build an `IHooksBehavior` for agents that store hooks in a JSON file using
 * the nested format:
 *   `{ hooks: { <Event>: [{ hooks: [{ type: 'command', command }] }] } }`
 *
 * Pass pre-built command strings (from `makeStdinHookCommand`, etc.) in `hookSpecs`.
 */
export function buildNestedJsonHookConfig(configPath: string, hookSpecs: HookSpec[]) {
  const specsByHookKey = new Map<string, HookSpec[]>();
  for (const spec of hookSpecs) {
    specsByHookKey.set(spec.hookKey, [...(specsByHookKey.get(spec.hookKey) ?? []), spec]);
  }

  const hasAllManagedNestedEntries = (hooks: Record<string, unknown[]>): boolean =>
    [...specsByHookKey].every(([hookKey, specs]) => {
      const entries = Array.isArray(hooks[hookKey]) ? hooks[hookKey] : [];
      const serializedEntries = entries.map((entry) => JSON.stringify(entry));
      return specs.every(({ command }) =>
        serializedEntries.includes(JSON.stringify(buildNestedEntry(command)))
      );
    });

  return {
    async readHooks(fs: PluginFs): Promise<HookRegistration[]> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      return hasAllManagedNestedEntries(hooks) ? [{ event: 'emdash', command: EMDASH_MARKER }] : [];
    },
    async writeHooks(fs: PluginFs, _hooks: HookRegistration[]): Promise<string[]> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      for (const [hookKey, specs] of specsByHookKey) {
        const existing = Array.isArray(hooks[hookKey]) ? hooks[hookKey] : [];
        hooks[hookKey] = [
          ...filterUserHooks(existing),
          ...specs.map(({ command }) => buildNestedEntry(command)),
        ];
      }
      await writeJsonConfig(fs, configPath, { ...config, hooks });
      return [configPath];
    },
    async deleteHooks(fs: PluginFs): Promise<void> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      for (const key of Object.keys(hooks)) {
        hooks[key] = filterUserHooks(hooks[key]);
      }
      await writeJsonConfig(fs, configPath, { ...config, hooks });
    },
    async getHooksInstalled(fs: PluginFs): Promise<boolean> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      return hasAllManagedNestedEntries(hooks);
    },
  };
}

/**
 * Build an `IHooksBehavior` for agents that store hooks in a JSON file using
 * the flat format: `{ hooks: { <Event>: [{ type: 'command', command }] } }`
 *
 * Optionally pass `extraFields` to merge at the config root (e.g. copilot `version`).
 */
export function buildFlatJsonHookConfig(
  configPath: string,
  hookSpecs: HookSpec[],
  extraRoot?: Record<string, unknown>
) {
  return {
    async readHooks(fs: PluginFs): Promise<HookRegistration[]> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      const installed = hookSpecs.every(({ hookKey, command }) => {
        const entries = Array.isArray(hooks[hookKey]) ? hooks[hookKey] : [];
        return entries.some(
          (entry) => JSON.stringify(entry) === JSON.stringify(buildFlatEntry(command))
        );
      });
      return installed ? [{ event: 'emdash', command: EMDASH_MARKER }] : [];
    },
    async writeHooks(fs: PluginFs, _hooks: HookRegistration[]): Promise<string[]> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      for (const { hookKey, command } of hookSpecs) {
        const existing = Array.isArray(hooks[hookKey]) ? hooks[hookKey] : [];
        hooks[hookKey] = mergeFlatEntries(existing, command);
      }
      await writeJsonConfig(fs, configPath, { ...config, ...extraRoot, hooks });
      return [configPath];
    },
    async deleteHooks(fs: PluginFs): Promise<void> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      for (const key of Object.keys(hooks)) {
        hooks[key] = filterUserHooks(hooks[key]);
      }
      await writeJsonConfig(fs, configPath, { ...config, hooks });
    },
    async getHooksInstalled(fs: PluginFs): Promise<boolean> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      return hookSpecs.every(({ hookKey, command }) => {
        const entries = Array.isArray(hooks[hookKey]) ? hooks[hookKey] : [];
        return entries.some(
          (entry) => JSON.stringify(entry) === JSON.stringify(buildFlatEntry(command))
        );
      });
    },
  };
}

/**
 * Build an `IHooksBehavior` for agents that store hooks as a minimal
 * `{ command }` object array under `config.hooks.<hookKey>`.
 */
export function buildMinimalJsonHookConfig(
  configPath: string,
  hookSpecs: HookSpec[],
  extraRoot?: Record<string, unknown>
) {
  return {
    async readHooks(fs: PluginFs): Promise<HookRegistration[]> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      const installed = hookSpecs.every(({ hookKey, command }) => {
        const entries = Array.isArray(hooks[hookKey]) ? hooks[hookKey] : [];
        return entries.some(
          (entry) => JSON.stringify(entry) === JSON.stringify(buildMinimalEntry(command))
        );
      });
      return installed ? [{ event: 'emdash', command: EMDASH_MARKER }] : [];
    },
    async writeHooks(fs: PluginFs, _hooks: HookRegistration[]): Promise<string[]> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      for (const { hookKey, command } of hookSpecs) {
        const existing = Array.isArray(hooks[hookKey]) ? hooks[hookKey] : [];
        hooks[hookKey] = mergeMinimalEntries(existing, command);
      }
      await writeJsonConfig(fs, configPath, { ...config, ...extraRoot, hooks });
      return [configPath];
    },
    async deleteHooks(fs: PluginFs): Promise<void> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      for (const key of Object.keys(hooks)) {
        hooks[key] = filterUserHooks(hooks[key]);
      }
      await writeJsonConfig(fs, configPath, { ...config, hooks });
    },
    async getHooksInstalled(fs: PluginFs): Promise<boolean> {
      const config = await readJsonConfig(fs, configPath);
      const hooks = hookMapFromConfig(config, configPath);
      return hookSpecs.every(({ hookKey, command }) => {
        const entries = Array.isArray(hooks[hookKey]) ? hooks[hookKey] : [];
        return entries.some(
          (entry) => JSON.stringify(entry) === JSON.stringify(buildMinimalEntry(command))
        );
      });
    },
  };
}
