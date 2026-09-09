/**
 * Code — Solid component rendering a CodeLaidOut block.
 *
 * Renders plain text first (synchronous), then applies Shiki highlighting
 * asynchronously on an idle callback.
 *
 * Layout: BlockFrame positions the block (absolute, full-width, height from
 * layout). Inside it:
 *   - CopyButton: absolute top-right, stays pinned because it is a sibling of
 *     the scroll container (not inside it).
 *   - inner div: absolute inset-0, is the actual scroll+card element. It has
 *     no .pblock class, so overflow-x-auto wins without a specificity fight
 *     against block-frame's `overflow: visible` base rule.
 *
 * Shiki writes --shiki-light-bg / --shiki-dark-bg as inline custom properties
 * onto wrapperEl (the inner div), which carries the background Tailwind class.
 */

import { useCaches } from '@components/contexts/CachesContext';
import { useStreamAnimation } from '@components/contexts/StreamContext';
import { BlockFrame } from '@components/engine/block-frame';
import { cancelIdle, scheduleIdle } from '@components/engine/dom-utils';
import { CopyButton } from '@components/primitives/CopyButton';
import { applyTokenLines } from '@core/highlight/apply-tokens';
import type { CodeLaidOut } from '@core/layout/layout-types';
import type { CodeBlock } from '@core/markdown/document';
import { For, createEffect, createMemo, onCleanup } from 'solid-js';
import { codeLine, codeWrapper } from './code.css';
import { codeGroup } from '@components/primitives/copy-button.css';

export type CodeProps = {
  block: CodeLaidOut;
  rawBlock: CodeBlock;
};

export function Code(props: CodeProps) {
  const caches = useCaches();
  const streamAnim = useStreamAnimation();
  const lineElsMap: Map<number, HTMLElement> = new Map();
  let wrapperEl: HTMLElement | undefined;

  // Derive the block's position from its id (`${messageId}#${index}`).
  // The id is stable for the lifetime of this component.
  const blockIndex = Number(props.rawBlock.id.slice(props.rawBlock.id.lastIndexOf('#') + 1));

  // A block is settled when the message is not streaming (streamAnim is null
  // for committed messages), or when its index is below the settled-prefix
  // count. This memo flips false→true exactly once per block, so the highlight
  // effect runs a single time when the block crosses a safe parse boundary
  // (fence close or blank line), rather than waiting for the whole message.
  const settled = createMemo(
    () => !streamAnim?.streaming() || blockIndex < (streamAnim?.settledCount() ?? 0)
  );

  createEffect(() => {
    if (!wrapperEl) return;
    const lang = props.block.lang;
    if (!lang) return;

    // Defer highlighting until this specific block has settled into the stable
    // parse prefix. For committed messages streamAnim is null so settled() is
    // always true; for streaming messages it flips true once and stays true.
    if (!settled()) return;

    const code = props.rawBlock.code;

    // Synchronous fast-path on cache hit
    const cached = caches.peekHighlight(code, lang);
    if (cached) {
      const lineEls = Array.from(lineElsMap.values());
      if (cached.rootStyle) {
        for (const decl of cached.rootStyle.split(';')) {
          const colon = decl.indexOf(':');
          if (colon === -1) continue;
          const prop = decl.slice(0, colon).trim();
          const val = decl.slice(colon + 1).trim();
          if (prop) wrapperEl!.style.setProperty(prop, val);
        }
      }
      applyTokenLines(lineEls, cached.lines);
      return;
    }

    // Deferred path
    let cancelled = false;
    const handle = scheduleIdle(() => {
      if (cancelled) return;
      const hl = caches.highlight(code, lang);
      if (!hl || cancelled) return;
      const el = wrapperEl;
      if (!el) return;
      if (hl.rootStyle) {
        for (const decl of hl.rootStyle.split(';')) {
          const colon = decl.indexOf(':');
          if (colon === -1) continue;
          const prop = decl.slice(0, colon).trim();
          const val = decl.slice(colon + 1).trim();
          if (prop) el.style.setProperty(prop, val);
        }
      }
      const lineEls = Array.from(lineElsMap.values());
      applyTokenLines(lineEls, hl.lines);
    });

    onCleanup(() => {
      cancelled = true;
      cancelIdle(handle);
    });
  });

  return (
    <BlockFrame layout={props.block} class={codeGroup}>
      {/*
       * Pinned copy button — sibling of the scroll container so it stays
       * fixed at top-right regardless of horizontal scroll position.
       */}
      <CopyButton text={props.rawBlock.code} variant="overlay" label="Copy code" />

      {/*
       * Scroll + card container. absolute inset:0 makes its border-box equal
       * the frame box, preserving the reserved height arithmetic. Having no
       * .pblock class means overflow-x-auto wins without any specificity tie.
       *
       * Background is transparent so the block inherits the chat background.
       * Shiki writes --shiki-light-bg / --shiki-dark-bg onto wrapperEl as
       * inline custom properties; token spans get their color from code.css.ts.
       */}
      <div
        ref={(el) => {
          wrapperEl = el;
        }}
        class={codeWrapper}
      >
        <For each={props.block.lines}>
          {(line, i) => (
            <div
              ref={(el) => {
                lineElsMap.set(i(), el);
                onCleanup(() => lineElsMap.delete(i()));
              }}
              class={codeLine}
              style={{ top: `${line.top}px` }}
            >
              {line.text}
            </div>
          )}
        </For>
      </div>
    </BlockFrame>
  );
}
