import { describe, expect, it } from 'vitest';
import { parseRipgrepJsonLine } from './ripgrep-json';

describe('parseRipgrepJsonLine', () => {
  it('converts ripgrep byte offsets into one-based UTF-16 editor columns', () => {
    const prefix = 'const 😀 ';
    const text = `${prefix}VALUE VALUE\r\n`;
    const firstStart = Buffer.byteLength(prefix);
    const secondStart = firstStart + Buffer.byteLength('VALUE ');

    expect(
      parseRipgrepJsonLine(
        JSON.stringify({
          type: 'match',
          data: {
            path: { text: './src/index.ts' },
            lines: { text },
            line_number: 7,
            submatches: [
              { start: firstStart, end: firstStart + 5, match: { text: 'VALUE' } },
              { start: secondStart, end: secondStart + 5, match: { text: 'VALUE' } },
            ],
          },
        })
      )
    ).toEqual({
      path: './src/index.ts',
      lineNumber: 7,
      previewText: 'const 😀 VALUE VALUE',
      locations: [
        {
          sourceRange: { startColumn: 10, endColumn: 15 },
          previewRange: { startColumn: 10, endColumn: 15 },
        },
        {
          sourceRange: { startColumn: 16, endColumn: 21 },
          previewRange: { startColumn: 16, endColumn: 21 },
        },
      ],
      locationsOmitted: false,
    });
  });

  it('supports ripgrep base64 byte payloads and ignores non-match events', () => {
    expect(parseRipgrepJsonLine(JSON.stringify({ type: 'begin', data: {} }))).toBeNull();
    expect(
      parseRipgrepJsonLine(
        JSON.stringify({
          type: 'match',
          data: {
            path: { bytes: Buffer.from('./file.txt').toString('base64') },
            lines: { bytes: Buffer.from('term\n').toString('base64') },
            line_number: 1,
            submatches: [{ start: 0, end: 4, match: { text: 'term' } }],
          },
        })
      )
    ).toMatchObject({ path: './file.txt', previewText: 'term' });
  });

  it('rejects malformed match records instead of emitting invalid contract data', () => {
    expect(() =>
      parseRipgrepJsonLine(
        JSON.stringify({
          type: 'match',
          data: {
            path: { text: './file.txt' },
            lines: { text: 'term\n' },
            line_number: 1,
            submatches: [{ start: 4, end: 2 }],
          },
        })
      )
    ).toThrow('submatch byte offsets');
  });

  it('limits occurrences before building the preview and reports omitted locations', () => {
    const parsed = parseRipgrepJsonLine(
      JSON.stringify({
        type: 'match',
        data: {
          path: { text: './file.txt' },
          lines: { text: 'term term term\n' },
          line_number: 1,
          submatches: [
            { start: 0, end: 4, match: { text: 'term' } },
            { start: 5, end: 9, match: { text: 'term' } },
            { start: 10, end: 14, match: { text: 'term' } },
          ],
        },
      }),
      { maxLocations: 2 }
    );

    expect(parsed?.locations).toHaveLength(2);
    expect(parsed?.locationsOmitted).toBe(true);
  });

  it('bounds and converts a dense line with many more matches than requested', () => {
    const occurrenceCount = 20_000;
    const text = `${'x '.repeat(occurrenceCount)}\n`;
    const submatches = Array.from({ length: occurrenceCount }, (_, index) => ({
      start: index * 2,
      end: index * 2 + 1,
      match: { text: 'x' },
    }));

    const parsed = parseRipgrepJsonLine(
      JSON.stringify({
        type: 'match',
        data: {
          path: { text: './dense.txt' },
          lines: { text },
          line_number: 1,
          submatches,
        },
      }),
      { maxLocations: 1_000 }
    );

    expect(parsed?.locations).toHaveLength(1_000);
    expect(parsed?.locations[0].sourceRange).toEqual({ startColumn: 1, endColumn: 2 });
    expect(parsed?.locations.at(-1)?.sourceRange).toEqual({
      startColumn: 1_999,
      endColumn: 2_000,
    });
    expect(parsed?.locationsOmitted).toBe(true);
  });
});
