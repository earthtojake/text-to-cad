/**
 * UnitRow — unit-level row renderer driven by UNIT_REGISTRY.
 *
 * The virtualizer indexes a flat RenderUnit[] array produced by flatten().
 * Each visible unit index renders via this component.
 *
 * Rendering:
 *   UnitDef.measure(data, ctx) → number  (content height)
 *   UnitDef.Render({ data, ctx })
 *   GroupChrome from the segmenter supplies insetX for horizontal padding.
 *
 * Height reservation:
 *   unitReservedHeight(unit, contentH) = gapBefore + contentH
 *
 * Inter-row spacing lives entirely in unit.gapBefore (top padding). flatten()
 * resolves each seam gap via margin-collapse (max of adjacent UnitDef margins)
 * and stamps it onto the lower unit's gapBefore. No trailing bottom padding is
 * added — each seam is owned by exactly one side.
 *
 * Collapse/expand animation:
 *   The LOGICAL reserved height is the exact value returned by measure() for
 *   the current collapse state. A createHeightTween tracks this target and
 *   interpolates toward it over ~200ms; the virtualizer is driven from the
 *   animated value so rows below reposition in lockstep.
 *
 *   While collapsing (animated height > logical target), a DISPLAY view of the
 *   collapse state lags the logical state to keep the expanded DOM mounted so
 *   the content is clipped-and-revealed rather than popped in/out. An
 *   `overflow: hidden` clip at the animated content height achieves the reveal.
 *   The clip is removed at rest so steady-state rendering is unchanged.
 *
 * Debug overlay: dashed outline at reserved height; red when actual ≠ reserved.
 *   Mismatch check is suppressed while animating (expected mid-tween).
 */

import { useDebug } from '@components/contexts/debug-context';
import type { ChatCaches } from '@core/caches';
import type { MeasureCtx, RenderCtx } from '@core/define';
import type { ChatTheme } from '@core/theme';
import type { RenderUnit } from '@core/units';
import { unitReservedHeight } from '@core/units';
import type { Virtualizer } from '@core/virtualizer';
import type { ViewState } from '@state/view-state';
import {
  Show,
  createEffect,
  createMemo,
  createSignal,
  onCleanup,
  onMount,
  untrack,
} from 'solid-js';
import { Dynamic } from 'solid-js/web';
import { createHeightTween } from './create-height-tween';
import type { TweenHandle, TweenRegistry } from './tween-registry';
import { UNIT_REGISTRY } from './unit-registry';
import {
  debugLabel,
  debugMismatch,
  debugMismatchText,
  debugOk,
  debugOverlay,
} from './unit-row.css';

// ── Debug overlay ─────────────────────────────────────────────────────────────

function UnitDebugOverlay(props: {
  reserved: number;
  animating: boolean;
  rowEl: () => HTMLElement | undefined;
}) {
  const [mismatch, setMismatch] = createSignal(false);
  const [actualH, setActualH] = createSignal(0);

  onMount(() => {
    const el = props.rowEl();
    if (!el) return;

    const check = () => {
      const h = el.offsetHeight;
      setActualH(h);
      // Suppress mismatch during animation — actual != reserved is expected.
      setMismatch(!props.animating && Math.abs(h - props.reserved) > 0.5);
    };
    const ro = new ResizeObserver(check);
    ro.observe(el);
    onCleanup(() => ro.disconnect());
    requestAnimationFrame(check);
  });

  return (
    <div
      class={`${debugOverlay} ${mismatch() ? debugMismatch : debugOk}`}
      style={{ height: `${props.reserved}px` }}
    >
      <span class={debugLabel}>
        unit · reserved={props.reserved}
        <Show when={mismatch()}>
          {' '}
          <span class={debugMismatchText}>
            ⚠ actual={actualH()} (+{actualH() - props.reserved})
          </span>
        </Show>
      </span>
    </div>
  );
}

// ── UnitRowProps ──────────────────────────────────────────────────────────────

export type UnitRowProps = {
  unit: RenderUnit;
  /** Absolute unit index in the flat units array (used by virt.setSize). */
  index: number;
  rowWidth: number;
  theme: ChatTheme;
  viewState: ViewState;
  virt: Virtualizer;
  onHeightChanged: (index: number, delta: number) => void;
  /**
   * Central tween registry from ChatRoot. When provided, height tweens are
   * managed centrally (Phase 2). When absent, falls back to a local
   * createHeightTween (legacy path for isolated stories / tests).
   */
  tweenRegistry?: TweenRegistry;
  /** True when the unit's source item is in activeTurn (currently streaming). */
  isActiveTurn?: boolean;
  /** Per-instance cache bundle from ChatRoot. */
  caches: ChatCaches;
  /**
   * Monotonic counter from ChatRoot bumped after fonts load.
   * Threaded into MeasureCtx so blockMemo fingerprints become stale,
   * forcing a re-measure with correct font metrics.
   */
  measureEpoch?: number;
  /**
   * Id of the single currently-expanded user message card (from ChatRoot).
   * Threaded into MeasureCtx so user card measure re-runs when expand toggles.
   */
  expandedId?: string | null;
};

// ── UnitRow ───────────────────────────────────────────────────────────────────

export function UnitRow(props: UnitRowProps) {
  const debug = useDebug();
  let rowEl: HTMLElement | undefined;

  const def = createMemo(() => UNIT_REGISTRY[props.unit.kind]);

  const chrome = createMemo(() => props.unit.chrome);
  const insetX = createMemo(() => chrome()?.insetX ?? 0);

  // ── LOGICAL ctx — the true committed collapse state ─────────────────────────
  // This is what measure() always reads. The tween target comes from here.

  const logicalMeasureCtx = (): MeasureCtx => ({
    theme: props.theme,
    width: Math.max(0, props.rowWidth - 2 * insetX()),
    isCollapsed: (id) => props.viewState.isCollapsed(id),
    expanded: (id) => props.viewState.isCollapsed(id),
    caches: props.caches,
    measureEpoch: props.measureEpoch,
    expandedId: props.expandedId,
  });

  const contentH = createMemo(() => {
    const d = def();
    if (!d) return 0;
    return d.measure(props.unit.data, logicalMeasureCtx(), d.vars ?? {});
  });

  const logicalReserved = createMemo(() => unitReservedHeight(props.unit, contentH()));

  // ── Height tween ───────────────────────────────────────────────────────────
  //
  // Only genuine collapse/expand toggles should animate. Layout settling on
  // mount (width measurement, font-load re-measure) and streaming growth all
  // change `logicalReserved` too, but must SNAP — otherwise the reserved height
  // animates during initial layout and the scrollbar jumps.
  //
  // We detect a real toggle by comparing the row's expand signature to the value
  // captured at the previous target change. A UnitDef may also expose a small
  // semantic animation key for state transitions such as thinking → done.
  // `shouldAnimate` is invoked untracked exactly once per target change so both
  // signatures stay in lockstep while ordinary streaming growth still snaps.
  // Inverted semantics throughout: `isCollapsed(id) === true` means "expanded".
  const rowExpanded = (): boolean =>
    props.viewState.isCollapsed(props.unit.itemId) || props.expandedId === props.unit.itemId;
  const rowAnimationKey = (): string | number | boolean | null => {
    const d = def();
    return d?.heightAnimationKey?.(props.unit.data, logicalMeasureCtx(), d.vars ?? {}) ?? null;
  };

  let lastExpandSig = untrack(rowExpanded);
  let lastAnimationKey = untrack(rowAnimationKey);
  const shouldAnimate = (): boolean => {
    const cur = rowExpanded();
    const animationKey = rowAnimationKey();
    const changed = cur !== lastExpandSig || animationKey !== lastAnimationKey;
    lastExpandSig = cur;
    lastAnimationKey = animationKey;
    return changed;
  };

  // Tween handle: reactive height/animating/clipHeight accessors.
  // Uses the central registry when available; falls back to a local rAF tween
  // for isolated stories and tests that don't wire up a ChatRoot.
  let tweenHandle: TweenHandle;

  if (props.tweenRegistry) {
    const reg = props.tweenRegistry;
    const getIndex = () => props.index;
    // One source item may segment into several independently measured rows.
    // RenderUnit.id includes the stable segment key; itemId does not.
    const unitId = props.unit.id;

    // Register the initial target; the effect below will call set() on changes.
    tweenHandle = reg.set(unitId, getIndex, untrack(logicalReserved), false);

    createEffect(() => {
      const target = logicalReserved();
      const anim = untrack(shouldAnimate);
      tweenHandle = reg.set(unitId, getIndex, target, anim);
    });

    onCleanup(() => reg.unregister(unitId));
  } else {
    // Legacy path: per-row rAF tween (for stories / tests without ChatRoot).
    const localTween = createHeightTween(logicalReserved, { shouldAnimate });

    // Drive the virtualizer from the animated height so rows below reposition.
    createEffect(() => {
      const delta = props.virt.setSize(props.index, localTween.height());
      if (delta !== 0) props.onHeightChanged(props.index, delta);
    });

    tweenHandle = {
      height: localTween.height,
      animating: localTween.animating,
      clipHeight: (gapBefore: number) =>
        localTween.animating() ? localTween.height() - gapBefore : null,
    };
  }

  const animatedReserved = () => tweenHandle.height();
  const animating = () => tweenHandle.animating();

  // ── Deferred clip release ─────────────────────────────────────────────────
  // When the tween finishes, hold overflow:hidden + the settled height for one
  // rAF before releasing to height:auto / overflow:visible. This prevents a
  // one-frame pop where the DOM and displayViewState swap content in the same
  // frame that the compositor lays out the last animation position.
  const [clipReleased, setClipReleased] = createSignal(!untrack(animating));

  createEffect(() => {
    if (animating()) {
      // Clip immediately when a tween starts (no lag on entering clipped state).
      setClipReleased(false);
    } else {
      // Tween settled — keep the clip for one more frame, then release.
      const rafId = requestAnimationFrame(() => setClipReleased(true));
      onCleanup(() => cancelAnimationFrame(rafId));
    }
  });

  // ── DISPLAY state — lags logical while collapsing ──────────────────────────
  // While the animated height is larger than the logical target (shrinking),
  // we are collapsing. Keep the expanded DOM mounted during this window so the
  // content can be clipped-and-revealed rather than popped out immediately.
  //
  // `itemId` is the id used by viewState and expandedId; the unit's data object
  // carries it as `id` for composite rows (thinking/execute/plan/file-op).
  // For user-message rows, collapse comes from expandedId, not viewState.

  const rowItemId = () => props.unit.itemId;
  const collapsing = () => animating() && animatedReserved() > logicalReserved();

  // Display viewState: override isCollapsed for this row's id while collapsing
  // so def.Render keeps rendering the expanded state.
  const displayViewState = {
    isCollapsed: (id: string): boolean => {
      if (collapsing() && id === rowItemId()) {
        // Inverted semantics in use throughout: "collapsed" flag = "expanded"
        // So returning true = "expanded" = keep the expanded content mounted.
        return true;
      }
      return props.viewState.isCollapsed(id);
    },
  };

  // Display measureCtx: also holds the expanded user-card open during collapse.
  const displayMeasureCtx = (): MeasureCtx => ({
    theme: props.theme,
    width: Math.max(0, props.rowWidth - 2 * insetX()),
    isCollapsed: displayViewState.isCollapsed,
    expanded: displayViewState.isCollapsed,
    caches: props.caches,
    measureEpoch: props.measureEpoch,
    // While collapsing a user-message card: hold expandedId so the expanded
    // render is kept alive during the tween.
    expandedId: collapsing() ? rowItemId() : props.expandedId,
  });

  // ── Animated clip ─────────────────────────────────────────────────────────
  // While animating, clamp the content container to the animated content height
  // (= animatedReserved - gapBefore) and hide overflow so the reveal is smooth.
  // At rest (animating === false), use `auto` / `visible` so steady-state
  // rendering is exactly as before — no clip, no overflow truncation.

  // clipHeight is threaded into RenderCtx so card-style rows (plan, execute)
  // can track their root height to the animated value and keep the bottom
  // border visible throughout the tween.
  const renderCtx: RenderCtx = {
    viewState: displayViewState,
    measureCtx: displayMeasureCtx,
    clipHeight: () => tweenHandle.clipHeight(props.unit.gapBefore),
  };

  return (
    <div
      ref={(e) => {
        rowEl = e;
      }}
      style={{ position: 'relative' }}
    >
      <Show when={def()}>
        {(d) => {
          const c = chrome();
          return (
            <div
              style={{
                'padding-top': `${props.unit.gapBefore}px`,
                'padding-bottom': '0px',
                'padding-left': `${c ? (c.insetX ?? 0) : 0}px`,
                'padding-right': `${c ? (c.insetX ?? 0) : 0}px`,
              }}
            >
              {/* Clip wrapper — active while animating or during one-frame hold */}
              <div
                style={{
                  height: !clipReleased()
                    ? `${animatedReserved() - props.unit.gapBefore}px`
                    : 'auto',
                  overflow: !clipReleased() ? 'hidden' : 'visible',
                }}
              >
                <Dynamic
                  component={d().Render}
                  data={props.unit.data}
                  ctx={renderCtx}
                  vars={d().vars ?? {}}
                />
              </div>
            </div>
          );
        }}
      </Show>
      <Show when={debug()}>
        <UnitDebugOverlay
          reserved={animatedReserved()}
          animating={animating()}
          rowEl={() => rowEl}
        />
      </Show>
    </div>
  );
}
