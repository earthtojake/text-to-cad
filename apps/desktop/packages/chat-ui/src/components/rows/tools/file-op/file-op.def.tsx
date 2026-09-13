import { ROW_H } from '@components/engine/row-metrics';
import { PreviewWindow } from '@components/primitives/PreviewWindow';
import type { MeasureCtx, RenderCtx } from '@core/define';
import type { SegmentCtx } from '@core/units';
import { defineUnit } from '@core/units';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import { Show, createMemo } from 'solid-js';
import type { ChatFileOpToolCall, ToolNode } from '@/model';
import { FileOpRow, FileOpHeader, FileOpList, FileOpPreviewBody } from './FileOperation';
import { fileOpCardVars, fileOpRoot } from './file-op.css';

export type FileOpVars = {
  /** Measure-only: fixed row height for header and per-file lines. */
  rowH: number;
  /** Style-relevant: vertical padding inside the file list. Consumed by fileOpCardVars. */
  padY: number;
  /** Measure-only: scrollable preview window height while running. */
  windowH: number;
};

export function readFileOpFromItem(
  item: Extract<ToolNode, { kind: 'read-tool-call' }>,
  ctx: SegmentCtx
): ChatFileOpToolCall {
  return {
    kind: 'file-op',
    id: item.id,
    op: 'read',
    status: item.status,
    ...(item.error !== undefined ? { error: item.error } : {}),
    awaitingPermission: ctx.pendingToolCallIds().has(item.toolCallId),
    ops: item.path || item.resource ? [{ path: item.path ?? item.resource! }] : [],
  };
}

export function deleteFileOpFromItem(
  item: Extract<ToolNode, { kind: 'delete-file-tool-call' }>,
  ctx: SegmentCtx
): ChatFileOpToolCall {
  return {
    kind: 'file-op',
    id: item.id,
    op: 'delete',
    status: item.status,
    ...(item.error !== undefined ? { error: item.error } : {}),
    awaitingPermission: ctx.pendingToolCallIds().has(item.toolCallId),
    ops: [{ path: item.path }],
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function measureFileOpH(item: ChatFileOpToolCall, ctx: MeasureCtx, vars: FileOpVars): number {
  const { rowH, padY, windowH } = vars;
  const isExpanded = ctx.expanded(item.id);

  if (item.ops.length <= 1) return rowH;
  if (isExpanded) return rowH + item.ops.length * rowH + 2 * padY;
  if (item.status === 'running') return rowH + windowH;
  return rowH;
}

// ── Render ────────────────────────────────────────────────────────────────────

function FileOpUnitRender(props: { data: ChatFileOpToolCall; ctx: RenderCtx; vars: FileOpVars }) {
  const rowH = () => props.vars.rowH;
  const padY = () => props.vars.padY;
  const windowH = () => props.vars.windowH;

  // Inverted semantics: stored "collapsed" bool = "expanded".
  const isExpanded = () => props.ctx.viewState.isCollapsed(props.data.id);

  const totalH = createMemo(() => {
    const ctx = props.ctx.measureCtx?.();
    if (!ctx) return props.vars.rowH;
    return measureFileOpH(props.data, ctx, props.vars);
  });

  return (
    <div class={fileOpRoot} style={assignInlineVars({ [fileOpCardVars.height]: `${totalH()}px` })}>
      <Show
        when={props.data.ops.length > 1}
        fallback={<FileOpRow item={props.data} rowH={rowH()} lineH={rowH()} />}
      >
        <FileOpHeader item={props.data} expanded={isExpanded()} rowH={rowH()} />
        <Show when={isExpanded()}>
          <FileOpList item={props.data} lineH={rowH()} padY={padY()} />
        </Show>
        <Show when={!isExpanded() && props.data.status === 'running'}>
          <PreviewWindow
            height={windowH()}
            maxH={windowH()}
            overlay="fade-top"
            autoScrollBottom
            contentHeight={() => props.data.ops.length}
          >
            <FileOpPreviewBody item={props.data} lineH={rowH()} padY={padY()} />
          </PreviewWindow>
        </Show>
      </Show>
    </div>
  );
}

// ── UnitDef ───────────────────────────────────────────────────────────────────

export const fileOpUnitDef = defineUnit<ChatFileOpToolCall, FileOpVars>({
  kind: 'file-op',
  margin: { top: 2, bottom: 2 },
  vars: {
    rowH: ROW_H,
    padY: 6,
    windowH: 72,
  },

  estimate(item, ctx, vars): number {
    return measureFileOpH(item, ctx, vars);
  },

  measure(item, ctx, vars): number {
    return measureFileOpH(item, ctx, vars);
  },

  Render: FileOpUnitRender,
});
