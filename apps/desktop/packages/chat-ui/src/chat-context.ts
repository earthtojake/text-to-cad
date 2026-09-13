/**
 * ChatContext — global services singleton for @emdash/chat-ui.
 *
 * Holds everything that is shared across all conversations and views:
 *   - Resolved theme + config (typography constants for measurement)
 *   - Shiki highlighter (expensive one-time init)
 *   - Content-addressed caches (highlight / diff / mermaid / richInline)
 *   - measureEpoch signal (bumped on font load / theme change to invalidate geometry)
 *   - mentionProvider (synchronous @-mention resolver)
 *
 * Lifetime: process-long (singleton). Dispose only when tearing down the app.
 *
 * Usage:
 *   const ctx = createChatContext({ theme, highlighter });
 *   const state = createChatState(ctx);
 *   const view  = createChatView({ context: ctx, state, parent });
 */

import { createRoot, createSignal } from 'solid-js';
import type { SharedCaches } from './core/caches';
import { createSharedCaches } from './core/caches';
import type { ChatConfig } from './core/config';
import { DEFAULT_CONFIG, buildChatTheme } from './core/config';
import type { ChatHighlighter } from './core/highlight/highlighter';
import type { CommandProvider } from './core/markdown/command-provider';
import type { MentionProvider } from './core/markdown/mention-provider';
import { registerFontsReadyClear } from './core/measure/pretext-cache';
import type { ChatTheme } from './core/theme';

export type ChatContextOptions = {
  /**
   * Full resolved theme. When omitted, `config` is used to derive one.
   * Color changes are free (CSS-variable themed). Typography/font changes must
   * bump measureEpoch — call `ctx.bumpEpoch()` after updating theme.
   */
  theme?: ChatTheme;
  /**
   * Chat configuration (typography, chip geometry). Ignored when `theme` is set.
   * Changing this after creation requires bumping `ctx.bumpEpoch()`.
   */
  config?: ChatConfig;
  /**
   * Optional syntax-highlighting adapter.
   * When omitted the bundled default highlighter is used.
   */
  highlighter?: ChatHighlighter;
  /**
   * Optional synchronous @-mention metadata resolver.
   * Threaded into parse caches so @-token spans render as pills.
   */
  mentionProvider?: MentionProvider;
  /**
   * Optional synchronous /-command metadata resolver.
   * Threaded into parse caches so /command spans render as chips.
   */
  commandProvider?: CommandProvider;
};

export type ChatContext = {
  /** Resolved theme (typography constants drive measurement geometry). */
  readonly theme: ChatTheme;
  /** Chat configuration that produced the theme. */
  readonly config: ChatConfig;
  /** Optional mention provider threaded into parse caches. */
  readonly mentionProvider: MentionProvider | undefined;
  /** Optional command provider threaded into parse caches. */
  readonly commandProvider: CommandProvider | undefined;
  /** Shared content-addressed caches (highlight / diff / mermaid / richInline). */
  readonly sharedCaches: SharedCaches;
  /**
   * Reactive accessor for the measurement epoch.
   * Read inside Solid reactive contexts (createMemo, JSX) to re-measure
   * when fonts load or theme typography changes.
   */
  readonly measureEpoch: () => number;
  /**
   * Bump the measurement epoch, invalidating all per-block geometry caches.
   * Call after fonts load (handled automatically) or after a typography change.
   */
  bumpEpoch(): void;
  /** Dispose the context's reactive root. Safe to call after all views are disposed. */
  dispose(): void;
};

/**
 * Create a ChatContext singleton.
 *
 * `registerFontsReadyClear` is called once: when the named fonts load,
 * `clearTextMeasure()` flushes pretext's glyph cache and `bumpEpoch()`
 * invalidates all block geometry caches.
 */
export function createChatContext(opts: ChatContextOptions = {}): ChatContext {
  const config = opts.config ?? DEFAULT_CONFIG;
  const theme = opts.theme ?? buildChatTheme(config);
  const sharedCaches = createSharedCaches(opts.highlighter);

  let measureEpoch!: () => number;
  let bumpEpoch!: () => void;
  let disposeRoot!: () => void;

  createRoot((dispose) => {
    disposeRoot = dispose;
    const [epoch, setEpoch] = createSignal(0);
    measureEpoch = epoch;
    bumpEpoch = () => setEpoch((e) => e + 1);
  });

  let disposed = false;

  registerFontsReadyClear(() => {
    if (disposed) return;
    sharedCaches.clearTextMeasure();
    bumpEpoch();
  });

  return {
    theme,
    config,
    mentionProvider: opts.mentionProvider,
    commandProvider: opts.commandProvider,
    sharedCaches,
    measureEpoch,
    bumpEpoch,
    dispose() {
      disposed = true;
      disposeRoot();
    },
  };
}
