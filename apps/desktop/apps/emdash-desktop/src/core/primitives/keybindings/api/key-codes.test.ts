import { describe, expect, expectTypeOf, it } from 'vitest';
import { CODE_TO_US_CHAR, isKeyCode } from './key-codes';
import type { KEY_CODES, KeyCode } from './key-codes';

describe('key codes', () => {
  it('derives the KeyCode union from the runtime source of truth', () => {
    expectTypeOf<(typeof KEY_CODES)[number]>().toEqualTypeOf<KeyCode>();
    expect(isKeyCode('BracketLeft')).toBe(true);
    expect(isKeyCode('Braket')).toBe(false);
  });

  it('keeps every US reference translation inside KEY_CODES', () => {
    for (const key of Object.keys(CODE_TO_US_CHAR)) {
      expect(isKeyCode(key), `${key} should be a known key code`).toBe(true);
    }
  });

  it('provides stable US reference translations', () => {
    expect(CODE_TO_US_CHAR.BracketLeft).toBe('[');
    expect(CODE_TO_US_CHAR.Backslash).toBe('\\');
    expect(CODE_TO_US_CHAR.KeyK).toBe('k');
  });
});
