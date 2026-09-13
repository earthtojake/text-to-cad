import type { CommandCatalog, CommandDef } from '@core/primitives/commands/api';
import type { CommandPaletteItemDef } from './command-palette-item';

export interface CommandPaletteCatalog<TItems extends readonly CommandPaletteItemDef[]> {
  readonly items: TItems;
  byCommandId(id: string): TItems[number] | undefined;
}

export function defineCommandPaletteCatalog<
  const TCommands extends readonly CommandDef[],
  const TItems extends readonly CommandPaletteItemDef[],
>(commandCatalog: CommandCatalog<TCommands>, definitions: TItems): CommandPaletteCatalog<TItems> {
  const byCommandId = new Map<string, TItems[number]>();

  for (const definition of definitions) {
    const { command } = definition;
    if (byCommandId.has(command.id)) {
      throw new Error(`Duplicate command palette command id: ${command.id}`);
    }
    if (commandCatalog.byId(command.id) !== command) {
      throw new Error(`Command palette command is not in command catalog: ${command.id}`);
    }
    if (!command.input.safeParse(undefined).success) {
      throw new Error(`Command palette command must accept undefined input: ${command.id}`);
    }
    byCommandId.set(command.id, definition);
  }

  const items = Object.freeze([...definitions]) as unknown as TItems;
  return Object.freeze({
    items,
    byCommandId: (id: string) => byCommandId.get(id),
  });
}
