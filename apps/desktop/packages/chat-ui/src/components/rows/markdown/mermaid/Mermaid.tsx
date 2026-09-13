/**
 * Mermaid — Solid component rendering a MermaidLaidOut block.
 *
 * Renders a plain placeholder first (synchronous), then swaps to an SVG
 * on an idle callback (non-blocking, mirroring Code.tsx / Shiki).
 *
 * The container is fixed at a 21:9 aspect ratio (height pre-computed in
 * mermaid.def.tsx from the measured width). On click the host's
 * onViewMermaid command is fired, allowing the application to open a
 * full-size diagram viewer.
 */

import { useCaches } from '@components/contexts/CachesContext';
import { useCommands } from '@components/contexts/CommandsContext';
import { BlockFrame } from '@components/engine/block-frame';
import { cancelIdle, scheduleIdle } from '@components/engine/dom-utils';
import type { MermaidLaidOut } from '@core/layout/layout-types';
import type { MermaidBlock } from '@core/markdown/document';
import { Show, createEffect, createSignal, onCleanup } from 'solid-js';
import { mermaidError, mermaidPlaceholder, mermaidWrapper } from './mermaid.css';

export type MermaidProps = {
  block: MermaidLaidOut;
  rawBlock: MermaidBlock;
};

export function Mermaid(props: MermaidProps) {
  const caches = useCaches();
  const commands = useCommands();
  const [svg, setSvg] = createSignal<string | null>(null);
  const [failed, setFailed] = createSignal(false);

  createEffect(() => {
    const source = props.rawBlock.source;

    // Reset state when source changes.
    setSvg(null);
    setFailed(false);

    // Synchronous fast-path when SVG is already cached (e.g. scroll-back).
    const cached = caches.peekMermaid(source);
    if (cached) {
      setSvg(cached);
      return;
    }

    // Deferred path — render on idle to keep first-paint / scroll off the
    // critical synchronous path.
    let cancelled = false;
    const handle = scheduleIdle(() => {
      if (cancelled) return;
      const result = caches.renderMermaid(source);
      if (cancelled) return;
      if (result) {
        setSvg(result);
      } else {
        // Invalid / unsupported diagram — show error fallback.
        setFailed(true);
      }
    });

    onCleanup(() => {
      cancelled = true;
      cancelIdle(handle);
    });
  });

  function handleClick(e: MouseEvent) {
    e.stopPropagation();
    commands().onViewMermaid?.({
      chart: props.rawBlock.source,
      blockId: props.block.id,
      source: 'mermaid-block',
    });
  }

  return (
    <BlockFrame layout={props.block}>
      <div
        class={mermaidWrapper}
        role="button"
        aria-label="View Mermaid diagram"
        tabIndex={0}
        onClick={handleClick}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') handleClick(e as unknown as MouseEvent);
        }}
      >
        <Show
          when={svg()}
          fallback={
            <Show
              when={failed()}
              fallback={<span class={mermaidPlaceholder}>Mermaid diagram</span>}
            >
              <span class={mermaidError}>Couldn&apos;t render diagram</span>
            </Show>
          }
        >
          {(s) => <div innerHTML={s()} />}
        </Show>
      </div>
    </BlockFrame>
  );
}
