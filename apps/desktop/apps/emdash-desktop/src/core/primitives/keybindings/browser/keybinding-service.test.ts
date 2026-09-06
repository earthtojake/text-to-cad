import { autorun } from 'mobx';
import { describe, expect, it, vi } from 'vitest';
import { defineCommand } from '@core/primitives/commands/api';
import { keybinding } from '@core/primitives/keybindings/api';
import { KeybindingService } from './keybinding-service';

const fixedCommand = defineCommand({
  id: 'test.fixed',
  title: 'Fixed',
  category: 'Test',
  keybinding: keybinding.fixed('Control+F'),
});

const settingsCommand = defineCommand({
  id: 'test.settings',
  title: 'Settings',
  category: 'Test',
  keybinding: keybinding.settings('testSettings', 'Mod+K', {
    ignoreWhenTextInputFocused: true,
  }),
});

const unboundCommand = defineCommand({
  id: 'test.unbound',
  title: 'Unbound',
  category: 'Test',
});

describe('KeybindingService', () => {
  it('resolves and parses fixed and settings-managed bindings', () => {
    const service = new KeybindingService([fixedCommand, settingsCommand, unboundCommand], {
      os: 'linux',
    });

    expect(service.entries.map(({ command, chord }) => [command.id, chord])).toEqual([
      ['test.fixed', 'Control+F'],
      ['test.settings', '$mod+K'],
    ]);
    expect(service.entries[1]?.options?.ignoreWhenTextInputFocused).toBe(true);
    expect(service.chordFor('test.settings')).toBe('$mod+K');
    expect(service.chordFor('test.unbound')).toBeNull();
  });

  it('applies overrides and removes explicitly unbound commands', () => {
    const service = new KeybindingService([fixedCommand, settingsCommand], { os: 'mac' });

    service.setOverrides({ testSettings: 'Meta+Shift+P' });
    expect(service.chordFor('test.settings')).toBe('Shift+Meta+P');
    expect(service.chordFor('test.fixed')).toBe('Control+F');

    service.setOverrides({ testSettings: null });
    expect(service.entries.map((entry) => entry.command.id)).toEqual(['test.fixed']);
  });

  it('recomputes observers when overrides change', () => {
    const service = new KeybindingService([settingsCommand], { os: 'linux' });
    const observed = vi.fn();
    const dispose = autorun(() => observed(service.chordFor('test.settings')));

    service.setOverrides({ testSettings: 'Control+P' });

    expect(observed).toHaveBeenNthCalledWith(1, '$mod+K');
    expect(observed).toHaveBeenNthCalledWith(2, 'Control+P');
    dispose();
  });

  it('projects settings and menu consumers from one effective index', () => {
    const service = new KeybindingService(
      [fixedCommand, settingsCommand, unboundCommand],
      { os: 'mac' },
      [settingsCommand]
    );

    expect(service.settingsEntries()).toEqual([
      {
        category: 'Test',
        entries: [
          {
            command: settingsCommand,
            binding: settingsCommand.keybinding,
            chord: '$mod+K',
            defaultChord: '$mod+K',
          },
        ],
      },
    ]);
    expect(service.snapshotForMenu()).toEqual([
      {
        commandId: settingsCommand.id,
        title: settingsCommand.title,
        accelerator: 'CmdOrCtrl+K',
      },
    ]);
    service.setOverrides({ testSettings: 'Meta+Shift+P' });
    expect(service.snapshotForMenu()[0]?.accelerator).toBe('Shift+Command+P');
  });
});
