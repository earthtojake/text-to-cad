import { useCommands } from '@components/contexts/CommandsContext';
import { useTurnState } from '@components/contexts/TurnStateContext';
import { BlockStackView } from '@components/primitives/BlockStackView';
import { clipTrackedHeight, isCardAnimating } from '@components/primitives/card-clip';
import { IconStop, ImageOffIcon } from '@components/primitives/icons';
import type { StackLayout } from '@core/compose';
import type { Measured, RenderCtx } from '@core/define';
import { layoutBlockStack } from '@core/layout/block-stack';
import { blockPlainText } from '@core/markdown/plain-text';
import { pxTokens } from '@styles/px-tokens';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import { For, Show, createMemo, createResource } from 'solid-js';
import type { ChatImageAttachment, ChatMessage } from '@/model';
import { attachStripHeight, type MessageVars, userInnerWidth } from './metrics';
import { srOnly } from './message.css';
import {
  attachmentStrip,
  attachPlaceholder,
  attachThumb,
  attachThumbBtn,
  card,
  cardFadeOverlay,
  cardRoot,
  cardVars,
  stopButtonOverlay,
  userCardGroup,
} from './user-message.css';

export function UserMessageCard(props: { data: ChatMessage; ctx: RenderCtx; vars: MessageVars }) {
  const commands = useCommands();
  const turn = useTurnState();
  const mCtx = () => props.ctx.measureCtx?.();

  const isCurrent = () => turn.currentMessageId() === props.data.id;
  const showStop = () => isCurrent() && turn.turnStatus() === 'generating';

  const styleVars = () => ({
    userCardPadX: props.vars.userCardPadX,
    userCardPadY: props.vars.userCardPadY,
    cardBorder: props.vars.cardBorder,
    attachThumb: props.vars.attachThumb,
    attachGap: props.vars.attachGap,
  });

  const innerWidth = () => {
    const c = mCtx();
    return c ? userInnerWidth(c.width, props.vars) : 0;
  };

  const stack = createMemo<Measured<StackLayout> | null>(() => {
    const ctx = mCtx();
    if (!ctx) return null;
    const blocks = ctx.caches.parseBlocks(props.data.id, props.data.text);
    if (blocks.length === 0) return null;
    const innerCtx = { ...ctx, width: innerWidth() };
    return layoutBlockStack(blocks, innerCtx, { isCollapsed: ctx.isCollapsed });
  });

  const fullContentH = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return props.vars.collapsedMaxH;
    const innerW = userInnerWidth(ctx.width, props.vars);
    const aH = attachStripHeight(props.data.attachments?.length ?? 0, innerW, props.vars);
    const blocks = ctx.caches.parseBlocks(props.data.id, props.data.text);
    if (blocks.length === 0) {
      return (
        aH +
        ctx.theme.fonts.body.lineHeight +
        2 * props.vars.userCardPadY +
        2 * props.vars.cardBorder
      );
    }
    const innerCtx = { ...ctx, width: innerW };
    const s = layoutBlockStack(blocks, innerCtx, { isCollapsed: ctx.isCollapsed });
    return aH + s.height + 2 * props.vars.userCardPadY + 2 * props.vars.cardBorder;
  });

  const isExpanded = () => mCtx()?.expandedId === props.data.id;
  const maxH = () => (isExpanded() ? props.vars.expandedMaxH : props.vars.collapsedMaxH);
  const clampedH = () => Math.min(fullContentH(), maxH());
  const isOverflowing = () => fullContentH() > maxH();

  // Track the animated clip edge during expand/collapse tween so the bottom
  // border and rounded corners are never hidden by the UnitRow overflow clip.
  const cardH = clipTrackedHeight(props.ctx, clampedH);

  const plainText = () => {
    const ctx = mCtx();
    if (!ctx) return props.data.text;
    return ctx.caches.parseBlocks(props.data.id, props.data.text).map(blockPlainText).join('\n\n');
  };

  return (
    <div
      data-user-card={props.data.id}
      class={`${card({ state: isOverflowing() && !isExpanded() ? 'overflowing' : 'static', current: showStop() })} ${cardRoot} ${userCardGroup}`}
      style={{
        ...assignInlineVars(cardVars, pxTokens({ ...styleVars(), height: cardH() })),
        // Force overflow:hidden while the UnitRow tween is in flight to avoid
        // a transient scrollbar mid-animation; restore auto only when expanded
        // at rest (so the user can scroll long messages).
        'overflow-y': isCardAnimating(props.ctx) || !isExpanded() ? 'hidden' : 'auto',
        cursor: !isExpanded() && isOverflowing() ? 'pointer' : 'default',
      }}
    >
      <div class={srOnly}>{plainText()}</div>
      <Show when={props.data.attachments?.length}>
        <div class={attachmentStrip}>
          <For each={props.data.attachments}>
            {(att) => <AttachmentThumb attachment={att} itemId={props.data.id} />}
          </For>
        </div>
      </Show>
      <Show when={stack()}>{(s) => <BlockStackView node={s()} />}</Show>
      <Show when={!isExpanded() && isOverflowing()}>
        <div class={cardFadeOverlay} />
      </Show>
      <Show when={showStop()}>
        <button
          type="button"
          class={stopButtonOverlay}
          aria-label="Stop generating"
          onClick={(e) => {
            e.stopPropagation();
            commands().onStop?.({ itemId: props.data.id });
          }}
        >
          <IconStop />
        </button>
      </Show>
    </div>
  );
}

function AttachmentThumb(props: { attachment: ChatImageAttachment; itemId: string }) {
  const commands = useCommands();
  const [resolvedDataUrl] = createResource(
    () => (props.attachment.dataUrl ? null : props.attachment.id),
    async () => commands().resolveAttachment?.(props.attachment) ?? null
  );
  const dataUrl = () => props.attachment.dataUrl ?? resolvedDataUrl() ?? undefined;

  return (
    <Show
      when={dataUrl()}
      fallback={
        <div title={props.attachment.name} class={attachPlaceholder}>
          <ImageOffIcon />
        </div>
      }
    >
      {(src) => (
        <button
          type="button"
          class={attachThumbBtn}
          aria-label={`View image: ${props.attachment.name}`}
          onClick={(e) => {
            e.stopPropagation();
            commands().onViewImage?.({
              attachment: { ...props.attachment, dataUrl: src() },
              itemId: props.itemId,
              source: 'user-message',
            });
          }}
        >
          <img src={src()} alt={props.attachment.name} class={attachThumb} />
        </button>
      )}
    </Show>
  );
}

export { userInnerWidth };
export type { MessageVars };
