import { matchKeybindingPress } from 'tinykeys';
import { describe, expect, it } from 'vitest';
import {
  chord,
  chordsEqual,
  code,
  isValidChord,
  parseChord,
  resolveChordSpec,
  toElectronAccelerator,
  tokenKind,
  translateCodeChord,
} from './chord';

describe('chord', () => {
  it('canonicalizes legacy modifiers, modifier order, and character casing', () => {
    expect(chord('Mod+,')).toBe('$mod+,');
    expect(chord('shift+mod+k')).toBe('$mod+Shift+K');
    expect(chord('ctrl+alt+delete')).toBe('Control+Alt+Delete');
    expect(chordsEqual(chord('Mod+K'), chord('$mod+k'))).toBe(true);
  });

  it('preserves char, code, and named token kinds', () => {
    expect(tokenKind(chord('$mod+K'))).toBe('char');
    expect(tokenKind(chord('$mod+KeyK'))).toBe('code');
    expect(tokenKind(chord('$mod+ArrowLeft'))).toBe('named');
  });

  it('validates definitions instead of accepting never-matching strings', () => {
    expect(() => chord('Hyper+K')).toThrow('Unknown chord modifier');
    expect(() => chord('$mod+Braket')).toThrow('Unknown chord key token');
    expect(() => chord('g i')).toThrow('Chord sequences are not supported');
    expect(() => chord('$mod++')).toThrow('Shifted character');
    expect(() => chord('$mod+Alt+K')).toThrow('must use a code token');
    expect(isValidChord('$mod+BracketLeft')).toBe(true);
    expect(isValidChord('$mod+Braket')).toBe(false);
  });

  it('authors positional chords with a typed code helper', () => {
    expect(code(['Mod'], 'BracketLeft')).toBe('$mod+BracketLeft');
    expect(code(['Mod', 'Shift'], 'Equal')).toBe('$mod+Shift+Equal');

    const invalidAuthoring = () => {
      // @ts-expect-error unknown key codes fail at authoring time
      return code(['Mod'], 'Braket');
    };
    expect(invalidAuthoring).toBeTypeOf('function');
  });

  it('parses a canonical chord with tinykeys once', () => {
    const parsed = parseChord(chord('Control+Shift+K'));
    expect(parsed[0]).toEqual(['Control', 'Shift']);
    expect(parsed[2]).toBe('K');
    expect(parseChord(chord('Control+Shift+K'))).toBe(parsed);
  });

  it('gives char and code tokens their respective tinykeys matching semantics', () => {
    const charPress = parseChord(chord('$mod+['));
    const codePress = parseChord(code(['Mod'], 'BracketLeft'));
    const requiredModifier = codePress[0][0];
    const germanEvent = {
      key: 'ü',
      code: 'BracketLeft',
      getModifierState: (modifier: string) => modifier === requiredModifier,
    } as unknown as KeyboardEvent;
    const usEvent = {
      key: '[',
      code: 'BracketLeft',
      getModifierState: (modifier: string) => modifier === requiredModifier,
    } as unknown as KeyboardEvent;

    expect(matchKeybindingPress(germanEvent, charPress)).toBe(false);
    expect(matchKeybindingPress(germanEvent, codePress)).toBe(true);
    expect(matchKeybindingPress(usEvent, charPress)).toBe(true);
    expect(matchKeybindingPress(usEvent, codePress)).toBe(true);
  });

  it('translates code tokens through a supplied layout', () => {
    const binding = code(['Mod'], 'BracketLeft');
    expect(translateCodeChord(binding, new Map([['BracketLeft', 'ü']]))).toBe('$mod+Ü');
    expect(translateCodeChord(binding, new Map())).toBeNull();
    expect(translateCodeChord(chord('$mod+K'), new Map([['KeyK', 'k']]))).toBeNull();
  });

  it('resolves platform-specific and functional chord specs', () => {
    expect(resolveChordSpec({ mac: 'Meta+K', other: 'Control+K' }, { os: 'mac' })).toBe('Meta+K');
    expect(resolveChordSpec({ mac: 'Meta+K', other: 'Control+K' }, { os: 'linux' })).toBe(
      'Control+K'
    );
    expect(
      resolveChordSpec(({ os }) => (os === 'windows' ? 'Alt+F4' : 'Meta+Q'), {
        os: 'windows',
      })
    ).toBe('Alt+F4');
  });

  it('converts chords to Electron accelerator syntax', () => {
    expect(toElectronAccelerator(chord('$mod+ArrowLeft'))).toBe('CmdOrCtrl+Left');
    expect(toElectronAccelerator(code(['Mod'], 'BracketLeft'))).toBe('CmdOrCtrl+[');
    expect(toElectronAccelerator(chord('Meta+K'))).toBe('Command+K');
  });
});
