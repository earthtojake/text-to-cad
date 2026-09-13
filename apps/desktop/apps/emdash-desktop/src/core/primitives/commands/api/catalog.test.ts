import { describe, expect, it } from 'vitest';
import { keybinding } from '@core/primitives/keybindings/api';
import { defineCommandCatalog } from './catalog';
import { defineCommand } from './define-command';

describe('defineCommandCatalog', () => {
  it('preserves tuple definitions and resolves them by id', () => {
    const command = defineCommand({
      id: 'app.test',
      title: 'Test',
      category: 'Test',
    });
    const catalog = defineCommandCatalog([command] as const);

    expect(catalog.defs).toEqual([command]);
    expect(catalog.byId('app.test')).toBe(command);
    expect(Object.isFrozen(catalog.defs)).toBe(true);
  });

  it('rejects duplicate command ids', () => {
    const command = defineCommand({
      id: 'app.test',
      title: 'Test',
      category: 'Test',
    });

    expect(() => defineCommandCatalog([command, command])).toThrow(
      'Duplicate command id: app.test'
    );
  });

  it('rejects duplicate settings keys', () => {
    const first = defineCommand({
      id: 'app.first',
      title: 'First',
      category: 'Test',
      keybinding: keybinding.settings('shared', 'Mod+1'),
    });
    const second = defineCommand({
      id: 'app.second',
      title: 'Second',
      category: 'Test',
      keybinding: keybinding.settings('shared', 'Mod+2'),
    });

    expect(() => defineCommandCatalog([first, second])).toThrow(
      'Duplicate keybinding settings key shared: app.first, app.second'
    );
  });
});
