import { describe, expect, it } from 'vitest';
import type { ChordKeyboardEventLike } from '../api/chord';
import {
  chordFromCaptureEvent,
  isTextInputFocusTarget,
  shouldIgnoreForOptions,
  type KeybindingFocusContext,
} from './chord-from-event';

function focus(overrides: Partial<KeybindingFocusContext> = {}): KeybindingFocusContext {
  return {
    textInputFocused: false,
    editorFocused: false,
    terminalFocused: false,
    browserFocused: false,
    ...overrides,
  };
}

function event(overrides: Partial<ChordKeyboardEventLike> = {}): ChordKeyboardEventLike {
  return {
    key: 'k',
    code: 'KeyK',
    ctrlKey: false,
    metaKey: true,
    altKey: false,
    shiftKey: false,
    repeat: false,
    isComposing: false,
    ...overrides,
  };
}

describe('shouldIgnoreForOptions', () => {
  it('always ignores composition events', () => {
    expect(
      shouldIgnoreForOptions(event({ isComposing: true }), undefined, {
        ...focus(),
      })
    ).toBe(true);
  });

  it('ignores repeat unless the binding explicitly allows it', () => {
    expect(shouldIgnoreForOptions(event({ repeat: true }), undefined, focus())).toBe(true);
    expect(shouldIgnoreForOptions(event({ repeat: true }), { allowRepeat: true }, focus())).toBe(
      false
    );
  });

  it('applies text-input gating per binding', () => {
    expect(
      shouldIgnoreForOptions(
        event(),
        { ignoreWhenTextInputFocused: true },
        focus({ textInputFocused: true })
      )
    ).toBe(true);
    expect(shouldIgnoreForOptions(event(), undefined, focus({ textInputFocused: true }))).toBe(
      false
    );
  });

  it('applies editor and browser gating independently', () => {
    expect(
      shouldIgnoreForOptions(
        event(),
        { ignoreWhenEditorFocused: true },
        focus({ editorFocused: true })
      )
    ).toBe(true);
    expect(
      shouldIgnoreForOptions(
        event(),
        { ignoreWhenBrowserFocused: true },
        focus({ browserFocused: true })
      )
    ).toBe(true);
    expect(
      shouldIgnoreForOptions(
        event(),
        { ignoreWhenEditorFocused: true },
        focus({ terminalFocused: true, textInputFocused: true }),
        { os: 'mac' }
      )
    ).toBe(false);
  });

  it('only allows opted-in terminal shortcuts on non-mac platforms', () => {
    const terminalFocus = focus({ terminalFocused: true, textInputFocused: true });

    expect(shouldIgnoreForOptions(event(), undefined, terminalFocus, { os: 'linux' })).toBe(true);
    expect(
      shouldIgnoreForOptions(event(), { allowWhenTerminalFocused: true }, terminalFocus, {
        os: 'windows',
      })
    ).toBe(false);
    expect(shouldIgnoreForOptions(event(), undefined, terminalFocus, { os: 'mac' })).toBe(false);
  });
});

describe('chordFromCaptureEvent', () => {
  it('records printable keys as layout-independent code chords', () => {
    expect(chordFromCaptureEvent(event(), { os: 'mac' })).toBe('$mod+KeyK');
    expect(
      chordFromCaptureEvent(event({ metaKey: false, ctrlKey: true, key: 'å', code: 'KeyA' }), {
        os: 'linux',
      })
    ).toBe('$mod+KeyA');
  });

  it('records named keys and explicit non-primary modifiers', () => {
    expect(
      chordFromCaptureEvent(
        event({
          key: 'ArrowUp',
          code: 'ArrowUp',
          metaKey: false,
          ctrlKey: true,
          shiftKey: true,
        }),
        { os: 'mac' }
      )
    ).toBe('Control+Shift+ArrowUp');
  });

  it('ignores lone modifiers, composition, and unsupported keys', () => {
    expect(
      chordFromCaptureEvent(event({ key: 'Meta', code: 'MetaLeft' }), { os: 'mac' })
    ).toBeNull();
    expect(chordFromCaptureEvent(event({ isComposing: true }), { os: 'mac' })).toBeNull();
    expect(
      chordFromCaptureEvent(event({ key: 'Unidentified', code: 'Unidentified' }), { os: 'mac' })
    ).toBeNull();
  });
});

describe('isTextInputFocusTarget', () => {
  it('recognizes form controls and editable elements through a structural target', () => {
    const input = { matches: (selector: string) => selector.includes('input') };
    const editable = {
      matches: (selector: string) => selector.includes('[contenteditable]'),
    };

    expect(isTextInputFocusTarget(input)).toBe(true);
    expect(isTextInputFocusTarget(editable)).toBe(true);
  });

  it('returns false for non-elements and ordinary elements', () => {
    expect(isTextInputFocusTarget(null)).toBe(false);
    expect(isTextInputFocusTarget({})).toBe(false);
    expect(isTextInputFocusTarget({ matches: () => false })).toBe(false);
  });
});
