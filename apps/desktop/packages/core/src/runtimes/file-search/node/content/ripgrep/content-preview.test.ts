import { describe, expect, it } from 'vitest';
import { createContentSearchPreview, type ContentSearchPreview } from './content-preview';

describe('createContentSearchPreview', () => {
  it('keeps short lines and source coordinates unchanged', () => {
    const preview = createContentSearchPreview('before needle after', [range(8, 14)]);

    expect(preview).toEqual({
      previewText: 'before needle after',
      locations: [
        {
          sourceRange: range(8, 14),
          previewRange: range(8, 14),
        },
      ],
      locationsOmitted: false,
    });
  });

  it('uses roughly one fifth of the context before a middle match', () => {
    const text = `${'a'.repeat(400)}needle${'b'.repeat(800)}`;
    const preview = createContentSearchPreview(text, [range(401, 407)], {
      charsPerMatch: 100,
      maxLength: 200,
    });

    expect(preview.previewText).toBe(
      `⟪ 382 characters skipped ⟫${'a'.repeat(18)}needle${'b'.repeat(76)}` +
        '⟪ 724 characters skipped ⟫'
    );
    expect(preview.locations).toEqual([
      {
        sourceRange: range(401, 407),
        previewRange: range(45, 51),
      },
    ]);
    expect(preview.locationsOmitted).toBe(false);
  });

  it('redistributes unavailable leading or trailing context', () => {
    const leading = createContentSearchPreview(`needle${'x'.repeat(100)}`, [range(1, 7)], {
      charsPerMatch: 30,
      maxLength: 100,
    });
    const trailing = createContentSearchPreview(`${'x'.repeat(100)}needle`, [range(101, 107)], {
      charsPerMatch: 30,
      maxLength: 100,
    });

    expect(leading.previewText).toBe(`needle${'x'.repeat(24)}⟪ 76 characters skipped ⟫`);
    expect(trailing.previewText).toBe(`⟪ 76 characters skipped ⟫${'x'.repeat(24)}needle`);
    assertLocationsSelectSourceText(`needle${'x'.repeat(100)}`, leading);
    assertLocationsSelectSourceText(`${'x'.repeat(100)}needle`, trailing);
  });

  it('merges nearby match windows instead of inserting a longer elision', () => {
    const text = `needle${'x'.repeat(8)}needle`;
    const preview = createContentSearchPreview(text, [range(1, 7), range(15, 21)], {
      charsPerMatch: 6,
      maxLength: 100,
    });

    expect(preview.previewText).toBe(text);
    expect(preview.locations.map(({ previewRange }) => previewRange)).toEqual([
      range(1, 7),
      range(15, 21),
    ]);
  });

  it('uses counted elisions between distant windows and maps each range', () => {
    const text = `needle${'x'.repeat(100)}needle`;
    const preview = createContentSearchPreview(text, [range(1, 7), range(107, 113)], {
      charsPerMatch: 6,
      maxLength: 100,
    });

    expect(preview.previewText).toBe('needle⟪ 100 characters skipped ⟫needle');
    expect(preview.locations).toEqual([
      { sourceRange: range(1, 7), previewRange: range(1, 7) },
      { sourceRange: range(107, 113), previewRange: range(33, 39) },
    ]);
    assertLocationsSelectSourceText(text, preview);
  });

  it('compacts a very long ripgrep line instead of treating it as malformed output', () => {
    const text = `${'a'.repeat(210_000)}lol${'b'.repeat(210_000)}`;
    const preview = createContentSearchPreview(text, [range(210_001, 210_004)]);

    expect(preview.previewText.length).toBeLessThanOrEqual(16_384);
    expect(preview.previewText.length).toBeLessThan(1_100);
    expect(preview.locationsOmitted).toBe(false);
    assertLocationsSelectSourceText(text, preview);
  });

  it('preserves overlapping locations independently', () => {
    const text = 'overlapping';
    const preview = createContentSearchPreview(text, [range(1, 8), range(5, 12)]);

    expect(preview.previewText).toBe(text);
    expect(preview.locations).toEqual([
      { sourceRange: range(1, 8), previewRange: range(1, 8) },
      { sourceRange: range(5, 12), previewRange: range(5, 12) },
    ]);
  });

  it('reserves the hard budget for complete locations before adding context', () => {
    const text = Array.from({ length: 12 }, (_, index) => `match${index}`).join('-'.repeat(40));
    const ranges = [...text.matchAll(/match\d+/gu)].map((match) =>
      range(match.index + 1, match.index + match[0].length + 1)
    );
    const preview = createContentSearchPreview(text, ranges, {
      charsPerMatch: 100,
      maxLength: 160,
    });

    expect(preview.previewText.length).toBeLessThanOrEqual(160);
    expect(preview.locations.length).toBeGreaterThan(0);
    expect(preview.locations.length).toBeLessThan(ranges.length);
    expect(preview.locations.map(({ sourceRange }) => sourceRange)).toEqual(
      ranges.slice(0, preview.locations.length)
    );
    expect(preview.locationsOmitted).toBe(true);
    assertLocationsSelectSourceText(text, preview);
  });

  it('retains every location when their match-only representation fits the hard bound', () => {
    const text = `one${'x'.repeat(100)}two${'y'.repeat(100)}three`;
    const ranges = [range(1, 4), range(104, 107), range(207, 212)];
    const preview = createContentSearchPreview(text, ranges, {
      charsPerMatch: 1_000,
      maxLength: 90,
    });

    expect(preview.previewText.length).toBeLessThanOrEqual(90);
    expect(preview.locations).toHaveLength(3);
    expect(preview.locationsOmitted).toBe(false);
    assertLocationsSelectSourceText(text, preview);
  });

  it('does not split UTF-16 surrogate pairs at preview boundaries', () => {
    const text = `${'😀'.repeat(30)}needle${'🚀'.repeat(30)}`;
    const preview = createContentSearchPreview(text, [range(61, 67)], {
      charsPerMatch: 21,
      maxLength: 80,
      leadingContextRatio: 0.5,
    });

    expect(hasUnpairedSurrogate(preview.previewText)).toBe(false);
    expect(preview.previewText.length).toBeLessThanOrEqual(80);
    assertLocationsSelectSourceText(text, preview);
  });

  it('rejects source ranges that split UTF-16 surrogate pairs', () => {
    expect(() => createContentSearchPreview('😀needle', [range(2, 4)])).toThrow(
      'cannot split UTF-16 surrogate pairs'
    );
  });

  it('sorts unsorted locations deterministically', () => {
    const text = `first${'x'.repeat(100)}second`;
    const ranges = [range(106, 112), range(1, 6)];
    const first = createContentSearchPreview(text, ranges, {
      charsPerMatch: 5,
      maxLength: 100,
    });
    const second = createContentSearchPreview(text, ranges, {
      charsPerMatch: 5,
      maxLength: 100,
    });

    expect(second).toEqual(first);
    expect(first.locations.map(({ sourceRange }) => sourceRange)).toEqual([
      range(1, 6),
      range(106, 112),
    ]);
  });

  it('maintains hard-bound and coordinate invariants across varied inputs', () => {
    for (let matchCount = 1; matchCount <= 30; matchCount += 1) {
      const pieces = Array.from({ length: matchCount }, (_, index) =>
        index % 2 === 0 ? `😀-${index}-hit` : `ascii-${index}-hit`
      );
      const text = pieces.join('z'.repeat((matchCount % 7) * 13 + 1));
      const ranges = [...text.matchAll(/hit/gu)].map((match) =>
        range(match.index + 1, match.index + match[0].length + 1)
      );

      for (const maxLength of [40, 80, 160, 320]) {
        const preview = createContentSearchPreview(text, ranges, {
          charsPerMatch: 37,
          maxLength,
        });

        expect(preview.previewText.length).toBeLessThanOrEqual(maxLength);
        expect(hasUnpairedSurrogate(preview.previewText)).toBe(false);
        assertLocationsSelectSourceText(text, preview);
      }
    }
  });
});

function range(startColumn: number, endColumn: number) {
  return { startColumn, endColumn };
}

function assertLocationsSelectSourceText(text: string, preview: ContentSearchPreview): void {
  for (const location of preview.locations) {
    const source = text.slice(
      location.sourceRange.startColumn - 1,
      location.sourceRange.endColumn - 1
    );
    const rendered = preview.previewText.slice(
      location.previewRange.startColumn - 1,
      location.previewRange.endColumn - 1
    );
    expect(rendered).toBe(source);
  }
}

function hasUnpairedSurrogate(text: string): boolean {
  for (let index = 0; index < text.length; index += 1) {
    const codeUnit = text.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = text.charCodeAt(index + 1);
      if (next < 0xdc00 || next > 0xdfff) return true;
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      return true;
    }
  }
  return false;
}
