import { StreamContext, type StreamAnimation } from '@components/contexts/StreamContext';
import { BlockStackView } from '@components/primitives/BlockStackView';
import { CopyButton } from '@components/primitives/CopyButton';
import type { StackLayout } from '@core/compose';
import type { MeasureCtx, Measured, RenderCtx } from '@core/define';
import { layoutBlockStack } from '@core/layout/block-stack';
import type { Block } from '@core/markdown/document';
import { blockPlainText } from '@core/markdown/plain-text';
import type { SegmentCtx } from '@core/units';
import { defineUnit } from '@core/units';
import { pxTokens } from '@styles/px-tokens';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import { Show, createMemo } from 'solid-js';
import type { ChatMessage } from '@/model';
import { attachStripHeight, type MessageVars, userInnerWidth } from './metrics';
import { UserMessageCard } from './UserMessageCard';
import {
  assistantOuter,
  assistantRoot,
  assistantVars,
  footerRow,
  messageText,
  srOnly,
} from './message.css';

export function messageFromItem(item: ChatMessage, ctx: SegmentCtx): ChatMessage {
  return {
    ...item,
    streaming: ctx.active && item.role === 'assistant',
    attachments: item.attachments?.map((attachment) => ({
      id: attachment.id,
      name: attachment.name,
      mimeType: attachment.mimeType,
    })),
  };
}

// ── Measure ───────────────────────────────────────────────────────────────────

export function measureMessage(item: ChatMessage, ctx: MeasureCtx, vars: MessageVars): number {
  const { userCardPadY, cardBorder, collapsedMaxH, expandedMaxH } = vars;
  const blocks = item.streaming
    ? ctx.caches.parseBlocksStreaming(item.id, item.text)
    : ctx.caches.parseBlocks(item.id, item.text);

  if (item.role === 'user') {
    const innerW = userInnerWidth(ctx.width, vars);
    const aH = attachStripHeight(item.attachments?.length ?? 0, innerW, vars);
    if (blocks.length === 0) {
      const fallback = aH + ctx.theme.fonts.body.lineHeight + 2 * userCardPadY + 2 * cardBorder;
      return Math.min(fallback, ctx.expandedId === item.id ? expandedMaxH : collapsedMaxH);
    }
    const innerCtx = { ...ctx, width: innerW };
    const stack = layoutBlockStack(blocks, innerCtx, { isCollapsed: ctx.isCollapsed });
    const contentH = aH + stack.height + 2 * userCardPadY + 2 * cardBorder;
    return Math.min(contentH, ctx.expandedId === item.id ? expandedMaxH : collapsedMaxH);
  }

  // assistant / thought
  const footer = item.role === 'assistant' ? vars.footerH : 0;
  if (blocks.length === 0) {
    return ctx.theme.fonts.body.lineHeight + footer;
  }
  const stack = layoutBlockStack(blocks, ctx, { isCollapsed: ctx.isCollapsed });
  return stack.height + footer;
}

function AssistantRender(props: { data: ChatMessage; ctx: RenderCtx; vars: MessageVars }) {
  const mCtx = () => props.ctx.measureCtx?.();

  // One frontier Map per mounted instance — persists across streaming chunks
  // because the <For> in UnitRow keeps this component alive. Shared by ref with
  // StreamContext so Prose.tsx can update it after each render without reactivity.
  //
  // `streaming` and `settledCount` are reactive accessors so Code.tsx effects
  // track the per-block settled transition (fence close or blank-line boundary)
  // and highlight each block exactly once when it crosses that boundary.
  const parsed = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return { blocks: [] as Block[], settledCount: 0 };
    const blocks = props.data.streaming
      ? ctx.caches.parseBlocksStreaming(props.data.id, props.data.text)
      : ctx.caches.parseBlocks(props.data.id, props.data.text);
    const settledCount = props.data.streaming
      ? ctx.caches.settledBlockCount(props.data.id)
      : blocks.length;
    return { blocks, settledCount };
  });

  const streamAnimation: StreamAnimation = {
    frontier: new Map(),
    streaming: () => props.data.streaming === true,
    settledCount: () => parsed().settledCount,
  };

  const stack = createMemo<Measured<StackLayout> | null>(() => {
    const ctx = mCtx();
    if (!ctx) return null;
    const blocks = parsed().blocks;
    if (blocks.length === 0) return null;
    return layoutBlockStack(blocks, ctx, { isCollapsed: ctx.isCollapsed });
  });

  const totalH = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return props.data.role === 'assistant' ? props.vars.footerH : 0;
    return measureMessage(props.data, ctx, props.vars);
  });

  const plainText = () => {
    const ctx = mCtx();
    if (!ctx) return props.data.text;
    // Use the same parse path as the renderer so we don't trigger a full reparse
    // during streaming just for the screen-reader text.
    const parse = props.data.streaming ? ctx.caches.parseBlocksStreaming : ctx.caches.parseBlocks;
    return parse(props.data.id, props.data.text).map(blockPlainText).join('\n\n');
  };

  const role = () =>
    (props.data.role === 'thought' ? 'thought' : 'assistant') as 'thought' | 'assistant';

  return (
    <div
      class={`${assistantOuter} ${messageText({ role: role() })} ${assistantRoot}`}
      style={assignInlineVars(assistantVars, pxTokens({ height: totalH() }))}
    >
      <div class={srOnly}>{plainText()}</div>
      <StreamContext.Provider value={props.data.streaming ? streamAnimation : null}>
        <Show when={stack()}>{(s) => <BlockStackView node={s()} />}</Show>
      </StreamContext.Provider>
      <Show when={props.data.role === 'assistant'}>
        <div
          class={footerRow}
          style={{ height: `${props.vars.footerH}px` }}
          aria-hidden={props.data.streaming ? 'true' : undefined}
        >
          <Show when={!props.data.streaming}>
            <CopyButton text={props.data.text} variant="inline" label="Copy message" />
          </Show>
        </div>
      </Show>
    </div>
  );
}

// ── MessageUnitRender ─────────────────────────────────────────────────────────

function MessageUnitRender(props: { data: ChatMessage; ctx: RenderCtx; vars: MessageVars }) {
  if (props.data.role === 'user') {
    return <UserMessageCard data={props.data} ctx={props.ctx} vars={props.vars} />;
  }
  return <AssistantRender data={props.data} ctx={props.ctx} vars={props.vars} />;
}

// ── UnitDef ───────────────────────────────────────────────────────────────────

export const messageUnitDef = defineUnit<ChatMessage, MessageVars>({
  kind: 'message',
  margin: { top: 8, bottom: 8 },
  vars: {
    cardBorder: 1,
    collapsedMaxH: 120,
    expandedMaxH: 360,
    userCardPadX: 16,
    userCardPadY: 16,
    attachThumb: 32,
    attachGap: 8,
    footerH: 24,
  },

  estimate(item, ctx, vars): number {
    if (item.role === 'user') {
      const innerW = userInnerWidth(ctx.width, vars);
      const lines = Math.max(1, Math.ceil(item.text.length / 60));
      const aH = attachStripHeight(item.attachments?.length ?? 0, innerW, vars);
      const est =
        aH + lines * ctx.theme.fonts.body.lineHeight + 2 * vars.userCardPadY + 2 * vars.cardBorder;
      return Math.min(est, ctx.expandedId === item.id ? vars.expandedMaxH : vars.collapsedMaxH);
    }
    const lines = Math.max(1, Math.ceil(item.text.length / 60));
    const footer = item.role === 'assistant' ? vars.footerH : 0;
    return lines * ctx.theme.fonts.body.lineHeight + footer;
  },

  measure: measureMessage,

  Render: MessageUnitRender,
});
