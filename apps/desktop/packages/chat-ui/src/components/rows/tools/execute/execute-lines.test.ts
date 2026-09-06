import { describe, expect, it, vi } from 'vitest';
import type { ChatExecute } from '@/model';
import { executeLines, maxOutputLineWidth } from './execute-lines';

function item(overrides: Partial<ChatExecute> = {}): ChatExecute {
  return {
    kind: 'execute',
    id: 'x',
    command: 'echo ok',
    status: 'done',
    startedAt: 0,
    ...overrides,
  };
}

describe('executeLines', () => {
  it('prefixes command lines and appends output after a spacer', () => {
    const lines = executeLines(item({ command: 'a\nb', outputLines: ['out1', 'out2'] }));
    expect(lines).toEqual([
      { kind: 'command', text: '$ a' },
      { kind: 'command', text: '  b' },
      { kind: 'spacer', text: '' },
      { kind: 'output', text: 'out1' },
      { kind: 'output', text: 'out2' },
    ]);
  });

  it('shows a single truncation indicator line before the output when flagged', () => {
    const lines = executeLines(item({ outputLines: ['tail'], outputTruncated: true }));
    expect(lines.map((line) => line.kind)).toEqual(['command', 'spacer', 'truncated', 'output']);
  });

  it('returns identical display objects for unchanged lines across live updates', () => {
    const live: string[] = ['one', 'two'];
    const first = executeLines(item({ outputLines: live, outputVersion: 1 }));
    live.push('three');
    const second = executeLines(item({ outputLines: live, outputVersion: 2 }));
    // Command, spacer, and pre-existing output rows keep identity; only the new row is fresh.
    expect(second.slice(0, first.length)).toEqual(first);
    for (let i = 0; i < first.length; i += 1) {
      expect(second[i]).toBe(first[i]);
    }
    expect(second).toHaveLength(first.length + 1);
  });
});

describe('maxOutputLineWidth', () => {
  it('measures each committed line once across repeated calls (running max)', () => {
    const measure = vi.fn((text: string) => text.length);
    const lines: string[] = ['aaaa', 'bb'];

    expect(maxOutputLineWidth(lines, 'font', measure)).toBe(4);
    // 'aaaa' committed; 'bb' (last, still growing) measured but not committed.
    expect(measure).toHaveBeenCalledTimes(2);

    measure.mockClear();
    lines.push('cccccc');
    expect(maxOutputLineWidth(lines, 'font', measure)).toBe(6);
    // Only 'bb' (newly committed) and 'cccccc' (new tail) are measured.
    expect(measure).toHaveBeenCalledTimes(2);

    measure.mockClear();
    expect(maxOutputLineWidth(lines, 'font', measure)).toBe(6);
    // Steady state: only the tail line is re-measured.
    expect(measure).toHaveBeenCalledTimes(1);
  });

  it('keeps the running max when old lines are evicted from the front', () => {
    const measure = (text: string) => text.length;
    const lines: string[] = ['wide-line-that-is-long', 'short'];
    expect(maxOutputLineWidth(lines, 'font', measure)).toBe(22);
    lines.shift();
    expect(maxOutputLineWidth(lines, 'font', measure)).toBe(22);
  });

  it('re-measures from scratch when the font key changes', () => {
    const measure = vi.fn((text: string) => text.length);
    const lines = ['abc', 'de'];
    maxOutputLineWidth(lines, 'font-a', measure);
    measure.mockClear();
    maxOutputLineWidth(lines, 'font-b', measure);
    expect(measure).toHaveBeenCalledTimes(2);
  });
});
