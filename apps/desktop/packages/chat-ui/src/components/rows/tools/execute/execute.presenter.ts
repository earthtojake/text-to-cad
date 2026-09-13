import type { SegmentCtx } from '@core/units';
import type { ChatExecute, ToolNode } from '@/model';

type ExecuteToolNode = Extract<ToolNode, { kind: 'execute-tool-call' }>;

/**
 * Memoized static-output split, keyed by node identity (ToolNodes are
 * identity-stable across streaming ticks). Keeps the returned lines array
 * identity-stable too, so downstream per-lines caches (width tracking) hit.
 */
const staticLinesMemo = new WeakMap<ExecuteToolNode, { text: string; lines: string[] }>();

function staticOutputLines(item: ExecuteToolNode): readonly string[] | undefined {
  if (item.outputText === undefined) return undefined;
  const hit = staticLinesMemo.get(item);
  if (hit && hit.text === item.outputText) return hit.lines;
  const lines = item.outputText.replace(/\r\n/g, '\n').split('\n');
  staticLinesMemo.set(item, { text: item.outputText, lines });
  return lines;
}

export function executeFromItem(item: ExecuteToolNode, ctx: SegmentCtx): ChatExecute {
  const live = item.terminalId ? ctx.terminalOutput(item.terminalId) : null;
  const outputLines = live ? live.lines : staticOutputLines(item);
  return {
    kind: 'execute',
    id: item.id,
    command: item.command ?? item.title,
    ...(item.inputSummary !== undefined ? { inputSummary: item.inputSummary } : {}),
    ...(outputLines !== undefined ? { outputLines } : {}),
    ...(live?.truncated ? { outputTruncated: true } : {}),
    ...(live ? { outputVersion: live.version } : {}),
    status: item.status,
    ...(item.error !== undefined ? { error: item.error } : {}),
    awaitingPermission: ctx.pendingToolCallIds().has(item.toolCallId),
    startedAt: 0,
    ...(item.terminalId !== undefined ? { terminalId: item.terminalId } : {}),
  };
}
