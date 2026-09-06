import type { CommandDef } from '@core/primitives/commands/api';

export interface CommandPaletteItemDef<TCommand extends CommandDef = CommandDef> {
  readonly command: TCommand;
  readonly aliases?: readonly string[];
}

export interface DefineCommandPaletteItemOptions<TCommand extends CommandDef> {
  readonly command: TCommand;
  readonly aliases?: readonly string[];
}

export function defineCommandPaletteItem<TCommand extends CommandDef>(
  options: DefineCommandPaletteItemOptions<TCommand>
): CommandPaletteItemDef<TCommand> {
  return Object.freeze({
    command: options.command,
    aliases: Object.freeze([...(options.aliases ?? [])]),
  });
}
