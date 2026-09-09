import { describe, expect, it } from 'vitest';
import { chord, code } from './chord';
import { getElectronTabNavigationDirection, matchesElectronInput } from './electron-input';

describe('matchesElectronInput', () => {
  it('matches portable modifiers and physical code chords', () => {
    expect(
      matchesElectronInput(
        { type: 'keyDown', key: 'P', code: 'KeyP', meta: true, shift: true },
        code(['Mod', 'Shift'], 'KeyP'),
        { os: 'mac' }
      )
    ).toBe(true);
    expect(
      matchesElectronInput(
        { type: 'keyDown', key: 'P', code: 'KeyP', control: true, shift: true },
        code(['Mod', 'Shift'], 'KeyP'),
        { os: 'linux' }
      )
    ).toBe(true);
    expect(
      matchesElectronInput(
        { type: 'keyDown', key: 'P', code: 'KeyP', control: true },
        chord('Mod+P'),
        { os: 'mac' }
      )
    ).toBe(false);
  });

  it('recognizes Electron Control+Tab navigation', () => {
    expect(getElectronTabNavigationDirection({ type: 'keyDown', key: 'Tab', control: true })).toBe(
      'next'
    );
    expect(
      getElectronTabNavigationDirection({
        type: 'keyDown',
        key: 'Tab',
        control: true,
        shift: true,
      })
    ).toBe('previous');
  });
});
