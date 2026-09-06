import { StreamContext, type StreamAnimation } from '@components/contexts/StreamContext';
import { useTheme } from '@components/contexts/ThemeContext';
import { HEADER_ROW_EXTRA_H } from '@components/engine/row-metrics';
import { BlockStackView } from '@components/primitives/BlockStackView';
import { CollapseHeader } from '@components/primitives/CollapseHeader';
import { PreviewWindow } from '@components/primitives/PreviewWindow';
import type { MeasureCtx, RenderCtx } from '@core/define';
import { layoutBlockStack } from '@core/layout/block-stack';
import type { Block } from '@core/markdown/document';
import { flattenBlockHeadings } from '@core/markdown/parse';
import { defineUnit } from '@core/units';
import { estimateThinkingTokens } from '@emdash/core/runtimes/acp/api/client';
import { pxTokens } from '@styles/px-tokens';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import { Show, createEffect, createMemo, createSignal, onCleanup, untrack } from 'solid-js';
import type { ChatThinking } from '@/model';
import {
  thinkingActive,
  thinkingCardVars,
  thinkingLabel,
  thinkingRoot,
  thinkingStatus,
  type ThinkingStyleVars,
} from './thinking.css';
import { sx } from '@styles/sprinkles.css';

export type ThinkingVars = {
  /** Measure-only: vertical padding baked into the body block-stack layout. */
  padY: number;
  /** Measure-only: preview window height during active thinking. */
  windowH: number;
};

const THINKING_VARS: ThinkingVars = {
  padY: 8,
  windowH: 72,
};

function thinkingHeaderH(ctx: MeasureCtx): number {
  return ctx.theme.fonts.body.lineHeight + HEADER_ROW_EXTRA_H;
}

function layoutThinkingBody(blocks: Block[], ctx: MeasureCtx, padY: number) {
  return layoutBlockStack(blocks, ctx, { padY });
}

function createAnimatedTokenCount(target: () => number, active: () => boolean) {
  const [value, setValue] = createSignal(untrack(active) ? 0 : untrack(target));

  createEffect(() => {
    const to = target();
    const shouldAnimate = active();
    const from = untrack(value);
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (!shouldAnimate || reduceMotion || from === to) {
      setValue(to);
      return;
    }

    const startedAt = performance.now();
    const durationMs = 180;
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / durationMs);
      const eased = 1 - (1 - progress) ** 3;
      setValue(Math.round(from + (to - from) * eased));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    onCleanup(() => cancelAnimationFrame(frame));
  });

  return value;
}

function ThinkingHeader(props: { item: ChatThinking; expanded: boolean; headerH: number }) {
  const startElapsed = Math.floor((Date.now() - props.item.startedAt) / 1000);
  const [elapsed, setElapsed] = createSignal(startElapsed);

  createEffect(() => {
    if (props.item.status !== 'thinking') return;
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - props.item.startedAt) / 1000));
    }, 1000);
    onCleanup(() => clearInterval(timer));
  });

  const tokenTarget = () => estimateThinkingTokens(props.item.text);
  const tokenCount = createAnimatedTokenCount(tokenTarget, () => props.item.status === 'thinking');

  const label = () => {
    const count = tokenCount();
    const tokenLabel = count > 0 ? ` · ~${count.toLocaleString()} tokens` : '';
    if (props.item.status === 'thinking') {
      if (elapsed() < 1) return `Thinking${tokenLabel}`;
      return `Thinking ${elapsed()}s${tokenLabel}`;
    }
    if (props.item.durationMs !== undefined) {
      if (props.item.durationMs < 1000) return `Thought briefly${tokenLabel}`;
      return `Thought for ${Math.floor(props.item.durationMs / 1000)}s${tokenLabel}`;
    }
    return `Thought${tokenLabel}`;
  };

  const statusAnnouncement = () => {
    if (props.item.status === 'thinking') return 'Thinking';
    if (props.item.durationMs === undefined) return 'Thought complete';
    if (props.item.durationMs < 1000) return 'Thought briefly';
    return `Thought for ${Math.floor(props.item.durationMs / 1000)} seconds`;
  };

  return (
    <CollapseHeader
      id={props.item.id}
      expanded={props.expanded}
      active={props.item.status === 'thinking'}
      height={props.headerH}
    >
      <span class={thinkingLabel}>{label()}</span>
      <span class={thinkingStatus} role="status" aria-live="polite" aria-atomic="true">
        {statusAnnouncement()}
      </span>
    </CollapseHeader>
  );
}

function thinkingMeasure(item: ChatThinking, ctx: MeasureCtx, vars: ThinkingVars): number {
  const headerH = thinkingHeaderH(ctx);
  const isExpanded = ctx.expanded(item.id);

  if (!isExpanded && item.status !== 'thinking') return headerH;

  const parsed =
    item.status === 'thinking'
      ? ctx.caches.parseBlocksStreaming(item.id, item.text ?? '')
      : ctx.caches.parseBlocks(item.id, item.text ?? '');
  const blocks = flattenBlockHeadings(parsed);
  const body = layoutThinkingBody(blocks, ctx, vars.padY);

  if (!isExpanded) return headerH + vars.windowH;
  return headerH + body.height;
}

function ThinkingUnitRender(props: { data: ChatThinking; ctx: RenderCtx; vars: ThinkingVars }) {
  const theme = useTheme();
  const mCtx = () => props.ctx.measureCtx?.();
  // Inverted semantics: stored "collapsed" bool = "expanded".
  const isExpanded = () => props.ctx.viewState.isCollapsed(props.data.id);

  const headerH = () => theme().fonts.body.lineHeight + HEADER_ROW_EXTRA_H;

  const parsed = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return { blocks: [] as Block[], settledCount: 0 };
    const streaming = props.data.status === 'thinking';
    const rawBlocks = streaming
      ? ctx.caches.parseBlocksStreaming(props.data.id, props.data.text ?? '')
      : ctx.caches.parseBlocks(props.data.id, props.data.text ?? '');
    const blocks = flattenBlockHeadings(rawBlocks);
    return {
      blocks,
      settledCount: streaming ? ctx.caches.settledBlockCount(props.data.id) : blocks.length,
    };
  });

  const streamAnimation: StreamAnimation = {
    frontier: new Map(),
    streaming: () => props.data.status === 'thinking',
    settledCount: () => parsed().settledCount,
  };

  const body = createMemo(() => {
    const ctx = mCtx();
    if (!ctx || parsed().blocks.length === 0) return null;
    return layoutThinkingBody(parsed().blocks, ctx, props.vars.padY);
  });

  const totalH = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return headerH();
    return thinkingMeasure(props.data, ctx, props.vars);
  });

  const transitionClipHeight = () => props.ctx.clipHeight?.() ?? null;
  const showBody = () =>
    isExpanded() || props.data.status === 'thinking' || transitionClipHeight() !== null;
  const bodyH = () => body()?.height ?? 0;

  const styleVars = (): ThinkingStyleVars => ({
    height: transitionClipHeight() ?? totalH(),
  });

  return (
    <div
      classList={{
        [sx({ color: 'fgPassive' })]: true,
        [thinkingRoot]: true,
        [thinkingActive]: props.data.status === 'thinking',
      }}
      style={assignInlineVars(thinkingCardVars, pxTokens(styleVars()))}
    >
      <ThinkingHeader item={props.data} expanded={isExpanded()} headerH={headerH()} />
      <StreamContext.Provider value={props.data.status === 'thinking' ? streamAnimation : null}>
        <Show when={showBody()}>
          <Show
            when={isExpanded()}
            fallback={
              <PreviewWindow
                height={props.vars.windowH}
                maxH={props.vars.windowH}
                overlay="fade-top"
                autoScrollBottom={props.data.status === 'thinking'}
                autoScrollBehavior="smooth"
                contentHeight={() => bodyH()}
              >
                <Show when={body()}>{(b) => <BlockStackView node={b()} />}</Show>
              </PreviewWindow>
            }
          >
            <Show when={body()}>{(b) => <BlockStackView node={b()} />}</Show>
          </Show>
        </Show>
      </StreamContext.Provider>
    </div>
  );
}

export const thinkingUnitDef = defineUnit<ChatThinking, ThinkingVars>({
  kind: 'thinking',
  margin: { top: 6, bottom: 6 },
  vars: THINKING_VARS,

  estimate(item, ctx, vars): number {
    const headerH = thinkingHeaderH(ctx);
    const isExpanded = ctx.expanded(item.id);

    if (!isExpanded) {
      if (item.status === 'thinking') return headerH + vars.windowH;
      return headerH;
    }

    const lines = Math.max(1, Math.ceil((item.text?.length ?? 0) / 60));
    return headerH + 2 * vars.padY + lines * ctx.theme.fonts.body.lineHeight;
  },

  heightAnimationKey(item) {
    return item.status;
  },

  measure: thinkingMeasure,

  Render: ThinkingUnitRender,
});
