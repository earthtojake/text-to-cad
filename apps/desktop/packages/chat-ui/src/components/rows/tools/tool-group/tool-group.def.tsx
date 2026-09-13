/**
 * ToolGroup — collapsible composite unit for hierarchical tool calls.
 *
 * A tool-group node is rendered as a single collapsible composite row instead
 * of a flat row for each child tool call.
 *
 * Layout:
 *   ┌─ CollapseHeader/SubagentHeader ─────────────────────────────┐
 *   │ PreviewWindow (collapsed) OR ChildStack (expanded)          │
 *   └─────────────────────────────────────────────────────────────┘
 *
 * Children are dispatched to their native leaf UnitDef.Render with no inset.
 * Multi-level nesting is handled by recursing through `ToolGroupRender`.
 */

import { useTheme } from '@components/contexts/ThemeContext';
import { HEADER_ROW_EXTRA_H, ROW_H } from '@components/engine/row-metrics';
import { CollapseHeader } from '@components/primitives/CollapseHeader';
import { PreviewWindow } from '@components/primitives/PreviewWindow';
import { planUnitDef } from '@components/rows/plan/plan.def';
import { diffUnitDef } from '@components/rows/tools/diff/diff.def';
import { executeUnitDef } from '@components/rows/tools/execute/execute.def';
import { fileOpUnitDef } from '@components/rows/tools/file-op/file-op.def';
import { SubagentHeader } from '@components/rows/tools/subagent/Subagent';
import {
  subagentHeaderH,
  subagentHeaderHFromLineHeight,
  subagentUnitDef,
} from '@components/rows/tools/subagent/subagent.def';
import { toolUnitDef } from '@components/rows/tools/tool/tool.def';
import type { MeasureCtx, RenderCtx } from '@core/define';
import type { UnitDef } from '@core/units';
import { defineUnit } from '@core/units';
import type { ItemNode } from '@state/flatten';
import { pxTokens } from '@styles/px-tokens';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import type { JSX } from 'solid-js';
import { For, Show, createMemo } from 'solid-js';
import type { ChatItem, ChatSubagentToolCall, ChatToolCall } from '@/model';
import { toolGroupCardVars, toolGroupRoot } from './tool-group.css';
import { subagentChildrenOffset } from '@components/rows/tools/subagent/subagent.css';

// ── Vars ──────────────────────────────────────────────────────────────────────

export type ToolGroupVars = {
  /** Max height (px) of the collapsed preview window. */
  windowH: number;
  /** Vertical gap (px) between consecutive children. */
  childGap: number;
};

const TOOL_GROUP_VARS: ToolGroupVars = {
  windowH: 180,
  childGap: 4,
};

const SUBAGENT_GROUP_BOTTOM_SPACER_H = 6;

// ── Child dispatch table ──────────────────────────────────────────────────────
//
// Direct imports of leaf defs avoids a circular dependency on unit-registry.ts.
// Only tool-family kinds can appear as children.

// oxlint-disable-next-line typescript/no-explicit-any -- registry boundary
const CHILD_DEFS: Record<string, UnitDef<any, any>> = {
  tool: toolUnitDef,
  subagent: subagentUnitDef,
  execute: executeUnitDef,
  diff: diffUnitDef,
  'file-op': fileOpUnitDef,
  plan: planUnitDef,
};

// ── Geometry helpers ──────────────────────────────────────────────────────────

function headerH(ctx: MeasureCtx): number {
  return ctx.theme.fonts.body.lineHeight + HEADER_ROW_EXTRA_H;
}

function isSubagentItem(item: ChatItem): item is ChatSubagentToolCall {
  return item.kind === 'subagent';
}

function nodeHeaderH(node: ItemNode, ctx: MeasureCtx): number {
  return isSubagentItem(node.item) ? subagentHeaderH(ctx) : headerH(ctx);
}

function isActiveItem(item: ChatItem): boolean {
  if (isSubagentItem(item)) return item.phase === 'spawning' || item.phase === 'running';
  return (item as ChatToolCall).status === 'running';
}

function canShowCollapsedPreview(item: ChatItem): boolean {
  return isActiveItem(item);
}

function subagentGroupBottomSpacerH(item: ChatItem): number {
  return isSubagentItem(item) ? SUBAGENT_GROUP_BOTTOM_SPACER_H : 0;
}

/**
 * Recursively sum the measured heights of all children in `node`.
 * Gaps between consecutive children are included.
 */
function childrenHeight(node: ItemNode, ctx: MeasureCtx, vars: ToolGroupVars): number {
  if (node.children.length === 0) return 0;
  let h = 0;
  for (let i = 0; i < node.children.length; i++) {
    if (i > 0) h += vars.childGap;
    const child = node.children[i];
    if (child.children.length > 0) {
      // Recurse: child is itself a parent.
      h += toolGroupUnitDef.measure(child, ctx, vars);
    } else {
      const def = CHILD_DEFS[child.item.kind];
      h += def ? def.measure(child.item, ctx, def.vars ?? {}) : ROW_H;
    }
  }
  return h;
}

function toolGroupUnitH(node: ItemNode, ctx: MeasureCtx, vars: ToolGroupVars): number {
  const hH = nodeHeaderH(node, ctx);
  const isExpanded = ctx.expanded(node.item.id);
  const showPreview = canShowCollapsedPreview(node.item);
  const chH = childrenHeight(node, ctx, vars);
  return (
    hH +
    (isExpanded ? chH : showPreview ? Math.min(chH, vars.windowH) : 0) +
    subagentGroupBottomSpacerH(node.item)
  );
}

// ── ChildStack ────────────────────────────────────────────────────────────────

/**
 * Render a leaf child (no children of its own) by dispatching to the native
 * def's Render component. The def is looked up once from CHILD_DEFS; `kind`
 * never changes on an existing item.
 */
function ChildLeaf(props: { node: ItemNode; ctx: RenderCtx; vars: ToolGroupVars }) {
  const def = CHILD_DEFS[props.node.item.kind];
  if (!def) return null;
  // Assign to a PascalCase local so JSX treats it as a component call.
  // oxlint-disable-next-line typescript/no-explicit-any -- registry boundary
  const Renderer = def.Render as (p: { data: ChatItem; ctx: RenderCtx; vars: any }) => JSX.Element;
  return <Renderer data={props.node.item} ctx={props.ctx} vars={def.vars ?? {}} />;
}

/**
 * Render one child node, dispatching to the recursive ToolGroupRender for
 * nested parents or to the native leaf def for leaf children.
 */
function ChildItem(props: { node: ItemNode; ctx: RenderCtx; vars: ToolGroupVars }) {
  return (
    <Show
      when={props.node.children.length > 0}
      fallback={<ChildLeaf node={props.node} ctx={props.ctx} vars={props.vars} />}
    >
      {/* Recursive parent */}
      <ToolGroupRender data={props.node} ctx={props.ctx} vars={props.vars} />
    </Show>
  );
}

function ChildStack(props: { node: ItemNode; ctx: RenderCtx; vars: ToolGroupVars }) {
  return (
    <For each={props.node.children}>
      {(child, i) => (
        <div
          style={{
            'margin-top': i() > 0 ? `${props.vars.childGap}px` : undefined,
          }}
        >
          <ChildItem node={child} ctx={props.ctx} vars={props.vars} />
        </div>
      )}
    </For>
  );
}

// ── Render ────────────────────────────────────────────────────────────────────

function ToolGroupRender(props: { data: ItemNode; ctx: RenderCtx; vars: ToolGroupVars }) {
  const theme = useTheme();
  const mCtx = () => props.ctx.measureCtx?.();

  // Inverted semantics: stored "collapsed" = "expanded".
  const isExpanded = () => props.ctx.viewState.isCollapsed(props.data.item.id);

  const isSubagent = () => isSubagentItem(props.data.item);
  const hH = () =>
    isSubagent()
      ? subagentHeaderHFromLineHeight(theme().fonts.body.lineHeight)
      : theme().fonts.body.lineHeight + HEADER_ROW_EXTRA_H;

  const chH = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return 0;
    return childrenHeight(props.data, ctx, props.vars);
  });

  const totalH = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return hH();
    return toolGroupUnitH(props.data, ctx, props.vars);
  });

  const isActive = () => isActiveItem(props.data.item);
  const label = () => {
    const item = props.data.item;
    if (item.kind === 'tool') return (item as ChatToolCall).name;
    return item.kind;
  };

  const showCollapsedPreview = () => canShowCollapsedPreview(props.data.item);
  const previewH = () => Math.min(chH(), props.vars.windowH);
  const childStack = () => (
    <Show
      when={isSubagent()}
      fallback={<ChildStack node={props.data} ctx={props.ctx} vars={props.vars} />}
    >
      <div class={subagentChildrenOffset}>
        <ChildStack node={props.data} ctx={props.ctx} vars={props.vars} />
      </div>
    </Show>
  );

  return (
    <div
      class={toolGroupRoot}
      style={assignInlineVars(toolGroupCardVars, pxTokens({ height: totalH() }))}
    >
      <Show
        when={isSubagent()}
        fallback={
          <CollapseHeader
            id={props.data.item.id}
            expanded={isExpanded()}
            active={isActive()}
            height={hH()}
          >
            {label()}
          </CollapseHeader>
        }
      >
        <SubagentHeader
          item={props.data.item as ChatSubagentToolCall}
          expanded={isExpanded()}
          height={hH()}
          collapsible
        />
      </Show>
      <Show
        when={isExpanded()}
        fallback={
          <Show when={showCollapsedPreview() && chH() > 0}>
            <PreviewWindow
              height={previewH()}
              maxH={props.vars.windowH}
              overlay="fade-bottom"
              autoScrollBottom={isActive()}
              contentHeight={chH}
            >
              {childStack()}
            </PreviewWindow>
          </Show>
        }
      >
        {childStack()}
      </Show>
      <Show when={isSubagent()}>
        <div style={{ height: `${SUBAGENT_GROUP_BOTTOM_SPACER_H}px` }} />
      </Show>
    </div>
  );
}

// ── UnitDef ───────────────────────────────────────────────────────────────────

export const toolGroupUnitDef = defineUnit<ItemNode, ToolGroupVars>({
  kind: 'tool-group',
  margin: { top: 2, bottom: 2 },
  vars: TOOL_GROUP_VARS,

  estimate(node, ctx, vars): number {
    const hH = nodeHeaderH(node, ctx);
    const isExpanded = ctx.expanded(node.item.id);
    const showPreview = canShowCollapsedPreview(node.item);
    // Approximate: 32px per child.
    const chH = node.children.length * ROW_H;
    return (
      hH +
      (isExpanded ? chH : showPreview ? Math.min(chH, vars.windowH) : 0) +
      subagentGroupBottomSpacerH(node.item)
    );
  },

  measure(node, ctx, vars): number {
    return toolGroupUnitH(node, ctx, vars);
  },

  Render: ToolGroupRender,
});
