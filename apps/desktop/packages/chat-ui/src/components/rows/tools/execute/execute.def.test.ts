import type { SegmentCtx } from '@core/units';
import { describe, expect, it } from 'vitest';
import type { TerminalOutputSnapshot, ToolNode } from '@/model';
import { executeFromItem } from './execute.presenter';

function executeItem(overrides: Partial<Extract<ToolNode, { kind: 'execute-tool-call' }>> = {}) {
  return {
    kind: 'execute-tool-call',
    id: 'tool-1',
    seq: 0,
    toolCallId: 'call-1',
    title: 'echo ok',
    command: 'echo ok',
    status: 'done',
    ...overrides,
  } satisfies Extract<ToolNode, { kind: 'execute-tool-call' }>;
}

function ctx(snapshot: TerminalOutputSnapshot | null): SegmentCtx {
  return {
    caches: {} as SegmentCtx['caches'],
    expanded: () => false,
    active: false,
    plan: () => null,
    pendingToolCallIds: () => new Set<string>(),
    terminalOutput: () => snapshot,
  };
}

function snapshot(
  lines: readonly string[],
  overrides: Partial<TerminalOutputSnapshot> = {}
): TerminalOutputSnapshot {
  return { lines, truncated: false, version: 1, ...overrides };
}

describe('executeFromItem', () => {
  it('splits static outputText into lines when no terminal output is live', () => {
    expect(
      executeFromItem(executeItem({ outputText: 'static output\nsecond line' }), ctx(null))
    ).toMatchObject({
      command: 'echo ok',
      outputLines: ['static output', 'second line'],
    });
  });

  it('reuses the same static split across calls for the same item (identity-stable)', () => {
    const item = executeItem({ outputText: 'one\ntwo' });
    const first = executeFromItem(item, ctx(null)).outputLines;
    const second = executeFromItem(item, ctx(null)).outputLines;
    expect(first).toBe(second);
  });

  it('passes the live line array through by reference (no join, no re-split)', () => {
    const lines = ['live output', 'still going'];
    const result = executeFromItem(
      executeItem({ terminalId: 'term-1', outputText: 'stale output' }),
      ctx(snapshot(lines, { version: 7 }))
    );
    expect(result.outputLines).toBe(lines);
    expect(result.outputVersion).toBe(7);
    expect(result.terminalId).toBe('term-1');
  });

  it('collapses upstream truncation into a single outputTruncated flag', () => {
    expect(
      executeFromItem(
        executeItem({ terminalId: 'term-1' }),
        ctx(snapshot(['tail'], { truncated: true }))
      )
    ).toMatchObject({ outputTruncated: true });
  });

  it('falls back to static outputText when terminal output is unavailable', () => {
    expect(
      executeFromItem(
        executeItem({ terminalId: 'term-1', outputText: 'static fallback' }),
        ctx(null)
      )
    ).toMatchObject({
      outputLines: ['static fallback'],
      terminalId: 'term-1',
    });
  });

  it('passes provider inputSummary through for the card header', () => {
    expect(
      executeFromItem(executeItem({ inputSummary: 'Installing Dependencies' }), ctx(null))
    ).toMatchObject({
      inputSummary: 'Installing Dependencies',
    });
  });
});
