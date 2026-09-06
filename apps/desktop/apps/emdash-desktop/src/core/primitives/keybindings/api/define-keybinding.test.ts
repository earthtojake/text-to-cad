import { describe, expect, expectTypeOf, it } from 'vitest';
import { code } from './chord';
import {
  keybinding,
  resolveEffectiveChord,
  type Keybinding,
  type SettingsKeybinding,
} from './define-keybinding';

const linux = { os: 'linux' } as const;

describe('keybinding', () => {
  it('creates frozen fixed and settings bindings', () => {
    const fixed = keybinding.fixed('Escape', { allowRepeat: false });
    const configurable = keybinding.settings('archiveTask', 'Mod+Shift+E', {
      ignoreWhenTextInputFocused: true,
    });

    expect(fixed).toEqual({
      kind: 'fixed',
      chord: 'Escape',
      options: { allowRepeat: false },
    });
    expect(configurable).toEqual({
      kind: 'settings',
      settingsKey: 'archiveTask',
      defaultChord: '$mod+Shift+E',
      options: { ignoreWhenTextInputFocused: true },
    });
    expect(Object.isFrozen(fixed)).toBe(true);
    expect(Object.isFrozen(fixed.options)).toBe(true);
    expect(Object.isFrozen(configurable)).toBe(true);
    expect(Object.isFrozen(configurable.options)).toBe(true);
    expectTypeOf(configurable).toEqualTypeOf<SettingsKeybinding<'archiveTask'>>();
    expectTypeOf(configurable).toMatchTypeOf<Keybinding<'archiveTask'>>();
  });

  it('validates static chord specs and settings keys when defined', () => {
    expect(() => keybinding.fixed('not-a-key')).toThrow('Unknown chord key token');
    expect(() => keybinding.settings(' ', 'Mod+K')).toThrow(
      'A keybinding settings key must not be empty'
    );
  });

  it('resolves fixed chords without consulting overrides', () => {
    const binding = keybinding.fixed({ mac: 'Meta+K', other: 'Control+K' });
    expect(resolveEffectiveChord(binding, { ignored: null }, linux)).toBe('Control+K');
  });

  it('layers settings overrides above defaults', () => {
    const binding = keybinding.settings('open', 'Mod+K');

    expect(resolveEffectiveChord(binding, {}, linux)).toBe('$mod+K');
    expect(resolveEffectiveChord(binding, { open: 'Control+O' }, linux)).toBe('Control+O');
    expect(resolveEffectiveChord(binding, { open: null }, linux)).toBeNull();
  });

  it('normalizes legacy spellings and accepts code-token overrides', () => {
    const binding = keybinding.settings('navigateBack', 'Mod+[');

    expect(resolveEffectiveChord(binding, { navigateBack: 'Mod+K' }, linux)).toBe('$mod+K');
    expect(resolveEffectiveChord(binding, { navigateBack: '$mod+BracketLeft' }, linux)).toBe(
      '$mod+BracketLeft'
    );
  });

  it('falls back to the default for invalid persisted overrides', () => {
    const binding = keybinding.settings('navigateBack', code(['Mod'], 'BracketLeft'));

    expect(resolveEffectiveChord(binding, { navigateBack: 'garbage' }, linux)).toBe(
      '$mod+BracketLeft'
    );
    expect(resolveEffectiveChord(binding, { navigateBack: '$mod+Braket' }, linux)).toBe(
      '$mod+BracketLeft'
    );
    expect(resolveEffectiveChord(binding, { navigateBack: 'g i' }, linux)).toBe('$mod+BracketLeft');
  });

  it('evaluates functional defaults against the platform context', () => {
    const binding = keybinding.settings('quit', ({ os }) =>
      os === 'mac' ? 'Meta+Q' : 'Control+Q'
    );

    expect(resolveEffectiveChord(binding, {}, { os: 'mac' })).toBe('Meta+Q');
    expect(resolveEffectiveChord(binding, {}, { os: 'windows' })).toBe('Control+Q');
  });
});
