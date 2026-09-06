import { useDebug } from '@components/contexts/debug-context';
import { Show, createSignal, onMount, type JSX, onCleanup } from 'solid-js';
import {
  debugLabel,
  debugMismatch,
  debugMismatchText,
  debugOk,
  debugOverlay,
  pblock,
} from './block-frame.css';

// ── Debug overlay ─────────────────────────────────────────────────────────────

type DebugOverlayProps = {
  id?: string;
  reservedHeight: number;
  elRef: () => HTMLElement | undefined;
};

function DebugOverlay(props: DebugOverlayProps) {
  const [mismatch, setMismatch] = createSignal(false);
  const [actualH, setActualH] = createSignal(0);

  onMount(() => {
    const el = props.elRef();
    if (!el) return;
    const check = () => {
      // offsetHeight is the correct probe here: it reads the border-box height
      // of the positioned frame, matching the reserveHeight() arithmetic that
      // produced props.reservedHeight.  scrollHeight is unreliable for frames
      // whose children are absolutely positioned (it excludes some padding).
      const h = el.offsetHeight;
      setActualH(h);
      setMismatch(Math.abs(h - props.reservedHeight) > 0.5);
    };
    const ro = new ResizeObserver(check);
    ro.observe(el);
    onCleanup(() => ro.disconnect());
    requestAnimationFrame(check);
  });

  return (
    <div class={`${debugOverlay} ${mismatch() ? debugMismatch : debugOk}`}>
      <span class={debugLabel}>
        {props.id ? `${props.id} · ` : ''}h={props.reservedHeight}
        <Show when={mismatch()}>
          {' '}
          <span class={debugMismatchText}>
            ⚠ actual={actualH()} (+{actualH() - props.reservedHeight})
          </span>
        </Show>
      </span>
    </div>
  );
}

// ── BlockFrame ────────────────────────────────────────────────────────────────

export type BlockFrameProps = {
  layout: { top: number; height: number; id?: string };
  class?: string;
  style?: JSX.CSSProperties;
  ref?: (el: HTMLElement) => void;
  children: JSX.Element;
};

export function BlockFrame(props: BlockFrameProps) {
  const debug = useDebug(); // () => boolean — reactive accessor
  let el: HTMLElement | undefined;
  const blockId = (props.layout as { id?: string }).id;

  return (
    <div
      ref={(e) => {
        el = e;
        props.ref?.(e);
      }}
      data-block-id={blockId}
      class={`${pblock}${props.class ? ` ${props.class}` : ''}`}
      style={{
        ...props.style,
        top: `${props.layout.top}px`,
        height: `${props.layout.height}px`,
        left: '0',
        right: '0',
        // Exact intrinsic size so the browser reserves the correct vertical space
        // while this block is skipped by content-visibility: auto. Must stay in
        // sync with layout.height (both come from the same measure() output).
        'contain-intrinsic-size': `0 ${props.layout.height}px`,
      }}
    >
      {props.children}
      <Show when={debug()}>
        <DebugOverlay id={blockId} reservedHeight={props.layout.height} elRef={() => el} />
      </Show>
    </div>
  );
}
