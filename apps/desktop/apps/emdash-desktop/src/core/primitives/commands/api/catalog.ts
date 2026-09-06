import type { CommandDef } from './define-command';

export interface CommandCatalog<TDefs extends readonly CommandDef[]> {
  readonly defs: TDefs;
  byId(id: string): TDefs[number] | undefined;
}

export function defineCommandCatalog<const TDefs extends readonly CommandDef[]>(
  definitions: TDefs
): CommandCatalog<TDefs> {
  const byId = new Map<string, TDefs[number]>();
  const commandBySettingsKey = new Map<string, TDefs[number]>();

  for (const definition of definitions) {
    if (byId.has(definition.id)) {
      throw new Error(`Duplicate command id: ${definition.id}`);
    }
    byId.set(definition.id, definition);

    const binding = definition.keybinding;
    if (binding?.kind !== 'settings') continue;
    const existing = commandBySettingsKey.get(binding.settingsKey);
    if (existing) {
      throw new Error(
        `Duplicate keybinding settings key ${binding.settingsKey}: ${existing.id}, ${definition.id}`
      );
    }
    commandBySettingsKey.set(binding.settingsKey, definition);
  }

  const defs = Object.freeze([...definitions]) as unknown as TDefs;
  return Object.freeze({
    defs,
    byId: (id: string) => byId.get(id),
  });
}
