import { describe, expect, it } from 'vitest';
import { formatCommandOutputTail } from './format-command-output-tail';

describe('formatCommandOutputTail', () => {
  it('returns the last non-empty lines', () => {
    expect(
      formatCommandOutputTail(
        ['Reading package lists... Done', '', 'E: Permission denied', 'E: Unable to lock'].join(
          '\n'
        )
      )
    ).toBe('Reading package lists... Done\nE: Permission denied\nE: Unable to lock');
  });

  it('returns an empty string for blank output', () => {
    expect(formatCommandOutputTail('   \n\n')).toBe('');
  });

  it('truncates long tails by character budget', () => {
    const line = 'x'.repeat(400);
    const tail = formatCommandOutputTail(line, { maxLines: 1, maxChars: 20 });
    expect(tail.startsWith('…')).toBe(true);
    expect(tail.length).toBe(20);
  });
});
