/**
 * layout.test.ts — unit tests for prose layout variant handling.
 *
 * Validates that heading variants use the correct heading font and line-height
 * rather than the body font, which was the root cause of the heading-overlap
 * bug (measured height too small → content overflowed into the next row).
 *
 * Two complementary layers:
 *  1. `runsToRichItems` unit tests — verify heading font selection without a
 *     canvas/pretext dependency.
 *  2. `layoutProse` structural tests using empty-run blocks — verify that
 *     `lineHeightForVariant` correctly selects the heading line height. Empty
 *     blocks skip the pretext measurement path (no canvas needed).
 */

import { DEFAULT_CONFIG, toFontConfig } from '@core/config';
import type { InlineRun, ProseBlock } from '@core/markdown/document';
import { runsToRichItems } from '@core/measure/to-rich-items';
import { describe, expect, it } from 'vitest';
import { layoutProse } from './layout';

const fonts = toFontConfig(DEFAULT_CONFIG);

// ── runsToRichItems: heading font selection ───────────────────────────────────
//
// This is the core fix: headings must measure with the heading font so that
// line-wrap predictions match the rendered output.

describe('runsToRichItems: heading variant selects heading font', () => {
  const plainRun: InlineRun = { kind: 'text', text: 'PHASE 1: CRITICAL CONCURRENCY FIXES' };
  const boldRun: InlineRun = { kind: 'text', text: 'PHASE 1', bold: true };

  it('h1: all runs use fonts.h1.font', () => {
    const items = runsToRichItems([plainRun], fonts, 'h1');
    expect(items).toHaveLength(1);
    expect(items[0].font).toBe(fonts.h1.font);
  });

  it('h2: plain run uses fonts.h2.font (not body)', () => {
    const items = runsToRichItems([plainRun], fonts, 'h2');
    expect(items[0].font).toBe(fonts.h2.font);
    expect(items[0].font).not.toBe(fonts.body.font);
  });

  it('h2: bold run uses fonts.h2.font (not bold)', () => {
    const items = runsToRichItems([boldRun], fonts, 'h2');
    expect(items[0].font).toBe(fonts.h2.font);
    expect(items[0].font).not.toBe(fonts.bold.font);
  });

  it('h3: uses fonts.h3.font', () => {
    const items = runsToRichItems([plainRun], fonts, 'h3');
    expect(items[0].font).toBe(fonts.h3.font);
  });

  it('h4/h5/h6: use fonts.h3.font (same as h3)', () => {
    for (const v of ['h4', 'h5', 'h6'] as const) {
      const items = runsToRichItems([plainRun], fonts, v);
      expect(items[0].font).toBe(fonts.h3.font);
    }
  });

  it('body: plain run uses fonts.body.font', () => {
    const items = runsToRichItems([plainRun], fonts, 'body');
    expect(items[0].font).toBe(fonts.body.font);
  });

  it('body: bold run uses fonts.bold.font (not heading)', () => {
    const items = runsToRichItems([boldRun], fonts, 'body');
    expect(items[0].font).toBe(fonts.bold.font);
  });

  it('h2: inline-code run uses fonts.h2.font (no chip extra width)', () => {
    const codeRun: InlineRun = { kind: 'code', text: 'const x' };
    const items = runsToRichItems([codeRun], fonts, 'h2');
    expect(items[0].font).toBe(fonts.h2.font);
    // No chip extra width in heading context.
    expect(items[0].extraWidth).toBeUndefined();
  });

  it('h2: heading fonts differ from body fonts (guard for meaningful tests)', () => {
    expect(fonts.h2.font).not.toBe(fonts.body.font);
    expect(fonts.h2.lineHeight).toBeGreaterThan(fonts.body.lineHeight);
  });
});

// ── layoutProse: lineHeight selection (empty-run fast-path, no canvas) ────────
//
// Empty blocks (`runs: []`) return immediately before the pretext canvas path.
// They still compute and return `lineHeight` via `lineHeightForVariant`, so we
// can assert the correct heading line-height is selected without a real canvas.

describe('layoutProse: empty block returns correct lineHeight for variant', () => {
  function emptyBlock(variant: ProseBlock['variant']): ProseBlock {
    return { kind: 'prose', id: 'b-empty', variant, runs: [] };
  }

  it('body → body lineHeight', () => {
    expect(layoutProse(emptyBlock('body'), 400, fonts, 0).lineHeight).toBe(fonts.body.lineHeight);
  });

  it('h1 → h1 lineHeight', () => {
    expect(layoutProse(emptyBlock('h1'), 400, fonts, 0).lineHeight).toBe(fonts.h1.lineHeight);
  });

  it('h2 → h2 lineHeight', () => {
    expect(layoutProse(emptyBlock('h2'), 400, fonts, 0).lineHeight).toBe(fonts.h2.lineHeight);
  });

  it('h3 → h3 lineHeight', () => {
    expect(layoutProse(emptyBlock('h3'), 400, fonts, 0).lineHeight).toBe(fonts.h3.lineHeight);
  });

  it('h4/h5/h6 → h3 lineHeight', () => {
    for (const v of ['h4', 'h5', 'h6'] as const) {
      expect(layoutProse(emptyBlock(v), 400, fonts, 0).lineHeight).toBe(fonts.h3.lineHeight);
    }
  });

  it('h2 lineHeight is strictly larger than body lineHeight', () => {
    // Regression guard: if they were equal, height mismatches would be invisible.
    expect(fonts.h2.lineHeight).toBeGreaterThan(fonts.body.lineHeight);
  });

  it('empty block height is 0 regardless of variant', () => {
    expect(layoutProse(emptyBlock('h2'), 400, fonts, 0).height).toBe(0);
    expect(layoutProse(emptyBlock('body'), 400, fonts, 0).height).toBe(0);
  });
});
