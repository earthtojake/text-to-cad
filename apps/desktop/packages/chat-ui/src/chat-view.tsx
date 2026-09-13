/**
 * createChatView — imperative entry point for mounting a chat transcript view.
 *
 * Renders a Solid root into `parent`, wiring a ChatContext (global services)
 * and a ChatState (per-conversation transcript + parse caches) to the internal
 * ChatRoot component. Returns a ChatView handle with scroll/collapse/state APIs.
 *
 * Lifecycle:
 *   const view = createChatView({ context, state, parent });
 *   // state.transcript is already writable before view mounts
 *   view.setCommands({ onStop: ... });
 *   // After mount, view.composerSlot is set (if composer:'slot').
 *   // Use onViewMounted to react immediately:
 *   createChatView({ ..., onViewMounted: (v) => portal(v.composerSlot) });
 *   view.dispose(); // tears down Solid root; does NOT dispose context/state
 *
 * View state persistence:
 *   Collapse state, expandedUserId, scroll anchor, and measured row heights
 *   live in `state` (ChatState), not in the view. Disposing a view and
 *   creating a new one against the same ChatState (e.g. tab switch) restores
 *   all view state automatically without any host-side bookkeeping.
 *
 * The composer slot:
 *   When `composer === 'slot'`, ChatRoot renders a sticky bottom div. Its
 *   height is measured by an internal ResizeObserver that drives `padBottom`
 *   automatically. Use `view.composerSlot` (or `onViewMounted`) to portal a
 *   React composer into it.
 */

import { batch, createSignal } from 'solid-js';
import { render } from 'solid-js/web';
import type { ChatContext } from './chat-context';
import { ChatRoot } from './ChatRoot';
import type { ComposerPlacement, ComposerPlacementOptions, EngineControls } from './ChatRoot';
import type { ChatCommands, ScrollToItemOptions } from './commands';
import type { TranscriptTurn } from './model';
import type { ChatState, ScrollMode } from './state/chat-state';

export type { ComposerPlacement, ComposerPlacementOptions } from './ChatRoot';

export type ChatViewOptions = {
  /** Global services (theme, shared caches, measureEpoch). */
  context: ChatContext;
  /** Per-conversation state (transcript + parse caches). */
  state: ChatState;
  /** DOM element to render the Solid root into. */
  parent: HTMLElement;
  /**
   * Whether to render an internal composer slot.
   * - `'slot'`: sticky bottom slot; internal ResizeObserver drives padBottom.
   * - `'none'` (default): no slot; use `setContentPadding` externally.
   */
  composer?: 'slot' | 'none';
  /** Initial placement for the internal composer slot. Defaults to `'bottom'`. */
  composerPlacement?: ComposerPlacement;
  /**
   * When true, render an absolutely-positioned overlay slot above the
   * transcript/scroll but below the composer. Use `view.contentOverlay` to
   * portal loading/empty/disabled states into it.
   */
  contentOverlay?: boolean;
  stickToBottom?: boolean;
  pinUserMessages?: boolean;
  /** Extra class for the scroll container. */
  class?: string;
  /** Class for the centered content column. */
  contentClass?: string;
  /** Top padding baked into virtualizer coordinates. */
  padTop?: number;
  /** Bottom padding (ignored when `composer === 'slot'` — driven by ResizeObserver). */
  padBottom?: number;
  /** Initial command callbacks. Update later via `view.setCommands`. */
  commands?: ChatCommands;
  onReachStart?: () => void;
  onAtBottomChange?: (atBottom: boolean) => void;
  /**
   * Fired when the latest user message's viewport visibility changes.
   * See ChatRoot prop of the same name for full semantics.
   */
  onActiveUserMessageVisibilityChange?: (visible: boolean) => void;
  /**
   * Called once after the Solid root mounts (after ChatRoot.onMount).
   * At this point `view.composerSlot` is set and all controls are wired.
   */
  onViewMounted?: (view: ChatView) => void;
};

export type ChatView = {
  /**
   * The composer slot element (non-null only when `composer === 'slot'` and
   * after mount). Host should portal a React composer into this element.
   * Use `onViewMounted` to be notified when it becomes available.
   */
  readonly composerSlot: HTMLElement | null;
  /**
   * The hero slot element rendered above the composer in centered placement.
   * Host should portal empty-state copy into this element.
   */
  readonly heroSlot: HTMLElement | null;
  /**
   * The content overlay slot element (non-null only when `contentOverlay` is
   * true and after mount). Portal loading/empty/disabled overlay UI here.
   */
  readonly contentOverlay: HTMLElement | null;
  /** Replace command callbacks without remounting. */
  setCommands(commands: ChatCommands): void;
  /** Scroll to the top of the transcript. */
  scrollToTop(opts?: { behavior?: ScrollBehavior }): void;
  /** Scroll to the bottom of the transcript. */
  scrollToBottom(opts?: { behavior?: ScrollBehavior }): void;
  /**
   * Scroll to the row for the given item id.
   * Best-effort precise: target settles within a frame or two if off-screen.
   */
  scrollToItem(id: string, opts?: ScrollToItemOptions): void;
  /**
   * Prepend older history items without losing scroll position.
   * Pair with `onReachStart` for infinite-scroll pagination.
   */
  loadOlder(turns: TranscriptTurn[]): void;
  /**
   * Toggle the collapsed state of an item by id.
   * Primarily for perf benchmarks; prefer user-driven collapse in production.
   */
  toggleCollapsed(id: string): void;
  /**
   * Update canvas padding without remounting.
   * `bottom` is ignored when `composer === 'slot'` (driven by internal ResizeObserver).
   */
  setContentPadding(p: { top?: number; bottom?: number }): void;
  /**
   * Declaratively set the scroll intent. ChatRoot projects the intent onto the
   * DOM immediately (flush + scrollTop write) and persists it in the current
   * ChatState so it survives subsequent tab switches.
   *
   * `tail`    — re-pin to newest content on every content change.
   * `anchor`  — keep the given item's edge at the given viewport offset.
   *             Use `pinTopMode(itemId)` to hold a row flush at the top.
   *
   * Use the `tailMode()` and `pinTopMode(itemId)` helpers from `@emdash/chat-ui`
   * rather than constructing objects inline.
   */
  setScrollMode(mode: ScrollMode): void;
  /** Move the internal composer slot without remounting portal contents. */
  setComposerPlacement(placement: ComposerPlacement, opts?: ComposerPlacementOptions): void;
  /**
   * Replace the ChatState this view renders without tearing down the Solid root
   * (Monaco/CodeMirror model-swap pattern). Snapshots the outgoing model's
   * heightmap into the old state, then loads the incoming model's ScrollMode
   * intent and projects it. Safe to call while the outgoing state is streaming.
   *
   * No-op when `state` is already the current model.
   */
  setModel(state: ChatState): void;
  /** Tear down the Solid root. Does NOT dispose context or state. */
  dispose(): void;
};

/**
 * Mount a chat transcript view into `parent` and return a ChatView handle.
 */
export function createChatView(opts: ChatViewOptions): ChatView {
  const [padTop, setPadTop] = createSignal(opts.padTop ?? 0);
  const [padBottom, setPadBottom] = createSignal(opts.padBottom ?? 0);
  const [commands, setCommandsSignal] = createSignal<ChatCommands>(opts.commands ?? {});
  // Hold the active ChatState in a signal so view.setModel() can swap models
  // reactively without tearing down the Solid root. Use a function form of
  // setCurrentModel to prevent Solid from treating the ChatState as a factory.
  const [currentModel, setCurrentModel] = createSignal<ChatState>(opts.state);

  const controls: EngineControls = {
    scrollToTop: () => {},
    scrollToBottom: () => {},
    scrollToItem: () => {},
    loadOlder: () => {},
    onMounted() {
      opts.onViewMounted?.(view);
    },
  };

  const onReachStart = opts.onReachStart ? () => opts.onReachStart?.() : undefined;
  const onAtBottomChange = opts.onAtBottomChange
    ? (b: boolean) => opts.onAtBottomChange?.(b)
    : undefined;
  const onActiveUserMessageVisibilityChange = opts.onActiveUserMessageVisibilityChange
    ? (v: boolean) => opts.onActiveUserMessageVisibilityChange?.(v)
    : undefined;

  // dispose is assigned after render() returns.
  let solidDispose: (() => void) | null = null;

  const view: ChatView = {
    get composerSlot() {
      return controls.composerSlot ?? null;
    },
    get heroSlot() {
      return controls.heroSlot ?? null;
    },
    get contentOverlay() {
      return controls.contentOverlay ?? null;
    },
    setCommands(c) {
      setCommandsSignal(c);
    },
    scrollToTop(o) {
      controls.scrollToTop(o);
    },
    scrollToBottom(o) {
      controls.scrollToBottom(o);
    },
    scrollToItem(id, o) {
      controls.scrollToItem(id, o);
    },
    loadOlder(items) {
      controls.loadOlder(items);
    },
    toggleCollapsed(id) {
      controls.toggleCollapsed?.(id);
    },
    setContentPadding(p) {
      batch(() => {
        if (p.top !== undefined) setPadTop(p.top);
        if (p.bottom !== undefined) setPadBottom(p.bottom);
      });
    },
    setScrollMode(m) {
      controls.setScrollMode?.(m);
    },
    setComposerPlacement(placement, opts) {
      controls.setComposerPlacement?.(placement, opts);
    },
    setModel(newState) {
      if (newState !== currentModel()) {
        // Use the function form so Solid does not treat ChatState as a factory.
        setCurrentModel(() => newState);
      }
    },
    dispose() {
      solidDispose?.();
    },
  };

  solidDispose = render(
    () => (
      <ChatRoot
        context={opts.context}
        state={currentModel}
        stickToBottom={opts.stickToBottom}
        class={opts.class}
        contentClass={opts.contentClass}
        padTop={padTop}
        padBottom={padBottom}
        commands={commands}
        onReachStart={onReachStart}
        onAtBottomChange={onAtBottomChange}
        onActiveUserMessageVisibilityChange={onActiveUserMessageVisibilityChange}
        controls={controls}
        pinUserMessages={opts.pinUserMessages}
        composer={opts.composer}
        composerPlacement={opts.composerPlacement}
        contentOverlay={opts.contentOverlay}
      />
    ),
    opts.parent
  );

  return view;
}
