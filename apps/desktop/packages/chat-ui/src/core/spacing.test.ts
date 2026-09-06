/**
 * spacing.ts — unit tests.
 *
 * Covers:
 *   1. collapse(): max-semantics, tie-breaking, zeros.
 *   2. resolveSeamGap(): uses declared margins, defaults to 0 for unknown kinds.
 *   3. Block-layer seam values: verifies that margin-collapse reproduces
 *      the expected gap values. These are tested here (not in block-stack.test.ts)
 *      because layoutBlockStack transitively imports BLOCK_REGISTRY components
 *      and cannot run in the node test project.
 */

import { describe, expect, it } from 'vitest';
import { collapse, resolveSeamGap } from './spacing';
import type { Margin } from './spacing';

describe('collapse', () => {
  it('returns the larger of the two values', () => {
    expect(collapse(10, 4)).toBe(10);
    expect(collapse(4, 10)).toBe(10);
  });

  it('returns the value when both are equal (tie)', () => {
    expect(collapse(6, 6)).toBe(6);
  });

  it('returns 0 when both are 0', () => {
    expect(collapse(0, 0)).toBe(0);
  });

  it('handles one side being 0', () => {
    expect(collapse(0, 8)).toBe(8);
    expect(collapse(8, 0)).toBe(8);
  });
});

describe('resolveSeamGap', () => {
  const margins: Record<string, Margin> = {
    message: { top: 8, bottom: 8 },
    tool: { top: 2, bottom: 2 },
    diff: { top: 2, bottom: 6 },
  };
  const marginOf = (k: string): Margin | undefined => margins[k];

  it('returns max of adjacent declared margins (symmetric)', () => {
    // tool.bottom=2, tool.top=2 → max(2,2)=2
    expect(resolveSeamGap('tool', 'tool', marginOf)).toBe(2);
  });

  it('returns max of adjacent declared margins (asymmetric)', () => {
    // tool.bottom=2, message.top=8 → max(2,8)=8
    expect(resolveSeamGap('tool', 'message', marginOf)).toBe(8);
    // diff.bottom=6, tool.top=2 → max(6,2)=6
    expect(resolveSeamGap('diff', 'tool', marginOf)).toBe(6);
  });

  it('defaults to 0 when prev kind has no margin', () => {
    // unknown.bottom=0, tool.top=2 → max(0,2)=2
    expect(resolveSeamGap('unknown', 'tool', marginOf)).toBe(2);
  });

  it('defaults to 0 when cur kind has no margin', () => {
    // tool.bottom=2, unknown.top=0 → max(2,0)=2
    expect(resolveSeamGap('tool', 'unknown', marginOf)).toBe(2);
  });

  it('defaults to 0 for both sides when neither kind has a margin', () => {
    // 0 on both sides → max(0,0)=0
    expect(resolveSeamGap('x', 'y', marginOf)).toBe(0);
  });
});

// ── Block-layer seam equivalence ──────────────────────────────────────────────
//
// Compact margin values (post-refactor):
//   prose body: 6/6
//   code/table: 8/8
//   rule: 12/12

describe('block-layer seam equivalence via collapse', () => {
  const PROSE_GAP = 6;
  const BLOCK_GAP = 8;
  const RULE_GAP = 12;

  const blockMargins: Record<string, Margin> = {
    prose: { top: PROSE_GAP, bottom: PROSE_GAP },
    code: { top: BLOCK_GAP, bottom: BLOCK_GAP },
    table: { top: BLOCK_GAP, bottom: BLOCK_GAP },
    rule: { top: RULE_GAP, bottom: RULE_GAP },
  };
  const marginOf = (k: string): Margin | undefined => blockMargins[k];

  it('prose↔prose → proseGap', () => {
    expect(resolveSeamGap('prose', 'prose', marginOf)).toBe(PROSE_GAP);
  });

  it('code↔code → blockGap', () => {
    expect(resolveSeamGap('code', 'code', marginOf)).toBe(BLOCK_GAP);
  });

  it('table↔table → blockGap', () => {
    expect(resolveSeamGap('table', 'table', marginOf)).toBe(BLOCK_GAP);
  });

  it('prose↔code → max(6,8)=8', () => {
    expect(resolveSeamGap('prose', 'code', marginOf)).toBe(BLOCK_GAP);
  });

  it('code↔prose → max(8,6)=8', () => {
    expect(resolveSeamGap('code', 'prose', marginOf)).toBe(BLOCK_GAP);
  });

  it('prose↔table → max(6,8)=8', () => {
    expect(resolveSeamGap('prose', 'table', marginOf)).toBe(BLOCK_GAP);
  });

  it('prose↔rule → max(6,12)=12', () => {
    expect(resolveSeamGap('prose', 'rule', marginOf)).toBe(RULE_GAP);
  });

  it('rule↔prose → max(12,6)=12', () => {
    expect(resolveSeamGap('rule', 'prose', marginOf)).toBe(RULE_GAP);
  });
});
