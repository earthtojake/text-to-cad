import { describe, expect, it } from 'vitest';
import { generatedImageGridMetrics } from './generated-image-layout';

const vars = { gap: 8, maxTileSize: 280, minTwoColumnWidth: 360 };

describe('generatedImageGridMetrics', () => {
  it('reserves no space without attachments', () => {
    expect(generatedImageGridMetrics(0, 500, vars)).toEqual({
      columns: 0,
      rows: 0,
      tileSize: 0,
      height: 0,
    });
  });

  it('shows one uncropped card at a stable maximum size', () => {
    expect(generatedImageGridMetrics(1, 500, vars)).toEqual({
      columns: 1,
      rows: 1,
      tileSize: 280,
      height: 280,
    });
  });

  it('lays out several images without exceeding the measured height', () => {
    expect(generatedImageGridMetrics(3, 500, vars)).toEqual({
      columns: 2,
      rows: 2,
      tileSize: 246,
      height: 500,
    });
  });

  it('falls back to one column in a narrow chat panel', () => {
    expect(generatedImageGridMetrics(2, 300, vars)).toEqual({
      columns: 1,
      rows: 2,
      tileSize: 280,
      height: 568,
    });
  });
});
