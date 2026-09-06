/**
 * PinnedUserMessage — a non-virtualized copy of a user message row, rendered
 * as the pinned-header overlay in ChatRoot when `pinUserMessages` is enabled.
 *
 * Layout:
 *   • `bg-chat-bg/80 backdrop-blur-sm` blurred strip at the top with padding
 *     equal to the user message's margin.top so the card starts at the same
 *     pin-line as inline rows.
 *   • `UserMessageCard` rendered directly — same card as the inline virtualized
 *     row, sharing the same expandedId so expand state is mirrored between the
 *     two. `pointer-events-auto` on the card makes clicks reach the outer
 *     wrapper's global handler.
 *   • 16px `fade-overlay-top` bottom fade signals rows scrolling below.
 *
 * `expandedId` is a reactive accessor (() => string | null) passed from ChatRoot
 * so the sticky card mirrors the same expand state as the inline row.
 *
 * Does NOT call `virt.setSize` — the overlay is outside the virtualizer tree.
 */

import type { ChatCaches } from '@core/caches';
import type { MeasureCtx, RenderCtx } from '@core/define';
import type { ChatTheme } from '@core/theme';
import type { ChatMessage } from '@/model';
import { messageUnitDef } from './message.def';
import { UserMessageCard } from './UserMessageCard';
import { pinnedBackdrop, pinnedScrollFade } from './user-message.css';

export function PinnedUserMessage(props: {
  item: ChatMessage;
  rowWidth: number;
  theme: ChatTheme;
  caches: ChatCaches;
  expandedId: () => string | null;
}) {
  const mCtx = (): MeasureCtx => ({
    theme: props.theme,
    width: props.rowWidth,
    isCollapsed: () => false,
    expanded: () => false,
    caches: props.caches,
    expandedId: props.expandedId(),
  });

  const renderCtx: RenderCtx = {
    viewState: { isCollapsed: () => false },
    measureCtx: mCtx,
  };

  return (
    <>
      <div class={pinnedBackdrop} style={{ 'padding-top': `${messageUnitDef.margin?.top ?? 8}px` }}>
        <UserMessageCard data={props.item} ctx={renderCtx} vars={messageUnitDef.vars!} />
      </div>
      {/* 16px scroll fade: signals that rows scroll beneath the pinned message. */}
      <div class={pinnedScrollFade} aria-hidden="true" />
    </>
  );
}
