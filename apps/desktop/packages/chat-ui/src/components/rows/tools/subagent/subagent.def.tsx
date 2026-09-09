import type { MeasureCtx, RenderCtx } from '@core/define';
import type { SegmentCtx } from '@core/units';
import { defineUnit } from '@core/units';
import { pxTokens } from '@styles/px-tokens';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import type { ChatSubagentToolCall, SubagentPhase, ToolNode } from '@/model';
import { SubagentHeader } from './Subagent';
import { subagentRoot, subagentVars } from './subagent.css';

export const SUBAGENT_INDICATOR_W = 16;
const SUBAGENT_ROW_GAP = 2;
const SUBAGENT_STATUS_ROW_H = 24;

type SpawnSubagentToolNode = Extract<ToolNode, { kind: 'spawn-subagent-tool-call' }>;

export function subagentPhase(
  item: Pick<ChatSubagentToolCall, 'status' | 'agentId'>
): SubagentPhase {
  if (item.status === 'done') return 'completed';
  if (item.status === 'error') return 'failed';
  return item.agentId ? 'running' : 'spawning';
}

export function subagentHeaderH(ctx: MeasureCtx): number {
  return ctx.theme.fonts.body.lineHeight + SUBAGENT_ROW_GAP + SUBAGENT_STATUS_ROW_H;
}

export function subagentHeaderHFromLineHeight(lineHeight: number): number {
  return lineHeight + SUBAGENT_ROW_GAP + SUBAGENT_STATUS_ROW_H;
}

const SUBAGENT_PREVIEW_LIMIT = 160;

function subagentOutputPreview(text: string | undefined): string | undefined {
  if (!text) return undefined;
  const line = text
    .split(/\r?\n/)
    .map((candidate) => candidate.trim())
    .find(Boolean);
  if (!line) return undefined;
  return line.length > SUBAGENT_PREVIEW_LIMIT
    ? `${line.slice(0, SUBAGENT_PREVIEW_LIMIT - 1)}…`
    : line;
}

export function subagentFromItem(
  item: SpawnSubagentToolNode,
  ctx: SegmentCtx
): ChatSubagentToolCall {
  const agentId = item.agentId || undefined;
  const status = item.status;
  const error = 'error' in item && typeof item.error === 'string' ? item.error : undefined;
  const name = item.name || item.title || 'Subagent';
  const outputPreview = subagentOutputPreview(item.outputText);
  return {
    kind: 'subagent',
    id: item.id,
    name,
    status,
    phase: subagentPhase({ status, agentId }),
    agentId,
    background: item.background,
    awaitingPermission: ctx.pendingToolCallIds().has(item.toolCallId),
    error,
    ...(outputPreview ? { outputPreview } : {}),
  };
}

function SubagentUnitRender(props: {
  data: ChatSubagentToolCall;
  ctx: RenderCtx;
  vars: Record<string, never>;
}) {
  const height = () => {
    const ctx = props.ctx.measureCtx?.();
    return ctx ? subagentHeaderH(ctx) : subagentHeaderHFromLineHeight(20);
  };

  return (
    <div
      class={subagentRoot}
      style={assignInlineVars(subagentVars, pxTokens({ height: height() }))}
    >
      <SubagentHeader item={props.data} height={height()} />
    </div>
  );
}

export const subagentUnitDef = defineUnit<ChatSubagentToolCall>({
  kind: 'subagent',
  margin: { top: 2, bottom: 8 },

  estimate(_item, ctx): number {
    return subagentHeaderH(ctx);
  },

  measure(_item, ctx): number {
    return subagentHeaderH(ctx);
  },

  Render: SubagentUnitRender,
});
