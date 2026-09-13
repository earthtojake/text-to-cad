import { Show, createEffect, onCleanup } from 'solid-js';
import type { JSX } from 'solid-js';
import { overlay } from './preview-window.css';
import { fadeOverlayBottom, fadeOverlayTop } from '@styles/effects.css';

export type PreviewWindowProps = {
  /** Outer container height (px). */
  height: number;
  /** Maximum scrollable area height (px). */
  maxH: number;
  overlay?: 'fade-top' | 'fade-bottom';
  /**
   * When true, scroll the container to the bottom whenever `contentHeight` changes.
   * Use for streaming content that grows from the bottom.
   */
  autoScrollBottom?: boolean;
  /** Smooth only the visual viewport; canonical streamed content is never buffered. */
  autoScrollBehavior?: 'instant' | 'smooth';
  /**
   * Reactive accessor whose value changes whenever content grows. When
   * `autoScrollBottom` is true, changing this value triggers a scroll-to-bottom.
   * Pass `() => item.text?.length` or similar growing signal.
   */
  contentHeight?: () => number;
  children: JSX.Element;
};

export function PreviewWindow(props: PreviewWindowProps): JSX.Element {
  let scrollEl: HTMLDivElement | undefined;

  createEffect(() => {
    if (!props.autoScrollBottom) return;
    // Track contentHeight to retrigger on every content-growth tick.
    props.contentHeight?.();
    if (!scrollEl) return;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (
      props.autoScrollBehavior === 'smooth' &&
      !reduceMotion &&
      typeof scrollEl.scrollTo === 'function'
    ) {
      scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: 'smooth' });
    } else {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    }
  });

  onCleanup(() => {
    scrollEl = undefined;
  });

  return (
    <div
      style={{
        height: `${props.height}px`,
        'max-height': `${props.maxH}px`,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <Show when={props.overlay}>
        <div
          class={`${props.overlay === 'fade-top' ? fadeOverlayTop : fadeOverlayBottom} ${overlay({ position: props.overlay === 'fade-top' ? 'top' : 'bottom' })}`}
          style={{ height: '28px' }}
          aria-hidden="true"
        />
      </Show>
      <div
        ref={(el) => {
          scrollEl = el;
        }}
        style={{
          'max-height': `${props.maxH}px`,
          overflow: props.autoScrollBottom ? 'auto' : 'hidden',
          'scrollbar-gutter': props.autoScrollBottom ? 'stable' : undefined,
        }}
      >
        {props.children}
      </div>
    </div>
  );
}
