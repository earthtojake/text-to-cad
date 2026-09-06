import { ROW_H } from '@components/engine/row-metrics';
import { CollapsibleCard } from '@components/primitives/CollapsibleCard';
import { IconTerminal } from '@components/primitives/icons';
import { measureProseNaturalWidth } from '@components/rows/markdown/prose/layout';
import type { MeasureCtx, RenderCtx } from '@core/define';
import type { ProseBlock } from '@core/markdown/document';
import { defineUnit } from '@core/units';
import { Show, createMemo } from 'solid-js';
import type { ChatExecute } from '@/model';
import { ExecuteBody } from './Execute';
import { executeLines, maxOutputLineWidth, type ExecuteDisplayLine } from './execute-lines';

export { executeFromItem } from './execute.presenter';

export type ExecuteVars = {
  /** Fixed height (px) of the header row. */
  rowH: number;
  /** Border width (px) on each side of the card. */
  border: number;
  /** Horizontal padding on each command line. */
  linePadX: number;
  /** Width and height of the thin native scrollbar. */
  scrollbarSize: number;
  /** Visual separation between command text and the horizontal scrollbar. */
  scrollbarGap: number;
  /** Max lines shown in the collapsed (preview) state. */
  collapsedMaxLines: number;
  /** Max lines shown / scrollable in the expanded state. */
  expandedMaxLines: number;
};

const EXECUTE_VARS: ExecuteVars = {
  rowH: ROW_H,
  border: 1,
  linePadX: 12,
  scrollbarSize: 8,
  scrollbarGap: 3,
  collapsedMaxLines: 2,
  expandedMaxLines: 16,
};

/** 3 borders: top card edge + header-separator + bottom card edge. */
function chromeY(vars: ExecuteVars): number {
  return 3 * vars.border;
}

function executeBodyH(
  lines: ExecuteDisplayLine[],
  codeLineH: number,
  isExpanded: boolean,
  vars: ExecuteVars
): { bodyH: number; contentH: number } {
  const contentH = lines.length * codeLineH;
  const maxLines = isExpanded ? vars.expandedMaxLines : vars.collapsedMaxLines;
  const cap = maxLines * codeLineH;
  const bodyH = Math.min(contentH, cap);
  return { bodyH, contentH };
}

function measureLineWidth(text: string, ctx: MeasureCtx): number {
  const codeFonts = { ...ctx.theme.fonts, body: ctx.theme.fonts.code };
  const block: ProseBlock = {
    kind: 'prose',
    id: 'execute-width',
    variant: 'body',
    runs: [{ kind: 'text', text }],
  };
  return measureProseNaturalWidth(block, codeFonts);
}

/**
 * Max natural line width. Non-output display lines (command, truncation
 * indicator) are few and measured directly; output lines are tracked as an
 * incremental running max keyed on the live lines array, so per-update
 * measurement cost is proportional to new lines only.
 */
function maxNaturalWidth(item: ChatExecute, lines: ExecuteDisplayLine[], ctx: MeasureCtx): number {
  let max = 0;
  for (const line of lines) {
    if (line.kind === 'output') break; // output lines are contiguous at the end
    if (line.text) max = Math.max(max, measureLineWidth(line.text, ctx));
  }
  if (item.outputLines) {
    max = Math.max(
      max,
      maxOutputLineWidth(item.outputLines, ctx.theme.fonts, (text) => measureLineWidth(text, ctx))
    );
  }
  return max;
}

function hasHorizontalOverflow(
  item: ChatExecute,
  lines: ExecuteDisplayLine[],
  ctx: MeasureCtx,
  vars: ExecuteVars,
  verticalScrollbarW: number
): boolean {
  const availableWidth = ctx.width - 2 * vars.border - 2 * vars.linePadX - verticalScrollbarW;
  return maxNaturalWidth(item, lines, ctx) > availableWidth;
}

function scrollbarSpace(
  item: ChatExecute,
  lines: ExecuteDisplayLine[],
  ctx: MeasureCtx,
  vars: ExecuteVars,
  hasVerticalOverflow: boolean
): number {
  const verticalScrollbarW = hasVerticalOverflow ? vars.scrollbarSize : 0;
  return hasHorizontalOverflow(item, lines, ctx, vars, verticalScrollbarW)
    ? vars.scrollbarGap + vars.scrollbarSize
    : 0;
}

function executeUnitH(item: ChatExecute, ctx: MeasureCtx, vars: ExecuteVars): number {
  const isExpanded = ctx.expanded(item.id);
  const lines = executeLines(item);
  const { bodyH, contentH } = executeBodyH(
    lines,
    ctx.theme.fonts.code.lineHeight,
    isExpanded,
    vars
  );
  const hasVerticalOverflow = isExpanded && contentH > bodyH;
  return (
    vars.rowH + bodyH + scrollbarSpace(item, lines, ctx, vars, hasVerticalOverflow) + chromeY(vars)
  );
}

function ExecuteUnitRender(props: { data: ChatExecute; ctx: RenderCtx; vars: ExecuteVars }) {
  const mCtx = () => props.ctx.measureCtx?.();
  // Inverted semantics: stored "collapsed" bool = "expanded".
  const isExpanded = () => props.ctx.viewState.isCollapsed(props.data.id);

  const lines = createMemo(() => executeLines(props.data));
  const codeLineH = createMemo(() => mCtx()?.theme.fonts.code.lineHeight ?? 0);
  const bodyGeometry = createMemo(() => {
    const lineH = codeLineH();
    if (!lineH) return { bodyH: 0, contentH: 0 };
    return executeBodyH(lines(), lineH, isExpanded(), props.vars);
  });
  const showScrollbar = createMemo(() => {
    const ctx = mCtx();
    const geometry = bodyGeometry();
    const hasVerticalOverflow = isExpanded() && geometry.contentH > geometry.bodyH;
    const verticalScrollbarW = hasVerticalOverflow ? props.vars.scrollbarSize : 0;
    return ctx
      ? hasHorizontalOverflow(props.data, lines(), ctx, props.vars, verticalScrollbarW)
      : false;
  });

  const totalH = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return props.vars.rowH + chromeY(props.vars);
    return executeUnitH(props.data, ctx, props.vars);
  });

  return (
    <CollapsibleCard
      id={props.data.id}
      ctx={props.ctx}
      height={totalH()}
      headerH={props.vars.rowH}
      expanded={isExpanded()}
      active={props.data.status === 'running' && !props.data.awaitingPermission}
      error={props.data.status === 'error'}
      errorTitle={props.data.error}
      awaitingPermission={props.data.awaitingPermission}
      icon={<IconTerminal />}
      header={props.data.inputSummary || 'Execute'}
    >
      <Show when={codeLineH() > 0}>
        <ExecuteBody
          item={props.data}
          lines={lines()}
          bodyH={bodyGeometry().bodyH}
          contentH={bodyGeometry().contentH}
          codeLineH={codeLineH()}
          linePadX={props.vars.linePadX}
          scrollbarH={showScrollbar() ? props.vars.scrollbarSize : 0}
          scrollbarGap={showScrollbar() ? props.vars.scrollbarGap : 0}
          expanded={isExpanded()}
        />
      </Show>
    </CollapsibleCard>
  );
}

export const executeUnitDef = defineUnit<ChatExecute, ExecuteVars>({
  kind: 'execute',
  margin: { top: 2, bottom: 6 },
  vars: EXECUTE_VARS,

  estimate(item, ctx, vars): number {
    // Use the collapsed line cap and current width for stable initial geometry.
    const lines = executeLines(item);
    // Approximate code line height — use a fixed fallback of 20px for estimate.
    const approxLineH = 20;
    const { bodyH } = executeBodyH(lines, approxLineH, false, vars);
    return vars.rowH + bodyH + scrollbarSpace(item, lines, ctx, vars, false) + chromeY(vars);
  },

  measure(item, ctx, vars): number {
    return executeUnitH(item, ctx, vars);
  },

  Render: ExecuteUnitRender,
});
