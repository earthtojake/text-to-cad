/**
 * execute-stream.perf — per-chunk cost of streaming terminal output through
 * the execute row's presenter + measure path.
 *
 * Simulates the client line store: an identity-stable lines array mutated in
 * place with a version bump per flush. After each flush the test runs the real
 * per-update work (executeFromItem → executeUnitDef.measure) and times it.
 *
 * The regression this guards: before the line-structured store, every update
 * re-split and re-measured the entire accumulated output, so per-chunk cost
 * grew linearly with total output. With incremental display lines and
 * running-max width tracking, per-chunk cost must stay flat.
 */

import { executeFromItem, executeUnitDef } from '@components/rows/tools/execute/execute.def';
import { createChatCaches } from '@core/caches';
import type { MeasureCtx } from '@core/define';
import { DEFAULT_THEME } from '@core/theme';
import type { SegmentCtx } from '@core/units';
import { describe, expect, it } from 'vitest';
import type { TerminalOutputSnapshot, ToolNode } from '@/model';
import { now, record } from './harness';

const UPDATES = 240;
const LINES_PER_UPDATE = 25;

function executeItem(): Extract<ToolNode, { kind: 'execute-tool-call' }> {
  return {
    kind: 'execute-tool-call',
    id: 'perf-exec',
    seq: 0,
    toolCallId: 'perf-call',
    title: 'stream',
    command: 'stream --lots-of-output',
    status: 'running',
    terminalId: 'perf-term',
  };
}

function segCtx(snapshot: () => TerminalOutputSnapshot): SegmentCtx {
  return {
    caches: createChatCaches(),
    expanded: () => false,
    active: true,
    plan: () => null,
    pendingToolCallIds: () => new Set<string>(),
    terminalOutput: () => snapshot(),
  };
}

function mean(samples: number[]): number {
  return samples.reduce((sum, value) => sum + value, 0) / samples.length;
}

describe('execute row streaming cost', () => {
  it('per-chunk presenter+measure cost does not scale with accumulated output', () => {
    const item = executeItem();
    const lines: string[] = [''];
    let version = 0;
    const ctx = segCtx(() => ({ lines, truncated: false, version }));
    const measureCtx: MeasureCtx = {
      theme: DEFAULT_THEME,
      width: 640,
      isCollapsed: () => false,
      expanded: () => false,
      caches: createChatCaches(),
    };

    const perUpdateMs: number[] = [];
    for (let update = 0; update < UPDATES; update += 1) {
      // Simulate one coalesced flush appending a batch of completed lines.
      lines.pop();
      for (let i = 0; i < LINES_PER_UPDATE; i += 1) {
        lines.push(`[${update}:${i}] output line with some representative width ${'x'.repeat(i)}`);
      }
      lines.push('');
      version += 1;

      const start = now();
      const data = executeFromItem(item, ctx);
      executeUnitDef.measure(data, measureCtx, executeUnitDef.vars!);
      perUpdateMs.push(now() - start);
    }

    // Skip warmup; compare early steady-state cost against cost once ~6000
    // lines have accumulated.
    const early = mean(perUpdateMs.slice(20, 60));
    const late = mean(perUpdateMs.slice(UPDATES - 40));
    const ratio = late / early;

    record({
      label: 'execute stream per-update cost',
      'early mean (ms)': Number(early.toFixed(4)),
      'late mean (ms)': Number(late.toFixed(4)),
      'late/early ratio': Number(ratio.toFixed(2)),
      'total lines': lines.length,
    });

    // O(total-output) behavior produces a ratio near UPDATES-proportional
    // growth (>10x here); flat per-chunk cost stays near 1. The bound is loose
    // to absorb CI noise while still catching a linear regression.
    expect(ratio).toBeLessThan(4);
  });
});
