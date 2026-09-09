import { describe, expect, it } from 'vitest';
import {
  CODE_TO_US_CHAR,
  findConflicts,
  resolveChordSpec,
  type KeybindingEntry,
} from '@core/primitives/keybindings/api';
import { SCOPE_CATALOG } from '../browser/scope-catalog';
import { COMMAND_CATALOG } from './command-catalog';

describe('COMMAND_CATALOG', () => {
  it('keeps settings keys unique', () => {
    const keys = COMMAND_CATALOG.defs.flatMap((command) =>
      command.keybinding?.kind === 'settings' ? [command.keybinding.settingsKey] : []
    );
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('allows undefined input for every keybinding-invocable command', () => {
    for (const command of COMMAND_CATALOG.defs) {
      if (!command.keybinding) continue;
      expect(command.input.safeParse(undefined).success, command.id).toBe(true);
    }
  });

  it('has no same-scope configurable keybinding conflicts under the US layout', () => {
    const groupByCommandId = new Map<string, string>();
    for (const scope of SCOPE_CATALOG) {
      for (const command of scope.commands) {
        groupByCommandId.set(command.id, scope.id);
      }
    }
    const entries: KeybindingEntry[] = COMMAND_CATALOG.defs.flatMap((command) =>
      command.keybinding
        ? [
            {
              id: command.id,
              group: groupByCommandId.get(command.id),
              binding: command.keybinding,
            },
          ]
        : []
    );

    for (const entry of entries) {
      const chord =
        entry.binding.kind === 'fixed'
          ? resolveChordSpec(entry.binding.chord, { os: 'linux' })
          : resolveChordSpec(entry.binding.defaultChord, { os: 'linux' });
      const errors = findConflicts(
        entries,
        chord,
        entry.id,
        {},
        { os: 'linux' },
        CODE_TO_US_CHAR
      ).filter((conflict) => conflict.severity === 'error');
      expect(errors, entry.id).toEqual([]);
    }
  });
});
