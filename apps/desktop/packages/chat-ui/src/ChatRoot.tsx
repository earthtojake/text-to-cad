/**
 * ChatRoot — the Solid component that implements the chat transcript renderer.
 *
 * Architecture (ChatContext / ChatState / ChatView split):
 *   - ChatContext is passed as `props.context`: provides theme, shared caches,
 *     measureEpoch, and the Shiki highlighter.
 *   - ChatState is passed as `props.state`: provides transcript + parse caches.
 *   - ChatState is passed as `props.state`: provides transcript, parse caches,
 *     and per-conversation view state (viewState, expandedUserId, scroll anchor,
 *     heightmap). These survive view dispose/recreate (e.g. tab switches).
 *   - ChatRoot owns the virtualizer, frame scheduler, and tween registry.
 *
 * Scheduler hardening (aligned with CodeMirror's measure cycle):
 *   - Created eagerly (before `onMount`) so tween arming never hits a null ref.
 *   - try/catch around phases; re-arm always executes in `finally`.
 *   - Visibility watchdog: `forceReconcile()` on visibilitychange and on attach.
 *
 * Width invalidation (A6 — per-row dirty via fingerprint):
 *   - clearTextMeasure() is NOT called on width change. The per-block fingerprint
 *     (measureEpoch|width|collapsed) already handles width invalidation.
 *   - prepareRichInline is width-independent (intrinsic glyph widths), so it
 *     is retained in SharedCaches without flushing on resize.
 *
 * Composer slot (A7):
 *   - When `composer === 'slot'`, ChatRoot renders a sticky bottom slot inside
 *     outerClip. An internal ResizeObserver drives `padBottom` automatically.
 *   - `controls.composerSlot` exposes the slot HTMLElement so the host can
 *     portal a React composer into it.
 */

import {
  For,
  Show,
  createEffect,
  createMemo,
  createSignal,
  on,
  onCleanup,
  onMount,
  untrack,
  useContext,
} from 'solid-js';
import type { ChatContext } from './chat-context';
import type { ChatCommands, ScrollToItemOptions } from './commands';
import { CachesContext } from './components/contexts/CachesContext';
import { CommandsContext } from './components/contexts/CommandsContext';
import { DebugContext } from './components/contexts/debug-context';
import { ThemeContext } from './components/contexts/ThemeContext';
import { TurnStateContext } from './components/contexts/TurnStateContext';
import { createFrameScheduler } from './components/engine/frame-scheduler';
import { createTweenRegistry } from './components/engine/tween-registry';
import { SEGMENTERS, UNIT_REGISTRY } from './components/engine/unit-registry';
import { UnitRow } from './components/engine/UnitRow';
import { PinnedUserMessage } from './components/rows/message/PinnedUserMessage';
import type { ChatCaches } from './core/caches';
import type { ThemeVarKey } from './core/config';
import type { MeasureCtx } from './core/define';
import { genericEstimate } from './core/layout/generic-estimate';
import { STICK_THRESHOLD_PX } from './core/stick-to-bottom';
import { unitReservedHeight } from './core/units';
import { Virtualizer } from './core/virtualizer';
import type { ChatItem, ChatMessage, TranscriptTurn } from './model';
import type { ChatState, ScrollMode } from './state/chat-state';
import { flattenTier, makeUnitsView, collectUserTurnUnits } from './state/flatten';
import type { UnitsView } from './state/flatten';
import type { LayoutSnapshot, PinSnapshot } from './state/geometry';
import { samePin, sameRange } from './state/geometry';
import {
  canvas,
  composerSlotAnimatingClass,
  composerSlotCenteredClass,
  composerSlotClass,
  composerSlotInnerBottomClass,
  composerSlotInnerCenteredClass,
  composerSlotInnerClass,
  contentOverlaySlotClass,
  defaultContentClass,
  heroSlotClass,
  heroSlotHiddenClass,
  heroSlotVisibleClass,
  outerClip,
  pinnedOverlay,
  pinnedOverlayColumn,
  scrollContainer,
  unitRowWrapper,
  widthProbeClass,
} from './chat-root.css';
import './chat-fonts.css';
import { vars } from './styles/theme.css';

// Centered content column. The scroll container stays full width (so the
// scrollbar sits at the viewport edge) while rows are measured and laid out
// against this capped, centered canvas — matching the desktop composer width.
const DEFAULT_CONTENT_CLASS = defaultContentClass;

// Vertical breathing room added above the first row and below the last row.
const TRANSCRIPT_VERTICAL_PADDING = 32;

// Symmetric overscan used when idle or velocity unknown
const OVERSCAN_BASE = 12;
// Leading buffer in the direction of scroll; trailing buffer behind it
const OVERSCAN_LEADING = 20;
const OVERSCAN_TRAILING = 8;

// Idle-time prefetch: how many rows beyond the overscan window to pre-measure
// during requestIdleCallback slices. Rows ahead in scroll direction get a
// larger budget; behind get a smaller one.
const PREFETCH_AHEAD = 40;
const PREFETCH_BEHIND = 20;
// Stop the current idle slice if less than this many ms remain (leaves headroom
// for the browser's own idle tasks).
const PREFETCH_MIN_REMAINING_MS = 3;

// onReachStart fires when the top row is visible and scrollTop is within this
// threshold of the canvas top. Debounced: only fires once until reset.
const REACH_START_THRESHOLD_PX = 200;

// Maximum absolute scrollTop delta that can originate from a writeScrollTop
// self-write (sub-pixel / device-pixel rounding). Any delta larger than this
// is classified as a real user scroll and updates lastUserScrollAt.
// Keeping it tight (0.5 px) avoids suppressing short-distance programmatic
// adjustments that should also be treated as self-writes.
const USER_SCROLL_EPSILON = 0.5;

// After a user/smooth scroll, suppress anchor projection until the gesture has
// been quiet this long. Must be comfortably longer than one rAF frame (~16 ms)
// so a momentary hold or an inter-event gap mid-drag does not open the gate
// and let projectAnchor jump the thumb forward. Tunable.
const SCROLL_SETTLE_MS = 120;

export type ComposerPlacement = 'bottom' | 'center';

export type ComposerPlacementOptions = {
  animate?: boolean;
};

function resolveComposerPlacement(
  value: ComposerPlacement | (() => ComposerPlacement) | undefined
): ComposerPlacement {
  return value === undefined ? 'bottom' : typeof value === 'function' ? value() : value;
}

function findLastUserMessageId(turns: readonly TranscriptTurn[]): string | null {
  for (let turnIndex = turns.length - 1; turnIndex >= 0; turnIndex--) {
    const turn = turns[turnIndex];
    for (let itemIndex = turn.items.length - 1; itemIndex >= 0; itemIndex--) {
      const item = turn.items[itemIndex];
      if (item.kind === 'message' && item.role === 'user') return item.id;
    }
  }
  return null;
}

// ── EngineControls ────────────────────────────────────────────────────────────

/**
 * Mutable holder populated by ChatRoot.onMount. createChatView creates an
 * instance and passes it to ChatRoot; the ChatView handle methods delegate to
 * it so callers never hold stale closures.
 */
export type EngineControls = {
  scrollToTop(opts?: { behavior?: ScrollBehavior }): void;
  scrollToBottom(opts?: { behavior?: ScrollBehavior }): void;
  scrollToItem(id: string, opts?: ScrollToItemOptions): void;
  loadOlder(turns: TranscriptTurn[]): void;
  /** Toggle collapse for an item by id (for view.toggleCollapsed). */
  toggleCollapsed?(id: string): void;
  /**
   * Reference to the composer slot element. Set by ChatRoot after mount when
   * `composer === 'slot'`. The host portals its React composer into this element.
   */
  composerSlot?: HTMLElement | null;
  /**
   * Reference to the hero slot element rendered above the composer in centered
   * placement. Hosts can portal empty-state copy into this element.
   */
  heroSlot?: HTMLElement | null;
  /**
   * Reference to the content overlay slot element. Set after mount when
   * `contentOverlay` is true. The host portals overlay content into it.
   */
  contentOverlay?: HTMLElement | null;
  /**
   * Declaratively set scroll intent; ChatRoot projects it immediately.
   * Wired by onMount; safe to call from outside the Solid reactive context.
   */
  setScrollMode?(mode: ScrollMode): void;
  /** Move the library-owned composer slot between supported placements. */
  setComposerPlacement?(placement: ComposerPlacement, opts?: ComposerPlacementOptions): void;
  /**
   * Called once at the end of ChatRoot's onMount, after all controls and
   * composerSlot are wired. Used by createChatView to fire onViewMounted.
   */
  onMounted?(): void;
};

// ── ChatRootProps ─────────────────────────────────────────────────────────────

export type ChatRootProps = {
  /** Global services: theme, shared caches, measureEpoch, highlighter. */
  context: ChatContext;
  /**
   * Per-conversation state: transcript + parse caches.
   * Accepts either a plain ChatState or a reactive accessor `() => ChatState`
   * (provided by createChatView for the setModel path).
   */
  state: ChatState | (() => ChatState);
  stickToBottom?: boolean;
  /** Extra classes for the full-width scroll container. */
  class?: string;
  /**
   * Classes for the centered content column. Defaults to a max-width column.
   * Rows are measured against this element's width, not the scroll container.
   */
  contentClass?: string;
  /**
   * Enable the layout-boundary debug overlay on every block and row.
   */
  debug?: boolean;
  /**
   * Vertical padding reserved at the top of the canvas (px). Baked into the
   * virtualizer coordinate space — not CSS padding — so scroll math stays exact.
   * Accepts a static number or a reactive accessor.
   */
  padTop?: number | (() => number);
  /**
   * Vertical padding reserved at the bottom of the canvas (px). The last row
   * rests above this space, keeping content clear of a floating composer.
   * When `composer === 'slot'` this is driven automatically by the slot's
   * ResizeObserver; pass a static value only for non-slot hosts.
   * Accepts a static number or a reactive accessor.
   */
  padBottom?: number | (() => number);
  /**
   * Reactive accessor returning the current ChatCommands. Provided by
   * createChatView via a signal so setCommands can update them without remounting.
   */
  commands?: () => ChatCommands;
  /** Fired when the user scrolls near the top and the engine has run out of history. */
  onReachStart?: () => void;
  /** Fired when the "at bottom" sticky state changes. */
  onAtBottomChange?: (atBottom: boolean) => void;
  /**
   * Fired when the latest user message's viewport visibility changes.
   * `true`  = the message body (or any part of it) intersects the viewport.
   * `false` = the message has scrolled fully out of view in either direction.
   * Useful for gating a scroll-to-bottom affordance on the most semantically
   * meaningful scroll position rather than the generic at-bottom threshold.
   */
  onActiveUserMessageVisibilityChange?: (visible: boolean) => void;
  /**
   * Mutable holder that ChatRoot.onMount populates with imperative scroll
   * methods and the composer slot reference.
   */
  controls?: EngineControls;
  /**
   * When true, the active turn's user message is pinned to the top of the
   * transcript while scrolling. Defaults to false.
   */
  pinUserMessages?: boolean;
  /**
   * Controls whether ChatRoot renders an internal composer slot.
   * - `'slot'`: render a sticky bottom slot; internal ResizeObserver drives padBottom.
   * - `'none'` (default): no slot; host controls padBottom externally.
   */
  composer?: 'slot' | 'none';
  /**
   * Initial or reactive composer placement when `composer === 'slot'`.
   * Defaults to `'bottom'`.
   */
  composerPlacement?: ComposerPlacement | (() => ComposerPlacement);
  /**
   * When true, render an absolutely-positioned overlay slot above the
   * transcript/scroll but below the composer (z-index 15). Hosts portal
   * loading/empty/disabled states into `controls.contentOverlay`.
   */
  contentOverlay?: boolean;
};

// ── ChatRoot ──────────────────────────────────────────────────────────────────

export function ChatRoot(props: ChatRootProps) {
  // Normalize state prop to an accessor so ChatRoot is reactive when the host
  // swaps models via view.setModel(). Plain ChatState objects (the common path)
  // are wrapped in a stable closure that never changes its value.
  const state: () => ChatState =
    typeof props.state === 'function' ? props.state : () => props.state as ChatState;

  // Assemble the full ChatCaches bundle from context (shared) + state (parse).
  // Leaf components (Code.tsx, Diff.tsx) consume this via useCaches().
  // Memo so it recomputes when the model swaps (new parseCaches).
  const caches = createMemo<ChatCaches>(() => ({
    ...props.context.sharedCaches,
    ...state().parseCaches,
  }));

  // Theme and CSS vars — set once at creation time. Color theme changes are
  // free (CSS-variable themed). Typography changes require bumping measureEpoch.
  const resolved = props.context.theme;
  const scrollElStyle = (() => {
    const tv = resolved.themeVars;
    const style: Record<string, string> = {};
    for (const k of Object.keys(tv) as ThemeVarKey[]) {
      const ref = String(vars[k as keyof typeof vars]);
      style[ref.startsWith('var(') ? ref.slice(4, -1) : ref] = tv[k];
    }
    return style;
  })();
  const theme = () => resolved;
  const contentClass = () => props.contentClass ?? DEFAULT_CONTENT_CLASS;
  const commands = () => props.commands?.() ?? {};
  const [composerPlacement, setComposerPlacementSignal] = createSignal<ComposerPlacement>(
    resolveComposerPlacement(props.composerPlacement)
  );
  const [composerAnimating, setComposerAnimating] = createSignal(false);
  const effectiveComposerPlacement = () =>
    props.composer === 'slot' ? composerPlacement() : 'bottom';

  const padTop = () => {
    const v = props.padTop;
    return (v === undefined ? 0 : typeof v === 'function' ? v() : v) + TRANSCRIPT_VERTICAL_PADDING;
  };

  // padBottom signal: either driven by the composer slot ResizeObserver (when
  // composer === 'slot') or by the external padBottom prop.
  // TRANSCRIPT_VERTICAL_PADDING is added on both paths so there is always
  // 32px of breathing room below the last row.
  const [slotPadBottom, setSlotPadBottom] = createSignal(0);
  const padBottom = () => {
    if (props.composer === 'slot') return slotPadBottom() + TRANSCRIPT_VERTICAL_PADDING;
    const v = props.padBottom;
    return (v === undefined ? 0 : typeof v === 'function' ? v() : v) + TRANSCRIPT_VERTICAL_PADDING;
  };

  const inheritedDebug = useContext(DebugContext);
  const debugValue = () => props.debug ?? inheritedDebug();

  // View state — owned by ChatState so it persists across view remounts.
  // All three are accessor functions so they always target the CURRENT model.
  const viewState = () => state().viewState;
  const expandedUserId = () => state().expandedUserId.get();
  const setExpandedUserId = (id: string | null) => state().expandedUserId.set(id);

  let scrollEl: HTMLDivElement | undefined;
  let canvasEl: HTMLDivElement | undefined;
  let outerEl: HTMLDivElement | undefined;
  // Zero-height probe that carries contentClass; the width ResizeObserver
  // targets this so it only fires on genuine layout-width changes.
  let widthProbeEl: HTMLDivElement | undefined;
  let composerSlotLayerEl: HTMLDivElement | undefined;
  let heroSlotEl: HTMLElement | undefined;
  let composerSlotEl: HTMLElement | undefined;
  let contentOverlaySlotEl: HTMLElement | undefined;
  const virt = new Virtualizer();
  // Visible row wrapper elements keyed by unit index.
  const rowEls = new Map<number, HTMLDivElement>();

  const [totalHeight, setTotalHeight] = createSignal(0);
  const [scrollVelocity, setScrollVelocity] = createSignal(0);
  const [viewHeight, setViewHeight] = createSignal(600);
  const [containerWidth, setContainerWidth] = createSignal(0);
  const [contentColumnLeft, setContentColumnLeft] = createSignal(0);

  const updateContentColumnGeometry = () => {
    if (!widthProbeEl || !outerEl) return;
    const probeRect = widthProbeEl.getBoundingClientRect();
    const outerRect = outerEl.getBoundingClientRect();
    if (probeRect.width <= 0) return;
    setContainerWidth(probeRect.width);
    setContentColumnLeft(probeRect.left - outerRect.left);
  };

  const updateSlotPadBottom = () => {
    if (props.composer !== 'slot' || effectiveComposerPlacement() === 'center') {
      setSlotPadBottom(0);
      return;
    }
    setSlotPadBottom(composerSlotEl?.getBoundingClientRect().height ?? 0);
  };

  const setComposerPlacement = (
    placement: ComposerPlacement,
    opts: ComposerPlacementOptions = {}
  ) => {
    if (props.composer !== 'slot') {
      setComposerPlacementSignal(placement);
      setSlotPadBottom(0);
      return;
    }

    const current = untrack(composerPlacement);
    if (current === placement) {
      updateSlotPadBottom();
      return;
    }

    const first = composerSlotEl?.getBoundingClientRect();
    setComposerPlacementSignal(placement);
    updateSlotPadBottom();

    if (!opts.animate || !composerSlotLayerEl || !composerSlotEl || !first) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;

    const last = composerSlotEl.getBoundingClientRect();
    const dx = first.left - last.left;
    const dy = first.top - last.top;
    if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;

    const layer = composerSlotLayerEl;
    setComposerAnimating(false);
    layer.style.transition = 'none';
    layer.style.transform = `translate(${dx}px, ${dy}px)`;
    // Force layout so the inverted transform is committed before animating home.
    void layer.offsetHeight;
    layer.style.transition = '';
    setComposerAnimating(true);

    let done = false;
    const cleanup = () => {
      if (done) return;
      done = true;
      layer.removeEventListener('transitionend', cleanup);
      layer.style.transform = '';
      setComposerAnimating(false);
    };

    layer.addEventListener('transitionend', cleanup);
    window.setTimeout(cleanup, 560);
    requestAnimationFrame(() => {
      layer.style.transform = '';
    });
  };

  // measureEpoch comes from ChatContext so all views share one epoch signal.
  // When fonts load, ChatContext bumps it and all views re-measure.
  const measureEpoch = props.context.measureEpoch;

  createEffect(() => {
    if (typeof props.composerPlacement !== 'function') return;
    const next = props.composerPlacement();
    if (next !== composerPlacement()) {
      setComposerPlacement(next, { animate: false });
    }
  });

  createEffect(() => {
    effectiveComposerPlacement();
    updateSlotPadBottom();
  });

  const refreshTotal = () => {
    setTotalHeight(virt.total());
  };

  // ── Geometry shadow ───────────────────────────────────────────────────────
  //
  // activeTurnReserve: the min-height of the active turn's response region,
  // expressed as trailing canvas space. When the tail of content (from the last
  // user message to the end) is shorter than the viewport, the reserve expands
  // maxScrollTop so projectAnchor('anchor'/'top') can place the user message at the
  // top. As the agent streams a response, tailHeight grows, reserve shrinks,
  // and once the tail fills the viewport reserve is 0 (normal scrolling).
  //
  // INVARIANT: derives from virt.total() (real measured heights) and is added
  // only in contentH — never fed back into virt — so there is no feedback loop
  // and the heightmap is never polluted with reserve padding.
  //
  // Gated by pinUserMessages so views that don't need this behavior are unaffected.
  // lastUserUnitIdx() is memoized on transcript changes, not per streaming tick.
  const activeTurnReserve = () => {
    if (!props.pinUserMessages) return 0;
    const idx = lastUserUnitIdx();
    if (idx < 0) return 0;
    const tailHeight = totalHeight() - virt.top(idx);
    // Subtract padBottom (composer height + TRANSCRIPT_VERTICAL_PADDING) so the
    // reserve grants exactly enough room to bring the user message flush to the
    // top edge, not past it. Without this, a short agent response allows the
    // user message to over-scroll into blank space below the composer.
    return Math.max(0, viewHeight() - padBottom() - tailHeight);
  };

  const contentH = () => totalHeight() + padTop() + padBottom() + activeTurnReserve();
  const maxScrollTop = () => Math.max(0, contentH() - viewHeight());

  // ── Flat unit view (two-tier, incremental) ────────────────────────────────
  const segmentCtx = (active = false) => ({
    caches: caches(),
    expanded: (_id: string) => false,
    active,
    plan: () => state().session.state.plan,
    pendingToolCallIds: () => state().session.state.pendingToolCallIds,
    terminalOutput: (terminalId: string) => state().session.state.terminalOutput(terminalId),
  });

  let committedUnitsArr: ReturnType<typeof flattenTier> = [];
  // O(1) lookup: itemId -> index of the FIRST unit for that item in the
  // committed tier. Maintained in lock-step with committedUnitsArr. Active-tier
  // items are handled by a small scan in firstUnitIndexOf since activeTurn is
  // always short (≤ a handful of items per streaming turn).
  const committedIndexById = new Map<string, number>();
  let lastCommitted: readonly TranscriptTurn[] = [];
  // Identity of the model this effect last built from. A change signals a
  // view.setModel swap and drives the snapshot + incremental-cache reset.
  let lastState: ChatState | undefined;
  const [committedUnitsVersion, setCommittedUnitsVersion] = createSignal(0);
  // Stable empty array passed to makeUnitsView when we need a committed-only
  // view. Must not change identity so memos don't re-run on each access.
  const NO_ACTIVE_UNITS: ReturnType<typeof flattenTier> = [];

  // ── Committed-tier build + model-swap reset (single effect) ────────────────
  // This effect owns BOTH the incremental committed build and the model-swap
  // reset. They were previously split across two effects that relied on Solid
  // running them in creation order; that assumption is unsafe — Solid notifies
  // effects in observer (subscription) order, which shifts as each effect
  // re-subscribes to state() on every run. On a fast tab swap the reset could
  // run AFTER the rebuild and wipe the freshly built committedUnitsArr, leaving
  // an empty transcript until the next named event. Folding both into one
  // computation makes the ordering deterministic: on a state-identity change we
  // snapshot the outgoing model and clear the incremental cache first, then
  // rebuild from the incoming model — all within the same synchronous run.
  createEffect(() => {
    const s = state();
    const next = s.transcript.state.committedTurns;

    if (s !== lastState) {
      // Model swap: snapshot the outgoing model's heights while committedUnitsArr
      // and virt still reflect it, then clear the incremental cache so the build
      // below re-seeds from scratch for the incoming model.
      if (lastState) snapshotInto(lastState);
      committedUnitsArr = [];
      committedIndexById.clear();
      lastCommitted = [];
      lastState = s;
    }

    const prev = lastCommitted;
    const ctx = segmentCtx(false);

    if (
      next.length > prev.length &&
      (prev.length === 0 || next[prev.length - 1] === prev[prev.length - 1])
    ) {
      // Incremental append: only process the new tail.
      const tail = next.slice(prev.length);
      const prevKind =
        committedUnitsArr.length > 0
          ? committedUnitsArr[committedUnitsArr.length - 1].kind
          : undefined;
      const newUnits = flattenTier(tail, ctx, SEGMENTERS, UNIT_REGISTRY, prevKind);
      const base = committedUnitsArr.length;
      for (let j = 0; j < newUnits.length; j++) {
        const u = newUnits[j];
        if (u && !committedIndexById.has(u.itemId)) {
          committedIndexById.set(u.itemId, base + j);
        }
      }
      committedUnitsArr = [...committedUnitsArr, ...newUnits];
    } else {
      // Full rebuild (seed, prepend, or non-append structural change).
      committedUnitsArr = flattenTier(next, ctx, SEGMENTERS, UNIT_REGISTRY);
      committedIndexById.clear();
      for (let i = 0; i < committedUnitsArr.length; i++) {
        const u = committedUnitsArr[i];
        if (u && !committedIndexById.has(u.itemId)) {
          committedIndexById.set(u.itemId, i);
        }
      }
    }

    lastCommitted = next;
    setCommittedUnitsVersion((v) => v + 1);
  });

  const activeUnits = createMemo(() => {
    committedUnitsVersion();
    const at = state().transcript.state.activeTurnSnapshot;
    const pendingPrompt = state().session.state.pendingPrompt;
    if ((!at || at.items.length === 0) && !pendingPrompt)
      return [] as ReturnType<typeof flattenTier>;
    const prevKind =
      committedUnitsArr.length > 0
        ? committedUnitsArr[committedUnitsArr.length - 1].kind
        : undefined;
    const activeTurn =
      at ??
      ({
        id: `pending:${pendingPrompt!.id}:turn`,
        seq: 0,
        initiator: 'user',
        items: [
          {
            kind: 'message',
            id: pendingPrompt!.id,
            seq: 0,
            role: 'user',
            text: pendingPrompt!.text,
            attachments: pendingPrompt!.attachments,
          } as TranscriptTurn['items'][number],
        ],
      } satisfies TranscriptTurn);
    return flattenTier([activeTurn], segmentCtx(true), SEGMENTERS, UNIT_REGISTRY, prevKind);
  });

  let pendingPromptCommittedTurns = state().transcript.state.committedTurns;
  createEffect(() => {
    const s = state();
    const pendingPrompt = s.session.state.pendingPrompt;
    const committedTurns = s.transcript.state.committedTurns;
    const hasActiveTurn = s.transcript.state.activeTurnSnapshot !== null;
    if (pendingPrompt && (hasActiveTurn || committedTurns !== pendingPromptCommittedTurns)) {
      s.session.setPendingPrompt(null);
    }
    pendingPromptCommittedTurns = committedTurns;
  });

  const units = createMemo<UnitsView>(() => {
    committedUnitsVersion();
    return makeUnitsView(committedUnitsArr, activeUnits());
  });

  const userTopGap = UNIT_REGISTRY.message?.margin?.top ?? 8;

  // ── Write-phase-owned geometry output signals ─────────────────────────────
  // These are the ONLY write targets for the visible-row set and the pin
  // overlay. They are written exclusively by commit() in the write phase, using
  // sameRange / samePin equality guards so JSX reconciles only on actual changes.
  const [visible, setVisible] = createSignal<number[]>([], { equals: sameRange });
  const [pin, setPin] = createSignal<PinSnapshot | null>(null, { equals: samePin });

  // Shadow geometry captured at the START of each read phase (before any DOM
  // write). computeVisible/computePin consume these inside the write phase so
  // they never force a layout read in the middle of a write sequence.
  let shadowScrollTop = 0;
  let shadowViewHeight = 600;

  // needsProject: set by onHeightChanged / count-sync whenever geometry changes
  // mid-stream so that a single projectAnchor runs in the write phase instead
  // of one per measured row (the layout-thrash regression fix).
  let needsProject = false;

  // appliedTop: tracks the last translateY written for each row element.
  // commit() skips the DOM write when the value hasn't changed.
  const appliedTop = new Map<number, number>();

  // lastLayout: previous LayoutSnapshot so commit() can diff field-by-field.
  let lastLayout: LayoutSnapshot | null = null;

  // lastVisibleStart/End: mirrors of the last derived visible range, used by
  // the idle prefetch slice (which runs outside the reactive scheduler).
  let lastVisibleStart = 0;
  let lastVisibleEnd = -1;

  // ── Count sync effect ─────────────────────────────────────────────────────
  createEffect(() => {
    const us = units();
    const t = theme();
    untrack(() => {
      const estimateCtx = {
        theme: t,
        width: 0,
        isCollapsed: () => false,
        expanded: () => false,
        caches: caches(),
        measureEpoch: measureEpoch(),
        expandedId: expandedUserId(),
      };
      // lastWidth > 0 iff onCleanup wrote a snapshot on a prior dispose.
      // Skip the Map.get pass entirely on cold mounts (empty heightmap).
      const currentState = state();
      const hasHeightmapSnapshot = currentState.heightmap.lastWidth > 0;
      virt.setCount(us.length, (i) => {
        const u = us.at(i);
        if (!u) return 60;
        // Use the persisted measured height if available (avoids scrollbar drift
        // on remount). Falls back to the cheap estimate for rows never measured
        // or when the heightmap was seeded at a different container width
        // (the scroll anchor will still restore the correct position).
        if (hasHeightmapSnapshot) {
          const snapped = currentState.heightmap.get(u.id);
          if (snapped !== undefined) return snapped;
        }
        const unitDef = UNIT_REGISTRY[u.kind];
        const contentH =
          unitDef?.estimate?.(u.data, estimateCtx, unitDef.vars ?? {}) ??
          genericEstimate(u.data as unknown as ChatItem, estimateCtx);
        return unitReservedHeight(u, contentH);
      });
      refreshTotal();
      // Defer projection to the write phase: projectAnchor will fire once per
      // frame (not once per row) preventing layout thrashing on streaming updates.
      needsProject = true;
    });
  });

  // Width change: do NOT flush caches. The per-block fingerprint
  // (measureEpoch|width|collapsed) already handles width invalidation.
  // richInline cache is width-independent (intrinsic glyph widths).
  // measureEpoch bumps (on font load) invalidate everything globally.

  // ── Pinned user-message overlay ───────────────────────────────────────────
  // Tracks committedUnitsVersion only — not units() — so it does not recompute
  // on every streaming frame. collectUserTurnUnits only looks at committed items
  // by design (see flatten.test.ts "does not include activeTurn user messages"),
  // and committed units are always the [0, committedUnitsArr.length) prefix of
  // the full units() view, so the returned absolute indices remain valid.
  const userTurns = createMemo(() => {
    committedUnitsVersion();
    return collectUserTurnUnits(
      state().transcript.state.committedTurns,
      makeUnitsView(committedUnitsArr, NO_ACTIVE_UNITS)
    );
  });

  // ── Last user message unit index ──────────────────────────────────────────
  // Finds the first unit index (in the full units() view) for the last user-
  // role message. Scans activeTurn first so the reserve picks up the freshly-
  // sent message during streaming (ACP bundles the prompt + response into one
  // activeTurn), then falls back to committed. Used by reservedBottom below.
  //
  // Memoized on committedUnitsVersion + activeTurn identity so it does not
  // recompute on every streaming text patch (only on structural turn changes).
  const lastUserUnitIdx = createMemo(() => {
    committedUnitsVersion();
    const transcript = state().transcript.state;
    let targetId: string | null = null;

    // 1. Scan activeTurn backward for the latest user message.
    const active = transcript.activeTurnSnapshot;
    if (active) {
      for (let i = active.items.length - 1; i >= 0; i--) {
        const item = active.items[i];
        if (item && item.kind === 'message' && (item as ChatMessage).role === 'user') {
          targetId = item.id;
          break;
        }
      }
    }

    // 2. Fall back to the last committed user message.
    if (targetId === null) {
      targetId = findLastUserMessageId(transcript.committedTurns);
    }

    if (targetId === null) return -1;

    // 3. Map itemId to its first unit index via the O(1) committed map +
    //    O(activeTurn) scan — no full units() scan needed.
    return firstUnitIndexOf(targetId);
  });

  // ── Pure geometry compute functions (called from write phase only) ─────────
  //
  // These functions read virt, shadow values, and Solid signals lazily (signals
  // are never subscribed inside a rAF callback — they just return cached values).
  // They must NOT write any signals or DOM nodes.

  /**
   * Computes the list of unit indices that should be rendered, using the
   * direction-aware asymmetric overscan and the current shadow scroll geometry.
   */
  function computeVisible(): number[] {
    const st = shadowScrollTop;
    const vh = shadowViewHeight;
    const v = scrollVelocity();
    let before: number;
    let after: number;
    if (v > 0) {
      before = OVERSCAN_TRAILING;
      after = OVERSCAN_LEADING;
    } else if (v < 0) {
      before = OVERSCAN_LEADING;
      after = OVERSCAN_TRAILING;
    } else {
      before = OVERSCAN_BASE;
      after = OVERSCAN_BASE;
    }
    const { start, end } = virt.range(Math.max(0, st - padTop()), vh, before, after);
    const n = units().length;
    const visEnd = Math.min(end, n - 1);
    lastVisibleStart = start;
    lastVisibleEnd = visEnd;
    const arr: number[] = [];
    for (let i = start; i <= visEnd; i++) arr.push(i);
    return arr;
  }

  /**
   * Computes the pinned-header state for the given scroll top and pad top.
   * Returns null when pinUserMessages is off or no user message has scrolled
   * past the top of the viewport.
   */
  function computePin(st: number, pt: number): PinSnapshot | null {
    if (!props.pinUserMessages) return null;
    const committedTurns = userTurns();
    // Include the active-turn user message so it can pin to the top too.
    const activeIdx = lastUserUnitIdx();
    const turns =
      activeIdx >= 0 &&
      (committedTurns.length === 0 || activeIdx > committedTurns[committedTurns.length - 1])
        ? [...committedTurns, activeIdx]
        : committedTurns;
    if (turns.length === 0) return null;

    const pinLine = userTopGap;

    let lo = 0;
    let hi = turns.length - 1;
    let activePos = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (virt.top(turns[mid]) + pt < st + pinLine) {
        activePos = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }

    if (activePos < 0) return null;

    const activeUserIdx = turns[activePos];
    const nextUserIdx = turns[activePos + 1];
    let overlayH = 0;
    const us = units();
    const activeUnit = us.at(activeUserIdx);
    const activeItemId = activeUnit?.itemId;
    if (activeUnit && activeItemId) {
      for (let ui = activeUserIdx; ui < us.length; ui++) {
        const u = us.at(ui);
        if (!u || u.itemId !== activeItemId) break;
        overlayH += virt.size(ui);
      }
    }

    const nextUserViewportTop =
      nextUserIdx !== undefined ? virt.top(nextUserIdx) + pt - st : Infinity;
    const overlayTop = Math.min(0, nextUserViewportTop - overlayH - pinLine);

    return { itemId: activeItemId ?? '', activeUserIdx, overlayTop };
  }

  /**
   * Returns true if the latest user message's canvas block intersects the
   * current scroll viewport [st, st+vh]. Uses the same unit-block summation as
   * computePin. Called from writePhase using the frame's shadow geometry.
   */
  function computeActiveUserVisible(st: number, vh: number, pt: number): boolean {
    const idx = lastUserUnitIdx();
    if (idx < 0) return true; // no user message yet — nothing to chase
    const us = units();
    const itemId = us.at(idx)?.itemId;
    if (!itemId) return true;
    let height = 0;
    for (let ui = idx; ui < us.length; ui++) {
      const u = us.at(ui);
      if (!u || u.itemId !== itemId) break;
      height += virt.size(ui);
    }
    const top = virt.top(idx) + pt;
    const bottom = top + height;
    // Visible if the block intersects the viewport [st, st+vh].
    return top < st + vh && bottom > st;
  }

  // ── Scroll intent (ScrollMode) ────────────────────────────────────────────
  //
  // A declarative intent loaded from ChatState on mount/swap and persisted back
  // ── Scroll anchor (event-sourced intent) ─────────────────────────────────
  //
  // `anchor` is the single source of truth for scroll intent. It changes only
  // on named events: user scroll (readPhase), expand/collapse, send, host
  // setScrollMode, scrollToBottom/scrollToItem. It is NEVER re-derived from
  // geometry on idle frames — that feedback loop is what caused scroll jumps.
  //
  // `expectedScrollTop` tracks the last value we wrote so readPhase can tell
  // a real user scroll (st !== expected) from an idle frame or our own write
  // (st === expected). Deterministic; replaces the old microtask-fragile counter.

  // Structural equality for the anchor signal. Avoids JSON.stringify allocations
  // on every setAnchor call (which happens on every user scroll tick).
  const sameScrollMode = (a: ScrollMode, b: ScrollMode): boolean => {
    if (a.kind !== b.kind) return false;
    if (a.kind === 'anchor' && b.kind === 'anchor') {
      return a.itemId === b.itemId && a.edge === b.edge && a.offset === b.offset;
    }
    return true; // both 'tail'
  };

  // Seeded from the current model's persisted intent (may be default 'tail').
  const [anchor, setAnchorSignal] = createSignal<ScrollMode>(untrack(state).scroll.get(), {
    equals: sameScrollMode,
  });

  // Persist intent to ChatState and update the local signal atomically.
  const setAnchor = (m: ScrollMode) => {
    setAnchorSignal(m);
    state().scroll.set(m);
  };

  // Last scrollTop we wrote. Seeded to 0; adopted from browser-clamped value
  // after each write so clamped positions are never counted as user movement.
  let expectedScrollTop = 0;

  const writeScrollTop = (top: number) => {
    if (!scrollEl) return;
    // Clamp arithmetically: projectAnchor already wrote canvasEl.style.height =
    // contentH() before calling us, so maxScrollTop() matches what the browser
    // would compute. Avoiding the read-back (scrollEl.scrollTop after the write)
    // eliminates the forced layout reflow that the read-back caused. Safe because
    // USER_SCROLL_EPSILON filters any sub-pixel divergence in readPhase.
    const clamped = Math.max(0, Math.min(top, maxScrollTop()));
    scrollEl.scrollTop = clamped;
    expectedScrollTop = clamped;
    // Arm the scheduler so the write phase re-derives the visible set for the
    // new scroll position (the scroll event may not fire for programmatic sets).
    scheduler.request();
  };

  // O(1) lookup: first unit index for the given itemId.
  // Committed tier uses committedIndexById (maintained in lock-step with
  // committedUnitsArr); active tier falls back to a small linear scan
  // (activeTurn is always short — typically ≤ 5 units per streaming turn).
  // Called from projectAnchor every frame when intent is 'anchor', and from
  // lastUserUnitIdx. Declared as a function (not const) so it is hoisted and
  // accessible from memos created earlier in the component body.
  function firstUnitIndexOf(id: string): number {
    const committedIdx = committedIndexById.get(id);
    if (committedIdx !== undefined) return committedIdx;
    const active = untrack(activeUnits);
    const base = committedUnitsArr.length;
    for (let i = 0; i < active.length; i++) {
      if (active[i]?.itemId === id) return base + i;
    }
    return -1;
  }

  function unitIndexOf(id: string): number {
    return firstUnitIndexOf(id);
  }

  // The ONE function that writes scrollTop. Flush canvas height first so the
  // browser never clamps scrollTop to a stale (outgoing) canvas height — this
  // is the root cause of "open at top after tab switch".
  const projectAnchor = (m: ScrollMode) => {
    if (!scrollEl) return;
    // Synchronously update canvas height so scrollTop is never clamped.
    if (canvasEl) canvasEl.style.height = `${contentH()}px`;

    if (m.kind === 'anchor') {
      const i = unitIndexOf(m.itemId);
      if (i >= 0) {
        const rowTop = virt.top(i) + padTop();
        const target =
          m.edge === 'top' ? rowTop + m.offset : rowTop + virt.size(i) - viewHeight() + m.offset;
        const next = Math.max(0, target);
        // Sub-pixel no-op guard: if the settle correction is smaller than 1 px
        // (anchor already matches the current position), skip the write so the
        // browser thumb is never perturbed by a near-zero adjustment.
        // Compare against expectedScrollTop (our last written value) rather than
        // reading scrollEl.scrollTop to preserve the no-DOM-read-in-write-phase
        // invariant established by Option B.
        if (Math.abs(next - expectedScrollTop) < 1) return;
        writeScrollTop(next);
        return;
      }
      // Anchor item not found (transcript not yet loaded); fall through to tail.
    }
    // tail mode (or anchor item not found yet): re-pin to end.
    if (props.stickToBottom !== false) {
      writeScrollTop(maxScrollTop());
    }
  };

  // ── Per-frame height coalescing ───────────────────────────────────────────
  let totalDirty = false;

  const queueTotalFlush = () => {
    if (totalDirty) return;
    totalDirty = true;
    scheduler.request();
  };

  // ── onHeightChanged — deferred (no per-row DOM read) ─────────────────────
  // Sets needsProject instead of calling projectAnchor synchronously so that
  // N row-height changes during a scroll sweep produce at most ONE projectAnchor
  // (and thus at most ONE forced reflow) in the write phase per rAF frame.
  // This collapses the per-row layout-thrash regression from the scroll rework.
  const onHeightChanged = (_index: number, delta: number) => {
    if (delta === 0) return;
    queueTotalFlush();
    needsProject = true;
    scheduler.request();
  };

  // ── Frame scheduler — created EAGERLY (before onMount) ───────────────────
  //
  // Hoisted to component scope so tween arming (from UnitRow createEffects)
  // never hits a null reference. Phases guard on scrollEl for pre-mount safety.
  let reachStartFired = false;
  // Cache to avoid emitting onActiveUserMessageVisibilityChange on every frame.
  // `undefined` means "not yet emitted" — forces an emit on the first writePhase
  // and after every model swap.
  let lastActiveUserVisible: boolean | undefined;
  let lastAtBottom: boolean | undefined;

  // Smooth-scroll suppression: when a smooth-scroll animation is in flight,
  // intermediate scrollTop updates are browser-driven and must not be treated
  // as user input. While `smoothScrolling` is true, readPhase keeps
  // expectedScrollTop in sync and skips intent re-derivation.
  let smoothScrolling = false;
  let smoothScrollTarget: number | undefined;

  // performance.now() of the last real user scroll or smooth-scroll animation
  // frame. Projection (projectAnchor) is suppressed until SCROLL_SETTLE_MS ms
  // after this timestamp — covering the whole gesture, not just one frame.
  // Initialised to 0 so the first write-phase call (no prior scroll) is settled.
  let lastUserScrollAt = 0;

  const emitAtBottom = (value: boolean): void => {
    if (value === lastAtBottom) return;
    lastAtBottom = value;
    props.onAtBottomChange?.(value);
  };

  const readPhase = () => {
    const el = scrollEl;
    if (!el) return;
    const st = el.scrollTop;
    // Capture shadow values for the write phase. These are stable for the
    // entire frame: computeVisible/computePin consume them without re-reading.
    shadowScrollTop = st;
    shadowViewHeight = viewHeight();
    const userDelta = st - expectedScrollTop;
    setScrollVelocity(userDelta);

    // Smooth-scroll suppression: while a smooth scroll animation is in flight
    // the browser moves scrollTop without user input. Keep expectedScrollTop in
    // sync so we don't misread intermediate frames as user scrolls.
    // Treat animation frames identically to user scrolls for settle-window
    // purposes so projectAnchor never fights an in-flight animation.
    if (smoothScrolling) {
      lastUserScrollAt = performance.now();
      expectedScrollTop = st;
      const target = smoothScrollTarget;
      if (target !== undefined && Math.abs(st - target) < 1) {
        smoothScrolling = false;
      }
      schedulePrefetch();
      return;
    }

    // Only re-derive intent when the user actually moved the scrollbar.
    // Use USER_SCROLL_EPSILON to filter sub-pixel self-write rounding so the
    // arithmetic clamp in writeScrollTop is never misread as a user scroll.
    if (Math.abs(userDelta) > USER_SCROLL_EPSILON) {
      lastUserScrollAt = performance.now();
      expectedScrollTop = st;
      const nowAtBottom = maxScrollTop() - st <= STICK_THRESHOLD_PX;
      const prevAnchor = anchor();
      const prevAtBottom = prevAnchor.kind === 'tail';
      if (nowAtBottom) {
        if (!prevAtBottom) {
          setAnchor({ kind: 'tail' });
        }
      } else {
        const pt = padTop();
        const anchorUnitIdx = virt.findIndex(Math.max(0, st - pt));
        const anchorUnit = units().at(anchorUnitIdx);
        if (anchorUnit) {
          setAnchor({
            kind: 'anchor',
            itemId: anchorUnit.itemId,
            edge: 'top',
            offset: st - (virt.top(anchorUnitIdx) + pt),
          });
        }
      }
      emitAtBottom(nowAtBottom);
    }

    if (st <= REACH_START_THRESHOLD_PX) {
      if (!reachStartFired) {
        reachStartFired = true;
        props.onReachStart?.();
      }
    } else {
      reachStartFired = false;
    }

    schedulePrefetch();
  };

  const animatePhase = (): boolean => tweenRegistry.advance(performance.now());

  // ── commit() — single-owner geometry committer ────────────────────────────
  //
  // commit() diffs a new LayoutSnapshot against lastLayout and applies only
  // the changed fields to the DOM / signals. This ensures:
  //   - No DOM read inside the write phase (all reads were in readPhase).
  //   - At most one forced reflow per frame (from projectAnchor if needsProject).
  //   - Zero signal writes on stable frames (snapshot diff + equals guards).

  function commit(next: LayoutSnapshot, nextVisible: number[]): void {
    const prev = lastLayout;

    // Canvas height — write only when changed.
    if (!prev || prev.canvasHeight !== next.canvasHeight) {
      if (canvasEl) canvasEl.style.height = `${next.canvasHeight}px`;
    }

    // Visible set — setVisible uses sameRange so <For> reconciles on changes only.
    setVisible(nextVisible);

    // Row positions — only write transforms that actually changed.
    const pt = padTop();
    for (const idx of nextVisible) {
      const top = virt.top(idx) + pt;
      if (appliedTop.get(idx) !== top) {
        appliedTop.set(idx, top);
        const el = rowEls.get(idx);
        if (el) el.style.transform = `translateY(${top}px)`;
      }
    }

    // Pin overlay — setPin uses samePin so <Show> reconciles on changes only.
    setPin(next.pin);

    lastLayout = next;
  }

  const writePhase = (): boolean => {
    if (totalDirty) {
      totalDirty = false;
      setTotalHeight(virt.total());
    }
    // Projection is coalesced: at most one projectAnchor per frame (not per row).
    // This is the fix for the per-row layout-thrash perf regression.
    //
    // Gate on a settle window instead of a per-frame flag: if the user scrolled
    // (or a smooth-scroll animation ran) within the last SCROLL_SETTLE_MS, skip
    // the correction so the browser thumb is never fought mid-gesture. This
    // eliminates the in-direction jump that a per-frame gate allowed (any rAF
    // tick landing between scroll events would open the old gate mid-drag).
    // While unsettled, scheduler.request() keeps the loop alive so the
    // projection fires after the window without any further events.
    // request() does not increment the converge counter, so it cannot trip
    // the MAX_CONVERGE halt in the frame scheduler.
    if (needsProject) {
      const settled = performance.now() - lastUserScrollAt > SCROLL_SETTLE_MS;
      if (settled) {
        needsProject = false;
        projectAnchor(anchor());
        // projectAnchor flushed canvas height and wrote scrollTop; re-capture
        // shadow scrollTop so computeVisible/computePin use the projected value.
        if (scrollEl) shadowScrollTop = scrollEl.scrollTop;
      } else {
        scheduler.request();
      }
    }
    const nextVisible = computeVisible();
    const pt = padTop();
    const nextPin = computePin(shadowScrollTop, pt);
    const next: LayoutSnapshot = {
      start: nextVisible[0] ?? 0,
      end: nextVisible[nextVisible.length - 1] ?? -1,
      canvasHeight: contentH(),
      pin: nextPin,
    };
    commit(next, nextVisible);

    emitAtBottom(maxScrollTop() - shadowScrollTop <= STICK_THRESHOLD_PX);

    // Emit active-user-message visibility change when the state flips.
    if (props.onActiveUserMessageVisibilityChange) {
      const visible = computeActiveUserVisible(shadowScrollTop, shadowViewHeight, pt);
      if (visible !== lastActiveUserVisible) {
        lastActiveUserVisible = visible;
        props.onActiveUserMessageVisibilityChange(visible);
      }
    }

    return false;
  };

  const scheduler = createFrameScheduler({
    read: readPhase,
    animate: animatePhase,
    write: writePhase,
  });
  onCleanup(() => scheduler.dispose());

  // ── Central tween registry — wired to eager scheduler ────────────────────
  const tweenRegistry = createTweenRegistry(virt, onHeightChanged, {
    requestFrame: () => scheduler.request(),
  });

  // ── Invalidation bridge — the single reactive input list ─────────────────
  //
  // One createEffect reads every layout-affecting signal and calls
  // scheduler.request(). This replaces the per-memo dependency curation that
  // drifted (and caused blank transcripts / stale pins). Any layout input
  // change => one arm, never more, never fewer.
  //
  // Output signals (visible, pin) are intentionally NOT in this list —
  // reading them here would create a feedback loop.
  createEffect(() => {
    // units() already tracks committedUnitsVersion() transitively — no need to
    // list it here separately.
    units();
    totalHeight();
    padTop();
    padBottom();
    viewHeight();
    containerWidth();
    measureEpoch();
    expandedUserId();
    scheduler.request();
  });

  // Idle-time prefetch state — referenced by readPhase / schedulePrefetch
  let prefetchIdleId: ReturnType<typeof requestIdleCallback> | null = null;
  let prefetchStart = -1;
  let prefetchEnd = -1;

  const schedulePrefetch = () => {
    if (prefetchIdleId !== null) return;
    prefetchIdleId = requestIdleCallback(runPrefetchSlice, { timeout: 500 });
  };

  const cancelPrefetch = () => {
    if (prefetchIdleId !== null) {
      cancelIdleCallback(prefetchIdleId);
      prefetchIdleId = null;
    }
  };

  const runPrefetchSlice = (deadline: IdleDeadline) => {
    prefetchIdleId = null;

    const visStart = lastVisibleStart;
    const visEnd = lastVisibleEnd;
    const us = units();
    const n = us.length;
    if (n === 0) return;

    const ahead = Math.min(visEnd + PREFETCH_AHEAD, n - 1);
    const behind = Math.max(visStart - PREFETCH_BEHIND, 0);

    if (prefetchStart < 0 || prefetchEnd < 0) {
      prefetchStart = visEnd + 1;
      prefetchEnd = ahead;
    }

    const w = containerWidth();
    const t = theme();

    let measured = 0;

    const prefetchUnit = (ui: number): void => {
      const u = us.at(ui);
      if (!u) return;
      const unitDef = UNIT_REGISTRY[u.kind];
      if (!unitDef) return;
      const c = u.chrome;
      const unitInsetX = c?.insetX ?? 0;
      const ctx: MeasureCtx = {
        theme: t,
        width: Math.max(0, w - 2 * unitInsetX),
        isCollapsed: (id: string) => viewState().isCollapsed(id),
        expanded: (id: string) => viewState().isCollapsed(id),
        caches: caches(),
        measureEpoch: measureEpoch(),
        expandedId: expandedUserId(),
      };
      const contentH = unitDef.measure(u.data, ctx, unitDef.vars ?? {});
      const h = unitReservedHeight(u, contentH);
      const delta = virt.setSize(ui, h);
      if (delta !== 0) onHeightChanged(ui, delta);
    };

    while (prefetchStart <= prefetchEnd && deadline.timeRemaining() >= PREFETCH_MIN_REMAINING_MS) {
      prefetchUnit(prefetchStart);
      measured++;
      prefetchStart++;
    }

    if (prefetchStart > prefetchEnd) {
      let backCursor = visStart - 1;
      while (backCursor >= behind && deadline.timeRemaining() >= PREFETCH_MIN_REMAINING_MS) {
        prefetchUnit(backCursor);
        measured++;
        backCursor--;
      }
    }

    if (measured > 0 && prefetchStart <= prefetchEnd) {
      schedulePrefetch();
    }
  };

  // ── Scroll helpers ────────────────────────────────────────────────────────
  const doScrollToTop = (opts?: { behavior?: ScrollBehavior }) => {
    const el = scrollEl;
    if (!el) return;
    const firstUnit = units().at(0);
    if (firstUnit) {
      setAnchor({ kind: 'anchor', itemId: firstUnit.itemId, edge: 'top', offset: -padTop() });
    }
    if (opts?.behavior === 'smooth') {
      smoothScrolling = true;
      smoothScrollTarget = 0;
      el.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
      writeScrollTop(0);
    }
  };

  const doScrollToBottom = (opts?: { behavior?: ScrollBehavior }) => {
    const el = scrollEl;
    if (!el) return;
    const target = maxScrollTop();
    setAnchor({ kind: 'tail' });
    if (opts?.behavior === 'smooth') {
      smoothScrolling = true;
      smoothScrollTarget = target;
      el.scrollTo({ top: target, behavior: 'smooth' });
    } else {
      writeScrollTop(target);
    }
  };

  const doScrollToItem = (id: string, opts?: ScrollToItemOptions) => {
    const el = scrollEl;
    if (!el) return;

    const us = units();
    let unitIdx = -1;
    for (let i = 0; i < us.length; i++) {
      if (us.at(i)?.itemId === id) {
        unitIdx = i;
        break;
      }
    }
    if (unitIdx < 0) return;

    let itemTotalH = 0;
    for (let i = unitIdx; i < us.length; i++) {
      if (us.at(i)?.itemId !== id) break;
      itemTotalH += virt.size(i);
    }

    const idx = unitIdx;
    const rowH = itemTotalH;

    const align = opts?.align ?? 'start';
    const extraOffset = opts?.offset ?? 0;
    const behavior = opts?.behavior ?? 'auto';

    const computeTarget = () => {
      const rowTop = virt.top(idx) + padTop();
      const vh = el.clientHeight;
      let target: number;
      if (align === 'center') {
        target = rowTop - (vh - rowH) / 2;
      } else if (align === 'end') {
        target = rowTop - vh + rowH;
      } else {
        target = rowTop;
      }
      return Math.max(0, target + extraOffset);
    };

    const t0 = computeTarget();

    // Commit the scroll as a top-edge anchor intent so onHeightChanged keeps
    // the row stable as content changes above.
    const anchorUnit = us.at(idx);
    if (anchorUnit) {
      const newOffset = t0 - (virt.top(idx) + padTop());
      setAnchor({
        kind: 'anchor',
        itemId: anchorUnit.itemId,
        edge: 'top',
        offset: newOffset + extraOffset,
      });
    }

    if (behavior === 'smooth') {
      smoothScrolling = true;
      smoothScrollTarget = t0;
      el.scrollTo({ top: t0, behavior: 'smooth' });
    } else {
      writeScrollTop(t0);
      requestAnimationFrame(() => {
        const t1 = computeTarget();
        writeScrollTop(t1);
      });
    }
  };

  const doLoadOlder = (turns: TranscriptTurn[]) => {
    const el = scrollEl;
    if (!el || turns.length === 0) return;

    const t = theme();
    const prependedUnits = flattenTier(turns, segmentCtx(false), SEGMENTERS, UNIT_REGISTRY);

    const anchorUnitIdx = virt.findIndex(Math.max(0, el.scrollTop - padTop()));
    const anchorId = units().at(anchorUnitIdx)?.itemId;
    const anchorOffset = el.scrollTop - (virt.top(anchorUnitIdx) + padTop());

    const loadEstimateCtx: MeasureCtx = {
      theme: t,
      width: containerWidth(),
      isCollapsed: () => false,
      expanded: () => false,
      caches: caches(),
    };
    const count = prependedUnits.length;
    virt.prepend(count, (i) => {
      const unit = prependedUnits[i];
      if (!unit) return userTopGap + 60;
      const unitDef = UNIT_REGISTRY[unit.kind];
      const contentH =
        unitDef?.estimate?.(unit.data, loadEstimateCtx, unitDef.vars ?? {}) ??
        genericEstimate(unit.data as unknown as ChatItem, loadEstimateCtx);
      return unitReservedHeight(unit, contentH);
    });

    state().transcript.history.prepend(turns);
    refreshTotal();

    if (anchorId !== undefined) {
      const newUs = units();
      let newUnitIdx = -1;
      for (let i = 0; i < newUs.length; i++) {
        if (newUs.at(i)?.itemId === anchorId) {
          newUnitIdx = i;
          break;
        }
      }
      if (newUnitIdx >= 0) {
        const newTop = virt.top(newUnitIdx) + padTop() + anchorOffset;
        writeScrollTop(newTop);
      }
    }
  };

  // ── Snapshot / restore helpers ────────────────────────────────────────────
  //
  // snapshotInto: persist only the heightmap. The scroll intent (ScrollMode)
  // is already kept current in ChatState by setAnchor() — no extra DOM reads
  // needed here. Called by the dispose onCleanup and by the swap effect.

  function snapshotInto(target: ChatState): void {
    // Use committedUnitsArr (not live units()) so that when this is called from
    // the reset effect (before clearing), it captures the OUTGOING model's unit
    // ids and measured sizes — not the incoming model's (which virt already
    // reflects by the time the swap effect fires). Active-turn units are
    // ephemeral and intentionally excluded; they are re-estimated on next mount.
    const w = untrack(containerWidth);
    const entries: Array<[string, number]> = [];
    for (let i = 0; i < committedUnitsArr.length; i++) {
      const u = committedUnitsArr[i];
      if (u) entries.push([u.id, virt.size(i)]);
    }
    target.heightmap.setAll(entries);
    target.heightmap.lastWidth = w;
    // ScrollMode is already persisted continuously by setAnchor() in readPhase
    // and by host calls to setScrollMode(). No DOM-derived anchor write here.
  }

  // attach: load the intent from a (possibly new) model and project it onto
  // the DOM. Synchronously flushes canvas height before writing scrollTop so
  // the browser never clamps to the outgoing model's stale canvas height —
  // the root cause of "open at top after tab switch".
  function attach(target: ChatState): void {
    const m = target.scroll.get();
    // Update the local signal without persisting (it already IS the canonical value).
    setAnchorSignal(m);
    projectAnchor(m);
  }

  // ── DOM setup ─────────────────────────────────────────────────────────────
  onMount(() => {
    const el = scrollEl!;

    // Populate the controls holder so handle delegates resolve immediately.
    if (props.controls) {
      props.controls.scrollToTop = doScrollToTop;
      props.controls.scrollToBottom = doScrollToBottom;
      props.controls.scrollToItem = doScrollToItem;
      props.controls.loadOlder = doLoadOlder;
      props.controls.toggleCollapsed = (id) => viewState().toggleCollapsed(id);
      props.controls.composerSlot = composerSlotEl ?? null;
      props.controls.heroSlot = heroSlotEl ?? null;
      props.controls.contentOverlay = contentOverlaySlotEl ?? null;
      props.controls.setComposerPlacement = setComposerPlacement;
      // Declarative scroll intent: host sets intent; ChatRoot projects it.
      props.controls.setScrollMode = (m: ScrollMode) => {
        setAnchor(m);
        projectAnchor(m);
      };
      // Notify the view creator that all controls are wired.
      props.controls.onMounted?.();
    }

    const onScroll = () => {
      if (el.offsetParent === null) return;
      scheduler.request();
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    onCleanup(() => {
      el.removeEventListener('scroll', onScroll);
      cancelPrefetch();
    });

    // On dispose: snapshot measured row heights and scroll anchor into ChatState
    // so the next mount can seed the Virtualizer and restore position without
    // scrollbar drift (e.g. when switching conversation tabs).
    onCleanup(() => snapshotInto(state()));

    const roHeight = new ResizeObserver((entries) => {
      const h = entries[0]?.contentRect.height;
      if (h && h > 0) setViewHeight(h);
    });
    roHeight.observe(el);
    onCleanup(() => roHeight.disconnect());

    // Target geometry ancestors instead of canvasEl so this observer only fires
    // on genuine column geometry changes and not on canvas height mutations from
    // streaming/tween updates. Observing outer/scroll catches a centered max-width
    // column moving horizontally even when the probe's own width is unchanged.
    if (widthProbeEl) {
      const roWidth = new ResizeObserver(() => updateContentColumnGeometry());
      roWidth.observe(widthProbeEl);
      roWidth.observe(el);
      if (outerEl) roWidth.observe(outerEl);
      updateContentColumnGeometry();
      onCleanup(() => roWidth.disconnect());
    }

    // Composer slot: measure its height and drive padBottom.
    if (props.composer === 'slot' && composerSlotEl) {
      const roSlot = new ResizeObserver((entries) => {
        const h = entries[0]?.contentRect.height ?? 0;
        setSlotPadBottom(effectiveComposerPlacement() === 'center' ? 0 : h);
      });
      roSlot.observe(composerSlotEl);
      onCleanup(() => roSlot.disconnect());
    }

    const onClick = (e: Event) => {
      const t = e.target as HTMLElement;

      const userCard = t.closest('[data-user-card]') as HTMLElement | null;
      if (userCard?.dataset.userCard) {
        const id = userCard.dataset.userCard;
        if (expandedUserId() !== id) {
          setExpandedUserId(id);
        }
        return;
      }

      const collapseTarget = t.closest('[data-collapse-id]') as HTMLElement | null;
      if (collapseTarget?.dataset.collapseId) {
        const id = collapseTarget.dataset.collapseId;
        // Pin the toggled row at its current viewport position before the height
        // change. With readPhase no longer reclassifying intent on idle frames,
        // this anchor is now guaranteed to survive the tween — fixing the scroll
        // jump on expand/collapse in short reserve-active transcripts.
        const idx = unitIndexOf(id);
        if (idx >= 0 && scrollEl) {
          const offset = scrollEl.scrollTop - (virt.top(idx) + padTop());
          setAnchor({ kind: 'anchor', itemId: id, edge: 'top', offset });
        }
        viewState().toggleCollapsed(id);
        return;
      }

      if (expandedUserId() !== null) {
        setExpandedUserId(null);
      }
    };
    const clickTarget = outerEl ?? el;
    clickTarget.addEventListener('click', onClick);
    onCleanup(() => clickTarget.removeEventListener('click', onClick));

    // Visibility watchdog: self-heal any missed wakes when pane becomes visible.
    if (typeof document !== 'undefined') {
      const onVisibilityChange = () => {
        if (!document.hidden) {
          scheduler.forceReconcile(() => {
            totalDirty = true;
          });
        }
      };
      document.addEventListener('visibilitychange', onVisibilityChange);
      onCleanup(() => document.removeEventListener('visibilitychange', onVisibilityChange));
    }

    // Attach to the initial model: load its persisted scroll intent and project
    // it onto the DOM. Flushes canvas height first so scrollTop is never clamped.
    attach(state());

    // ── Model-swap effect (view.setModel path) ────────────────────────────
    // When the host calls view.setModel(newState), the `state` signal changes.
    // The reset effect (created before onMount in component scope) runs first
    // and snapshots the outgoing model's heightmap into it before clearing
    // committedUnitsArr. By the time this swap effect fires, virt is already
    // re-seeded by the count-sync effect. We only need to attach the incoming
    // model's intent and force a fresh geometry pass.
    createEffect(
      on(
        state,
        (next) => {
          // Reset visibility cache so the next writePhase re-emits for the new
          // conversation, even if the boolean value happens to be the same.
          lastActiveUserVisible = undefined;
          lastAtBottom = undefined;
          // Load the incoming model's scroll intent and project it onto the DOM.
          attach(next);
          needsProject = true;
          scheduler.forceReconcile(() => {
            totalDirty = true;
          });
        },
        { defer: true }
      )
    );

    // Force an initial reconcile pass so the scheduler runs once on attach.
    scheduler.forceReconcile(() => {
      totalDirty = true;
    });
  });

  // ── Active-turn id set ────────────────────────────────────────────────────
  const activeTurnItemIds = createMemo(() => {
    const active = state().transcript.state.activeTurnSnapshot;
    const ids = new Set(active?.items.map((i) => i.id) ?? []);
    const pendingPrompt = state().session.state.pendingPrompt;
    if (pendingPrompt) ids.add(pendingPrompt.id);
    return ids;
  });

  const currentMessageId = createMemo<string | null>(() => {
    return findLastUserMessageId(state().transcript.state.committedTurns);
  });

  const turnStatus = () => state().transcript.state.turnStatus;

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <DebugContext.Provider value={debugValue}>
      <ThemeContext.Provider value={theme}>
        <CachesContext.Provider value={caches()}>
          <CommandsContext.Provider value={commands}>
            <TurnStateContext.Provider value={{ currentMessageId, turnStatus }}>
              <div
                ref={(el) => {
                  outerEl = el;
                }}
                class={outerClip}
              >
                <div
                  ref={(el) => {
                    scrollEl = el;
                  }}
                  data-chat-scroll
                  class={`${scrollContainer}${props.class ? ` ${props.class}` : ''}`}
                  style={scrollElStyle}
                >
                  {/* Zero-height probe: same max-width cap as rows; the width
                      ResizeObserver targets this to isolate layout-width changes
                      from canvas height mutations (streaming / tween updates). */}
                  <div
                    ref={(el) => {
                      widthProbeEl = el;
                    }}
                    data-chat-width-probe
                    aria-hidden="true"
                    class={`${widthProbeClass} ${contentClass()}`}
                  />
                  <div
                    ref={(el) => {
                      canvasEl = el;
                      el.style.height = `${contentH()}px`;
                    }}
                    data-chat-canvas
                    class={`${canvas} ${contentClass()}`}
                  >
                    <For each={visible()}>
                      {(unitIndex) => {
                        const u = () => units().at(unitIndex);
                        const isActiveTurn = () => {
                          const unit = u();
                          return unit ? activeTurnItemIds().has(unit.itemId) : false;
                        };

                        return (
                          <Show when={u()}>
                            <div
                              class={unitRowWrapper}
                              ref={(el) => {
                                rowEls.set(unitIndex, el);
                                // Seed initial transform; commit() reconciles on each frame.
                                el.style.transform = `translateY(${virt.top(unitIndex) + padTop()}px)`;
                                onCleanup(() => {
                                  rowEls.delete(unitIndex);
                                  appliedTop.delete(unitIndex);
                                });
                              }}
                              data-index={String(unitIndex)}
                            >
                              <UnitRow
                                unit={u()!}
                                index={unitIndex}
                                rowWidth={containerWidth()}
                                theme={theme()}
                                viewState={viewState()}
                                virt={virt}
                                onHeightChanged={onHeightChanged}
                                tweenRegistry={tweenRegistry}
                                isActiveTurn={isActiveTurn()}
                                caches={caches()}
                                measureEpoch={measureEpoch()}
                                expandedId={expandedUserId()}
                              />
                            </div>
                          </Show>
                        );
                      }}
                    </For>
                  </div>
                </div>
                <Show when={pin()}>
                  {(ps) => {
                    // Resolve the ChatMessage reactively via itemId (stable) so
                    // a stale unit-index lookup can never hand a wrong item to
                    // PinnedUserMessage. findItemById searches committed-then-active
                    // so live active-turn user messages resolve too.
                    const pinnedItem = (): ChatMessage | undefined => {
                      const itemId = ps().itemId;
                      if (!itemId) return undefined;
                      const transcript = state().transcript;
                      const item = transcript.findItemById(itemId);
                      return item && item.kind === 'message' && item.role === 'user'
                        ? (item as ChatMessage)
                        : undefined;
                    };
                    return (
                      <Show when={pinnedItem()}>
                        {(item) => (
                          <div
                            class={pinnedOverlay}
                            aria-hidden="true"
                            style={{ transform: `translateY(${ps().overlayTop}px)` }}
                          >
                            {/* Position from the scroll-container width probe so
                                classic scrollbar gutters cannot offset the pinned
                                copy from the inline transcript row underneath. */}
                            <div
                              class={`${pinnedOverlayColumn} ${contentClass()}`}
                              style={{
                                'margin-left': `${contentColumnLeft()}px`,
                                'margin-right': '0px',
                                width: `${containerWidth()}px`,
                                'max-width': 'none',
                              }}
                            >
                              <PinnedUserMessage
                                item={item()}
                                rowWidth={containerWidth()}
                                theme={theme()}
                                caches={caches()}
                                expandedId={expandedUserId}
                              />
                            </div>
                          </div>
                        )}
                      </Show>
                    );
                  }}
                </Show>
                {/* Content overlay slot: absolute cover above transcript/scroll,
                    below the composer (z-index 15). Hosts portal loading/empty/
                    disabled states into this element. */}
                <Show when={props.contentOverlay}>
                  <div
                    ref={(el) => {
                      contentOverlaySlotEl = el;
                    }}
                    class={contentOverlaySlotClass}
                  />
                </Show>
                {/* Composer slot: full-width blurred backdrop strip; the inner
                    centered div is what the host portals its React composer
                    into, and what the ResizeObserver measures for padBottom. */}
                <Show when={props.composer === 'slot'}>
                  <div
                    ref={(el) => {
                      composerSlotLayerEl = el;
                    }}
                    class={`${effectiveComposerPlacement() === 'center' ? composerSlotCenteredClass : composerSlotClass}${composerAnimating() ? ` ${composerSlotAnimatingClass}` : ''}`}
                  >
                    <div
                      ref={(el) => {
                        heroSlotEl = el;
                      }}
                      class={`${heroSlotClass} ${effectiveComposerPlacement() === 'center' ? heroSlotVisibleClass : heroSlotHiddenClass}`}
                    />
                    <div
                      ref={(el) => {
                        composerSlotEl = el;
                      }}
                      class={`${composerSlotInnerClass} ${effectiveComposerPlacement() === 'center' ? composerSlotInnerCenteredClass : composerSlotInnerBottomClass}`}
                    />
                  </div>
                </Show>
              </div>
            </TurnStateContext.Provider>
          </CommandsContext.Provider>
        </CachesContext.Provider>
      </ThemeContext.Provider>
    </DebugContext.Provider>
  );
}
