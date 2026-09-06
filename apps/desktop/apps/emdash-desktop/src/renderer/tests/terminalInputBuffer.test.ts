import { describe, expect, it, vi } from 'vitest';
import {
  isRealTaskInput,
  SubmittedInputBuffer,
  TerminalInputBuffer,
} from '@core/features/terminals/browser/pty/pty-input-buffer';

describe('TerminalInputBuffer', () => {
  it('captures a message after Enter + confirmSubmit', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('Fix the login page');
    buffer.feed('\r');
    buffer.confirmSubmit();

    expect(onCapture).toHaveBeenCalledWith('Fix the login page');
    expect(buffer.isComplete).toBe(true);
  });

  it('fires callback only once', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('First message here\r');
    buffer.confirmSubmit();

    buffer.feed('Second message here\r');
    buffer.confirmSubmit();

    expect(onCapture).toHaveBeenCalledTimes(1);
    expect(onCapture).toHaveBeenCalledWith('First message here');
  });

  it('handles backspace correctly', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('Hell');
    buffer.feed('\x7f');
    buffer.feed('lo world');
    buffer.feed('\r');
    buffer.confirmSubmit();

    expect(onCapture).toHaveBeenCalledWith('Hello world');
  });

  it('strips ANSI escape codes', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('\x1b[32mFix the broken auth\x1b[0m');
    buffer.feed('\r');
    buffer.confirmSubmit();

    expect(onCapture).toHaveBeenCalledWith('Fix the broken auth');
  });

  it('strips split OSC/CSI control sequences before classifying input', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('\x1b]10;rgb:1f1f/2929/3737');
    buffer.feed('\x1b\\\x1b]11;rgb:fcfc/fcfc/fcfc\x1b\\');
    buffer.feed('\x1b[1;1Hhello world');
    buffer.feed('\r');
    buffer.confirmSubmit();

    expect(onCapture).toHaveBeenCalledWith('hello world');
  });

  it('strips repeated focus/noise escapes before classifying input', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('\x1b[O\x1b[I\x1b[O\x1b[Ifix auth flow');
    buffer.feed('\r');
    buffer.confirmSubmit();

    expect(onCapture).toHaveBeenCalledWith('fix auth flow');
  });

  it('applies kitty CSI-u backspace keys to the buffered line', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('/model');
    for (let i = 0; i < 6; i++) {
      buffer.feed('\x1b[127;1u');
    }
    buffer.feed('hello\r');
    buffer.confirmSubmit();

    expect(onCapture).toHaveBeenCalledWith('hello');
  });

  it('skips slash commands', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('/help\r');
    buffer.confirmSubmit();

    expect(onCapture).not.toHaveBeenCalled();
    expect(buffer.isComplete).toBe(false);
  });

  it('skips single-character confirmations', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('y\r');
    buffer.confirmSubmit();
    expect(onCapture).not.toHaveBeenCalled();

    buffer.feed('ok\r');
    buffer.confirmSubmit();
    expect(onCapture).not.toHaveBeenCalled();
  });

  it('skips very short messages', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('x\r');
    buffer.confirmSubmit();

    expect(onCapture).not.toHaveBeenCalled();
    expect(buffer.isComplete).toBe(false);
  });

  it('accepts concise natural-language prompts', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('fix bug\r');
    buffer.confirmSubmit();

    expect(onCapture).toHaveBeenCalledWith('fix bug');
    expect(buffer.isComplete).toBe(true);
  });

  it('captures after skipping invalid input', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('y\r');
    buffer.confirmSubmit();
    expect(onCapture).not.toHaveBeenCalled();

    buffer.feed('Implement the authentication flow for OAuth\r');
    buffer.confirmSubmit();
    expect(onCapture).toHaveBeenCalledWith('Implement the authentication flow for OAuth');
  });

  it('does not fire without confirmSubmit', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('Fix the login page\r');
    expect(onCapture).not.toHaveBeenCalled();
  });

  it('ignores feed after completion', () => {
    const onCapture = vi.fn();
    const buffer = new TerminalInputBuffer(onCapture);

    buffer.feed('First message here\r');
    buffer.confirmSubmit();
    expect(buffer.isComplete).toBe(true);

    buffer.feed('Another message\r');
    expect(onCapture).toHaveBeenCalledTimes(1);
  });

  it('requires at least one alphabetic character', () => {
    expect(isRealTaskInput('1234')).toBe(false);
    expect(isRealTaskInput('---')).toBe(false);
    expect(isRealTaskInput('fix')).toBe(true);
  });

  it('clearLine removes prefilled slash command before subsequent submit', () => {
    const buffer = new SubmittedInputBuffer();

    buffer.feed('/model');
    buffer.clearLine();
    const submitted = buffer.feed('hello\r');

    expect(submitted).toEqual(['hello']);
  });

  it('tracks left-arrow insertion at cursor position', () => {
    const buffer = new SubmittedInputBuffer();

    const submitted = buffer.feed('hello\x1b[DX\r');

    expect(submitted).toEqual(['hellXo']);
  });

  it('tracks Ctrl+U line clear before new text', () => {
    const buffer = new SubmittedInputBuffer();

    const submitted = buffer.feed('hello\x15world\r');

    expect(submitted).toEqual(['world']);
  });

  it('tracks CSI-u encoded Ctrl+U line clear before new text', () => {
    const buffer = new SubmittedInputBuffer();

    const submitted = buffer.feed('hello\x1b[21;1uworld\r');

    expect(submitted).toEqual(['world']);
  });

  it('bounds very long CSI payloads and continues parsing input', () => {
    const buffer = new SubmittedInputBuffer();

    buffer.feed('hello');
    buffer.feed(`\x1b[${'9'.repeat(1024)}D`);
    const submitted = buffer.feed('X\r');

    expect(submitted).toEqual(['Xhello']);
  });

  it('does not discard a typed line when Escape is pressed before Enter', () => {
    const buffer = new SubmittedInputBuffer();

    buffer.feed('hello');
    buffer.feed('\x1b');
    const submitted = buffer.feed('\r');

    expect(submitted).toEqual(['hello']);
  });
});
