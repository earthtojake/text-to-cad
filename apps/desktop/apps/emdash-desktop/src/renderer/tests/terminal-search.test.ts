import { describe, expect, it } from 'vitest';
import {
  collectTerminalSearchMatches,
  getNextTerminalSearchIndex,
  type TerminalSearchBufferLike,
  type TerminalSearchBufferLineLike,
  type TerminalSearchMatch,
} from '@core/features/terminals/browser/pty/terminal-search';

class MockBufferLine implements TerminalSearchBufferLineLike {
  constructor(
    private readonly text: string,
    readonly isWrapped: boolean = false
  ) {}

  translateToString(): string {
    return this.text;
  }
}

function makeBuffer(lines: Array<{ text: string; isWrapped?: boolean }>): TerminalSearchBufferLike {
  const bufferLines = lines.map((line) => new MockBufferLine(line.text, line.isWrapped ?? false));
  return {
    length: bufferLines.length,
    getLine: (index: number) => bufferLines[index],
  };
}

describe('terminal-search', () => {
  it('finds case-insensitive matches on buffer rows', () => {
    const buffer = makeBuffer([{ text: 'Alpha beta' }, { text: 'beta gamma' }]);

    expect(collectTerminalSearchMatches(buffer, 'BETA')).toEqual<TerminalSearchMatch[]>([
      { row: 0, col: 6, length: 4 },
      { row: 1, col: 0, length: 4 },
    ]);
  });

  it('maps wrapped-line matches back to the physical row and column', () => {
    const buffer = makeBuffer([
      { text: 'Hello ', isWrapped: false },
      { text: 'world', isWrapped: true },
      { text: 'separate line', isWrapped: false },
    ]);

    expect(collectTerminalSearchMatches(buffer, 'world')).toEqual<TerminalSearchMatch[]>([
      { row: 1, col: 0, length: 5 },
    ]);
  });

  it('cycles forward and backward through matches', () => {
    const matches: TerminalSearchMatch[] = [
      { row: 0, col: 1, length: 3 },
      { row: 3, col: 2, length: 3 },
      { row: 7, col: 0, length: 3 },
    ];

    expect(getNextTerminalSearchIndex(matches, null, 'next')).toBe(0);
    expect(getNextTerminalSearchIndex(matches, null, 'prev')).toBe(2);
    expect(getNextTerminalSearchIndex(matches, matches[0], 'next')).toBe(1);
    expect(getNextTerminalSearchIndex(matches, matches[0], 'prev')).toBe(2);
    expect(getNextTerminalSearchIndex(matches, matches[2], 'next')).toBe(0);
  });
});
