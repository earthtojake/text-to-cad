import { describe, expect, it } from 'vitest';
import { decodeOsc52ClipboardData } from '@core/features/terminals/browser/pty/pty-clipboard';
import {
  CTRL_J_ASCII,
  CTRL_U_ASCII,
  shouldCopySelectionFromTerminal,
  shouldHandleInterruptFromTerminal,
  shouldKillLineFromTerminal,
  shouldMapShiftEnterToCtrlJ,
  shouldPasteToTerminal,
  type KeyEventLike,
} from '@core/features/terminals/browser/pty/pty-keybindings';

describe('TerminalSessionManager - Shift+Enter to Ctrl+J mapping', () => {
  const makeEvent = (overrides: Partial<KeyEventLike> = {}): KeyEventLike => ({
    type: 'keydown',
    key: 'Enter',
    shiftKey: false,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    ...overrides,
  });

  it('maps Shift+Enter to Ctrl+J only', () => {
    expect(shouldMapShiftEnterToCtrlJ(makeEvent({ shiftKey: true }))).toBe(true);
    expect(shouldMapShiftEnterToCtrlJ(makeEvent({ shiftKey: false }))).toBe(false);
    expect(shouldMapShiftEnterToCtrlJ(makeEvent({ shiftKey: true, ctrlKey: true }))).toBe(false);
    expect(shouldMapShiftEnterToCtrlJ(makeEvent({ shiftKey: true, metaKey: true }))).toBe(false);
    expect(shouldMapShiftEnterToCtrlJ(makeEvent({ shiftKey: true, altKey: true }))).toBe(false);
    expect(shouldMapShiftEnterToCtrlJ(makeEvent({ key: 'a', shiftKey: true }))).toBe(false);
    expect(shouldMapShiftEnterToCtrlJ(makeEvent({ type: 'keyup', shiftKey: true }))).toBe(false);
  });

  it('uses line feed for Ctrl+J', () => {
    expect(CTRL_J_ASCII).toBe('\n');
  });

  it('detects copy shortcuts with selection', () => {
    const withSelection = true;
    const withoutSelection = false;

    // macOS: Cmd+C should copy selected text
    expect(
      shouldCopySelectionFromTerminal(makeEvent({ key: 'c', metaKey: true }), true, withSelection)
    ).toBe(true);

    // non-macOS: Ctrl+C should copy selected text
    expect(
      shouldCopySelectionFromTerminal(makeEvent({ key: 'c', ctrlKey: true }), false, withSelection)
    ).toBe(true);

    // all platforms: Ctrl+Shift+C should copy selected text
    expect(
      shouldCopySelectionFromTerminal(
        makeEvent({ key: 'c', ctrlKey: true, shiftKey: true }),
        true,
        withSelection
      )
    ).toBe(true);
    expect(
      shouldCopySelectionFromTerminal(
        makeEvent({ key: 'c', ctrlKey: true, shiftKey: true }),
        false,
        withSelection
      )
    ).toBe(true);

    // all platforms: Ctrl+Shift+C can use the recent selection fallback
    expect(
      shouldCopySelectionFromTerminal(
        makeEvent({ key: 'c', ctrlKey: true, shiftKey: true }),
        false,
        withoutSelection,
        true
      )
    ).toBe(true);

    // non-macOS: Ctrl+C requires a live selection so stale selections do not block SIGINT
    expect(
      shouldCopySelectionFromTerminal(
        makeEvent({ key: 'c', ctrlKey: true }),
        false,
        withoutSelection,
        true
      )
    ).toBe(false);

    // no selection should never copy
    expect(
      shouldCopySelectionFromTerminal(
        makeEvent({ key: 'c', metaKey: true }),
        true,
        withoutSelection
      )
    ).toBe(false);
    expect(
      shouldCopySelectionFromTerminal(
        makeEvent({ key: 'c', ctrlKey: true }),
        false,
        withoutSelection
      )
    ).toBe(false);

    // modifier mismatch should not copy
    expect(
      shouldCopySelectionFromTerminal(
        makeEvent({ key: 'c', metaKey: true, shiftKey: true }),
        true,
        withSelection
      )
    ).toBe(false);
    expect(
      shouldCopySelectionFromTerminal(
        makeEvent({ key: 'c', altKey: true, ctrlKey: true }),
        false,
        withSelection
      )
    ).toBe(false);
  });

  it('decodes OSC 52 clipboard payloads', () => {
    expect(decodeOsc52ClipboardData('c;aGVsbG8=')).toBe('hello');
    expect(decodeOsc52ClipboardData('pc;8J+agA==')).toBe('🚀');
    expect(decodeOsc52ClipboardData(';dGV4dA==')).toBe('text');

    expect(decodeOsc52ClipboardData('p;aGVsbG8=')).toBeNull();
    expect(decodeOsc52ClipboardData('c;?')).toBeNull();
    expect(decodeOsc52ClipboardData('c;not base64')).toBeNull();
    expect(decodeOsc52ClipboardData('missing-separator')).toBeNull();
  });

  it('detects paste shortcut per platform', () => {
    const isMac = true;
    const isNotMac = false;
    const isWin = true;
    const isNotWin = false;

    // Linux: Ctrl+Shift+V should trigger paste
    expect(
      shouldPasteToTerminal(
        makeEvent({ key: 'v', ctrlKey: true, shiftKey: true }),
        isNotMac,
        isNotWin
      )
    ).toBe(true);

    // Linux: Ctrl+V alone should NOT trigger
    expect(shouldPasteToTerminal(makeEvent({ key: 'v', ctrlKey: true }), isNotMac, isNotWin)).toBe(
      false
    );

    // Windows: Ctrl+V should trigger paste (native convention)
    expect(shouldPasteToTerminal(makeEvent({ key: 'v', ctrlKey: true }), isNotMac, isWin)).toBe(
      true
    );

    // Windows: Ctrl+Shift+V should also trigger paste
    expect(
      shouldPasteToTerminal(makeEvent({ key: 'v', ctrlKey: true, shiftKey: true }), isNotMac, isWin)
    ).toBe(true);

    // macOS: Ctrl+Shift+V should NOT trigger (macOS uses Cmd+V, handled natively)
    expect(
      shouldPasteToTerminal(makeEvent({ key: 'v', ctrlKey: true, shiftKey: true }), isMac, isNotWin)
    ).toBe(false);

    // macOS: Ctrl+V should NOT trigger
    expect(shouldPasteToTerminal(makeEvent({ key: 'v', ctrlKey: true }), isMac, isNotWin)).toBe(
      false
    );

    // Additional modifiers should NOT trigger on any platform
    expect(
      shouldPasteToTerminal(
        makeEvent({ key: 'v', ctrlKey: true, shiftKey: true, altKey: true }),
        isNotMac,
        isNotWin
      )
    ).toBe(false);
    expect(
      shouldPasteToTerminal(
        makeEvent({ key: 'v', ctrlKey: true, shiftKey: true, metaKey: true }),
        isNotMac,
        isWin
      )
    ).toBe(false);
    expect(
      shouldPasteToTerminal(makeEvent({ key: 'v', ctrlKey: true, altKey: true }), isNotMac, isWin)
    ).toBe(false);

    // Plain V without Ctrl should NOT trigger
    expect(shouldPasteToTerminal(makeEvent({ key: 'v' }), isNotMac, isWin)).toBe(false);

    // Wrong key should NOT trigger
    expect(
      shouldPasteToTerminal(
        makeEvent({ key: 'c', ctrlKey: true, shiftKey: true }),
        isNotMac,
        isNotWin
      )
    ).toBe(false);

    // keyup should NOT trigger
    expect(
      shouldPasteToTerminal(
        makeEvent({ type: 'keyup', key: 'v', ctrlKey: true, shiftKey: true }),
        isNotMac,
        isNotWin
      )
    ).toBe(false);
    expect(
      shouldPasteToTerminal(makeEvent({ type: 'keyup', key: 'v', ctrlKey: true }), isNotMac, isWin)
    ).toBe(false);
  });

  it('uses Ctrl+U for kill-line', () => {
    expect(CTRL_U_ASCII).toBe('\x15');
  });

  it('detects Cmd+Backspace on macOS only', () => {
    const isMac = true;
    const isNotMac = false;

    // Cmd+Backspace on macOS should trigger
    expect(shouldKillLineFromTerminal(makeEvent({ key: 'Backspace', metaKey: true }), isMac)).toBe(
      true
    );

    // Cmd+Backspace on Linux/Windows should NOT trigger
    expect(
      shouldKillLineFromTerminal(makeEvent({ key: 'Backspace', metaKey: true }), isNotMac)
    ).toBe(false);

    // Ctrl+Backspace should NOT trigger on any platform
    expect(shouldKillLineFromTerminal(makeEvent({ key: 'Backspace', ctrlKey: true }), isMac)).toBe(
      false
    );
    expect(
      shouldKillLineFromTerminal(makeEvent({ key: 'Backspace', ctrlKey: true }), isNotMac)
    ).toBe(false);

    // Additional modifiers should NOT trigger
    expect(
      shouldKillLineFromTerminal(
        makeEvent({ key: 'Backspace', metaKey: true, shiftKey: true }),
        isMac
      )
    ).toBe(false);
    expect(
      shouldKillLineFromTerminal(
        makeEvent({ key: 'Backspace', metaKey: true, altKey: true }),
        isMac
      )
    ).toBe(false);

    // Wrong key should NOT trigger
    expect(shouldKillLineFromTerminal(makeEvent({ key: 'Delete', metaKey: true }), isMac)).toBe(
      false
    );

    // keyup should NOT trigger
    expect(
      shouldKillLineFromTerminal(
        makeEvent({ type: 'keyup', key: 'Backspace', metaKey: true }),
        isMac
      )
    ).toBe(false);
  });

  it('detects plain Escape as interrupt intent', () => {
    expect(shouldHandleInterruptFromTerminal(makeEvent({ key: 'Escape' }))).toBe(true);
    expect(shouldHandleInterruptFromTerminal(makeEvent({ key: 'Escape', ctrlKey: true }))).toBe(
      false
    );
    expect(shouldHandleInterruptFromTerminal(makeEvent({ key: 'Escape', metaKey: true }))).toBe(
      false
    );
    expect(shouldHandleInterruptFromTerminal(makeEvent({ key: 'Escape', altKey: true }))).toBe(
      false
    );
    expect(shouldHandleInterruptFromTerminal(makeEvent({ type: 'keyup', key: 'Escape' }))).toBe(
      false
    );
  });
});
