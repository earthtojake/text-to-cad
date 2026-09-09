/**
 * chat-transcript.tsx — React adapter for @emdash/chat-ui.
 *
 * Renderer-local copy of the @emdash/ui ChatTranscript wrapper, importing
 * createChatView and types directly from @emdash/chat-ui. This keeps ChatComposer
 * as the only @emdash/ui runtime import consumed by the desktop renderer.
 *
 * Uses React.createElement (no JSX) to avoid dual-JSX-runtime conflicts.
 * Creates a ChatView into the container div on mount and disposes on unmount.
 *
 * context + state must be created by the host via createChatContext /
 * createChatState before passing them in. This mirrors the CodeMirror
 * EditorState/EditorView split: the host owns the model (ChatState), this
 * component owns the DOM view.
 *
 * padTop is accepted as a prop and pushed reactively through setContentPadding.
 * padBottom is intentionally omitted: when `composer` is `'slot'`, ChatView's
 * internal ResizeObserver drives padBottom automatically. For non-slot usage,
 * call view.setContentPadding({ bottom: ... }) directly.
 *
 * commands / onReachStart / onAtBottomChange are pushed reactively so inline
 * callbacks do not go stale after React re-renders.
 */

import {
  type ChatCommands,
  type ChatContext,
  type ChatState,
  type ChatView,
  type ChatViewOptions,
  type TranscriptTurn,
} from '@emdash/chat-ui';
import { createElement, useEffect, useRef } from 'react';
import { getChatUiRuntime } from './chat-ui-runtime';

export type ChatTranscriptProps = Pick<
  ChatViewOptions,
  | 'stickToBottom'
  | 'pinUserMessages'
  | 'composer'
  | 'composerPlacement'
  | 'contentOverlay'
  | 'class'
  | 'contentClass'
  | 'onReachStart'
  | 'onAtBottomChange'
  | 'onActiveUserMessageVisibilityChange'
> & {
  /** Global services singleton shared across conversations. */
  context: ChatContext;
  /** Per-conversation state (transcript + parse caches). */
  state: ChatState;
  /** Called once after the Solid root is mounted with the chat view handle. */
  onReady?: (view: ChatView) => void;
  style?: React.CSSProperties;
  className?: string;
  /**
   * Top padding (px) reserved inside the canvas for a pinned header. Pushed
   * reactively via setContentPadding so it can change without remounting.
   */
  padTop?: number;
  /**
   * Command callbacks invoked by user interactions inside the transcript.
   * Pushed reactively so inline callbacks are never stale.
   */
  commands?: ChatCommands;
};

export function ChatTranscript(props: ChatTranscriptProps): React.ReactElement {
  const ref = useRef<HTMLDivElement>(null);
  const propsRef = useRef(props);
  propsRef.current = props;

  const viewRef = useRef<ChatView | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const p = propsRef.current;
    const view = getChatUiRuntime().createChatView({
      context: p.context,
      state: p.state,
      parent: ref.current,
      composer: p.composer,
      composerPlacement: p.composerPlacement,
      contentOverlay: p.contentOverlay,
      stickToBottom: p.stickToBottom,
      pinUserMessages: p.pinUserMessages,
      class: p.class,
      contentClass: p.contentClass,
      commands: p.commands ?? {},
      padTop: p.padTop,
      // Thread stable wrappers that read from propsRef at call time — never stale.
      onReachStart: p.onReachStart ? () => propsRef.current.onReachStart?.() : undefined,
      onAtBottomChange: p.onAtBottomChange
        ? (b: boolean) => propsRef.current.onAtBottomChange?.(b)
        : undefined,
      onActiveUserMessageVisibilityChange: p.onActiveUserMessageVisibilityChange
        ? (v: boolean) => propsRef.current.onActiveUserMessageVisibilityChange?.(v)
        : undefined,
      onViewMounted: (v) => propsRef.current.onReady?.(v),
    });
    viewRef.current = view;

    return () => {
      view.dispose();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Swap the underlying ChatState when props.state identity changes (setModel path).
  // The view handle, composer slot, and commands remain stable across swaps.
  useEffect(() => {
    viewRef.current?.setModel(props.state);
  }, [props.state]);

  // Push top padding updates reactively.
  useEffect(() => {
    viewRef.current?.setContentPadding({ top: props.padTop });
  }, [props.padTop]);

  // Push command callbacks reactively so inline functions are never stale.
  useEffect(() => {
    if (props.commands !== undefined) {
      viewRef.current?.setCommands(props.commands);
    }
  }, [props.commands]);

  return createElement('div', {
    ref,
    style: { height: '100%', ...props.style },
    className: props.className,
  });
}

// Re-export imperative types so consumers don't need to import from @emdash/chat-ui directly.
export type {
  ChatView,
  ChatCommands,
  ChatViewCommand,
  ChatViewCommandId,
  ScrollToItemOptions,
  ChatHighlighter,
  HighlightResult,
  CodeToken,
  MentionProvider,
  ChatContext,
  ChatState,
  TranscriptTurn,
} from '@emdash/chat-ui';
export type LoadOlderFn = (turns: TranscriptTurn[]) => void;
