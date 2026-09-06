import { describe, expect, it } from 'vitest';
import { highlightSegments } from './highlight';

describe('highlightSegments', () => {
  it('converts one-based preview ranges into highlighted text segments', () => {
    expect(
      highlightSegments('test and test', [
        { startColumn: 1, endColumn: 5 },
        { startColumn: 10, endColumn: 14 },
      ])
    ).toEqual([
      { text: 'test', highlighted: true },
      { text: ' and ', highlighted: false },
      { text: 'test', highlighted: true },
    ]);
  });

  it('merges overlapping and adjacent ranges', () => {
    expect(
      highlightSegments('abcdefghij', [
        { startColumn: 2, endColumn: 5 },
        { startColumn: 4, endColumn: 7 },
        { startColumn: 7, endColumn: 9 },
      ])
    ).toEqual([
      { text: 'a', highlighted: false },
      { text: 'bcdefgh', highlighted: true },
      { text: 'ij', highlighted: false },
    ]);
  });

  it('clamps ranges to the text length', () => {
    expect(
      highlightSegments('abc', [
        { startColumn: 0, endColumn: 2 },
        { startColumn: 3, endColumn: 99 },
      ])
    ).toEqual([
      { text: 'a', highlighted: true },
      { text: 'b', highlighted: false },
      { text: 'c', highlighted: true },
    ]);
  });

  it('returns plain text for empty or invalid ranges', () => {
    expect(highlightSegments('abc', [])).toEqual([{ text: 'abc', highlighted: false }]);
    expect(highlightSegments('abc', [{ startColumn: 2, endColumn: 2 }])).toEqual([
      { text: 'abc', highlighted: false },
    ]);
  });
});
