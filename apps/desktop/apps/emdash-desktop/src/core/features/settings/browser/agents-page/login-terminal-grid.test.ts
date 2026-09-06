import { describe, expect, it } from 'vitest';
import {
  MAX_LOGIN_COLS,
  MAX_LOGIN_ROWS,
  planLoginGrid,
  type LoginHostSize,
} from './login-terminal-grid';

const CELL = { cellWidth: 9, cellHeight: 18 };

function plan(hostSize: LoginHostSize, lastAppliedHostSize: LoginHostSize | null = null) {
  return planLoginGrid({ hostSize, ...CELL, paddingPx: 8, lastAppliedHostSize });
}

describe('planLoginGrid', () => {
  it('computes the grid from host size and real cell metrics', () => {
    const dims = plan({ width: 928, height: 520 });

    // 928 - 16 padding = 912 / 9 = 101 cols; 520 - 16 = 504 / 18 = 28 rows.
    expect(dims).toEqual({ cols: 101, rows: 28 });
  });

  it('skips a tick when the host size is unchanged since the last applied resize', () => {
    const size = { width: 928, height: 520 };

    expect(plan(size, { ...size })).toBeNull();
  });

  it('replans when the host size actually changed', () => {
    const dims = plan({ width: 928, height: 600 }, { width: 928, height: 520 });

    expect(dims).not.toBeNull();
    expect(dims!.rows).toBeGreaterThan(28);
  });

  it('clamps runaway host growth to the maximum grid', () => {
    // Simulates the resize feedback loop: the host reports an absurd height
    // (content-sized chain), which must degrade to a bounded grid.
    const dims = plan({ width: 967_870, height: 967_870 });

    expect(dims).toEqual({ cols: MAX_LOGIN_COLS, rows: MAX_LOGIN_ROWS });
  });

  it('feedback growth converges instead of compounding', () => {
    // Each applied resize is followed by a tick at the same host size (the
    // observer re-fires after terminal.resize); the guard must return null so
    // rows cannot compound off their own output.
    let lastApplied: LoginHostSize | null = null;
    const size = { width: 928, height: 520 };

    const first = plan(size, lastApplied);
    expect(first).not.toBeNull();
    lastApplied = { ...size };

    const echoTick = plan(size, lastApplied);
    expect(echoTick).toBeNull();
  });

  it('returns null for degenerate cell metrics', () => {
    expect(
      planLoginGrid({
        hostSize: { width: 928, height: 520 },
        cellWidth: 0,
        cellHeight: 0,
        paddingPx: 8,
        lastAppliedHostSize: null,
      })
    ).toBeNull();
  });
});
