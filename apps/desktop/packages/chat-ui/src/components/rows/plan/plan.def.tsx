import { ROW_H } from '@components/engine/row-metrics';
import { CollapsibleCard } from '@components/primitives/CollapsibleCard';
import { IconPlanList } from '@components/primitives/icons';
import { PreviewWindow } from '@components/primitives/PreviewWindow';
import type { StackLayout } from '@core/compose';
import { type Measured, type MeasureCtx, type RenderCtx } from '@core/define';
import { layoutBlockStack } from '@core/layout/block-stack';
import type { SegmentCtx } from '@core/units';
import { defineUnit } from '@core/units';
import { pxTokens } from '@styles/px-tokens';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import { Show, createMemo } from 'solid-js';
import type { ChatPlan, PlanEntryPriority, PlanEntryStatus, ToolNode } from '@/model';
import { PlanList } from './Plan';
import { planVars, type PlanStyleVars } from './plan.css';

export type PlanVars = {
  /** Fixed height (px) of the plan header row. */
  rowH: number;
  /** Border width (px) of the plan card. */
  border: number;
  /** Horizontal padding (px) inside the plan card border, each side. */
  padX: number;
  /** Vertical padding (px) inside the expanded entry list, applied top and bottom. */
  padY: number;
  /** Width (px) of the status-icon box to the left of each entry body. */
  iconBox: number;
  /** Horizontal gap (px) between the status icon and the entry text. */
  iconGap: number;
  /** Vertical gap (px) between consecutive plan entries. */
  entryGap: number;
  /** Maximum height (px) of the collapsed preview window. */
  windowH: number;
};

export function planFromItem(
  item: Extract<ToolNode, { kind: 'create-plan-tool-call' }>,
  ctx: SegmentCtx
): ChatPlan {
  // The item carries the plan as this turn last saw it; older transcripts
  // without that snapshot fall back to the live session plan.
  const entries = item.entries ?? ctx.plan()?.entries ?? [];
  return {
    kind: 'plan',
    id: item.id,
    entries: entries.map(({ content, status, priority }) => ({ content, status, priority })),
    streaming: item.status === 'running',
  };
}

export type PlanEntryLaid = {
  /** Pre-measured block stack for this entry's content. */
  measured: Measured<StackLayout>;
  status: PlanEntryStatus;
  priority: PlanEntryPriority;
};

/** Total horizontal chrome: 2*padX + 2*border. */
function chromeX(vars: PlanVars): number {
  return 2 * vars.padX + 2 * vars.border;
}

/** Total vertical chrome: top border + header separator + bottom border. */
function chromeY(vars: PlanVars): number {
  return 3 * vars.border;
}

/** Total entry indent: icon box + icon gap. */
function entryIndent(vars: PlanVars): number {
  return vars.iconBox + vars.iconGap;
}

/** Lay out each entry's content into a measured block stack. */
function measureEntries(item: ChatPlan, ctx: MeasureCtx, vars: PlanVars): PlanEntryLaid[] {
  const bodyWidth = ctx.width - chromeX(vars) - entryIndent(vars);
  return item.entries.map((entry, i) => {
    const blocks = ctx.caches.parseBlocks(`${item.id}:e${i}`, entry.content);
    const measured = layoutBlockStack(blocks, { ...ctx, width: bodyWidth }, { padY: 0 });
    return { measured, status: entry.status, priority: entry.priority };
  });
}

function listHeight(entries: PlanEntryLaid[], vars: PlanVars): number {
  const totalEntryH = entries.reduce((sum, e) => sum + e.measured.height, 0);
  const gaps = entries.length > 1 ? (entries.length - 1) * vars.entryGap : 0;
  return totalEntryH + gaps + 2 * vars.padY;
}

function planMeasure(item: ChatPlan, ctx: MeasureCtx, vars: PlanVars): number {
  const headerH = vars.rowH;
  const isExpanded = ctx.expanded(item.id);
  const entries = measureEntries(item, ctx, vars);
  const listH = listHeight(entries, vars);
  const bodyH = isExpanded ? listH : Math.min(listH, vars.windowH);
  return headerH + bodyH + chromeY(vars);
}

function PlanUnitRender(props: { data: ChatPlan; ctx: RenderCtx; vars: PlanVars }) {
  const mCtx = () => props.ctx.measureCtx?.();
  // Inverted semantics: stored "collapsed" bool = "expanded".
  const isExpanded = () => props.ctx.viewState.isCollapsed(props.data.id);

  const entries = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return [];
    return measureEntries(props.data, ctx, props.vars);
  });

  const listH = createMemo(() => listHeight(entries(), props.vars));
  const bodyH = createMemo(() => (isExpanded() ? listH() : Math.min(listH(), props.vars.windowH)));

  const totalH = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return props.vars.rowH + chromeY(props.vars);
    return planMeasure(props.data, ctx, props.vars);
  });

  const autoScroll = () => !!props.data.streaming;
  const active = () =>
    !!props.data.streaming || props.data.entries.some((e) => e.status === 'in_progress');
  const done = () => props.data.entries.filter((e) => e.status === 'completed').length;
  const total = () => props.data.entries.length;

  const listStyleVars = (): PlanStyleVars => ({
    padX: props.vars.padX,
    padY: props.vars.padY,
    iconBox: props.vars.iconBox,
    iconGap: props.vars.iconGap,
    entryGap: props.vars.entryGap,
  });

  return (
    <div style={assignInlineVars(planVars, pxTokens(listStyleVars()))}>
      <CollapsibleCard
        id={props.data.id}
        ctx={props.ctx}
        height={totalH()}
        headerH={props.vars.rowH}
        expanded={isExpanded()}
        active={active()}
        icon={<IconPlanList />}
        header={
          <>
            Plan {done()} out of {total()} Tasks done
          </>
        }
      >
        <div style={{ 'padding-left': planVars.padX, 'padding-right': planVars.padX }}>
          <Show when={!isExpanded()} fallback={<PlanList entries={entries()} />}>
            <PreviewWindow
              height={bodyH()}
              maxH={props.vars.windowH}
              overlay="fade-bottom"
              autoScrollBottom={autoScroll()}
              contentHeight={() => listH()}
            >
              <PlanList entries={entries()} />
            </PreviewWindow>
          </Show>
        </div>
      </CollapsibleCard>
    </div>
  );
}

export const planUnitDef = defineUnit<ChatPlan, PlanVars>({
  kind: 'plan',
  margin: { top: 8, bottom: 8 },
  vars: {
    rowH: ROW_H,
    border: 1,
    padX: 8,
    padY: 6,
    iconBox: 14,
    iconGap: 8,
    entryGap: 4,
    windowH: 96,
  },

  estimate(item, ctx, vars): number {
    const headerH = vars.rowH;
    const isExpanded = ctx.expanded(item.id);
    const lineH = ctx.theme.fonts.body.lineHeight;
    const entryH = 2 * lineH;
    const gaps = item.entries.length > 1 ? (item.entries.length - 1) * vars.entryGap : 0;
    const listH = item.entries.length * entryH + gaps + 2 * vars.padY;
    const bodyH = isExpanded ? listH : Math.min(listH, vars.windowH);
    return headerH + bodyH + chromeY(vars);
  },

  measure: planMeasure,

  Render: PlanUnitRender,
});
