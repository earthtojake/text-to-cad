/**
 * usePtyPaneResize — per-pane PTY resize controller.
 *
 * Owns the single source of truth for cols/rows within a pane:
 *   1. Reacts to the pane's observable pixel dimensions (PaneDimensionSink) via MobX.
 *   2. Converts px → cols/rows using a cached cell size derived from standalone
 *      canvas measurement (so PTYs resize even when no terminal is mounted).
 *   3. Accepts calibration from a live terminal for maximum accuracy once one mounts.
 *   4. Broadcasts runtime resize calls to ALL session IDs in the pane.
 *   5. Exposes an observable `controllerDims` box so mounted terminals can call
 *      term.resize() reactively without re-measuring.
 *   6. Listens to terminal-font-changed events and recomputes when font settings change.
 *
 * Must be called inside a PaneDimensionProvider so the sink is available.
 */

import type { IObservableValue } from 'mobx';
import { observable, reaction, runInAction } from 'mobx';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  getFrontendPty,
  TERMINAL_LETTER_SPACING,
  TERMINAL_LINE_HEIGHT,
  TERMINAL_PADDING_PX,
} from '@core/features/terminals/api/browser/pty/pty';
import {
  computeGridDimensions,
  invalidateCellMetricsCache,
  measureTerminalCell,
} from '@core/features/terminals/api/browser/pty/pty-dimensions';
import { buildTerminalFontFamily } from '@core/features/terminals/api/browser/pty/terminal-font';
import { TERMINAL_FONT_SIZE_DEFAULT } from '@core/primitives/terminals/api';
import type { PaneDimensionSink } from '@core/primitives/workbench-shell/browser/tabs/pane-dimension-provider';
import { createResizeScheduler, type ResizeScheduler } from './resize-scheduler';

const PTY_RESIZE_DEBOUNCE_MS = 60;

export interface PtyPaneResizeControls {
  /**
   * Observable box tracking the current cols/rows computed by the controller.
   * Mounted terminals subscribe to this to keep their xterm grid in sync without
   * re-measuring themselves.
   */
  controllerDims: IObservableValue<{ cols: number; rows: number } | null>;
  /**
   * Called by a mounted terminal with its exact CSS cell dimensions.
   * Updates the controller's cell size and triggers an immediate recompute
   * so the grid and backend stay in lockstep with the correct measurements.
   */
  calibrateCell(width: number, height: number): void;
  /**
   * Returns the latest known cols/rows synchronously, for pre-mount sizing.
   * Returns null if neither standalone measurement nor calibration has produced
   * a result yet.
   */
  getCurrentDimensions(): { cols: number; rows: number } | null;
}

export function usePtyPaneResize(
  sessionIds: string[],
  sink: PaneDimensionSink | null,
  bottomPadding = 0
): PtyPaneResizeControls {
  const sessionsRef = useRef<string[]>([]);

  // ── Observable controller dims box (stable across renders) ──────────────────
  const controllerDimsBoxRef =
    useRef<IObservableValue<{ cols: number; rows: number } | null>>(null);
  if (controllerDimsBoxRef.current === null) {
    controllerDimsBoxRef.current = observable.box<{ cols: number; rows: number } | null>(null);
  }
  const controllerDims = controllerDimsBoxRef.current;

  // ── Cell size: seeded from standalone measurement, refined by calibration ───
  const cellSizeRef = useRef<{ width: number; height: number } | null>(null);
  if (cellSizeRef.current === null) {
    // Prime with the default font so the controller can broadcast before any
    // terminal has mounted in the pane. lineHeight and letterSpacing must match
    // the Terminal options so the seed rows/cols are correct pre-calibration.
    cellSizeRef.current = measureTerminalCell(
      buildTerminalFontFamily(),
      TERMINAL_FONT_SIZE_DEFAULT,
      TERMINAL_LINE_HEIGHT,
      TERMINAL_LETTER_SPACING
    );
  }

  // ── Calibration guard ────────────────────────────────────────────────────────
  // Prevents the seed from ever reaching the PTY backend. Backend broadcasts are
  // suppressed until a real terminal has calibrated the cell size via calibrateCell().
  const hasCalibratedRef = useRef(false);

  // ── Broadcast scheduler ─────────────────────────────────────────────────────
  const schedulerRef = useRef<ResizeScheduler<{ cols: number; rows: number }> | null>(null);
  if (schedulerRef.current === null) {
    schedulerRef.current = createResizeScheduler((dims) => {
      for (const id of sessionsRef.current) {
        const frontendPty = getFrontendPty(id);
        frontendPty?.resizeBackend(dims.cols, dims.rows);
        const term = frontendPty?.terminal;
        if (term && (term.cols !== dims.cols || term.rows !== dims.rows)) {
          term.resize(dims.cols, dims.rows);
        }
      }
    }, PTY_RESIZE_DEBOUNCE_MS);
  }

  // ── Core recompute ──────────────────────────────────────────────────────────
  // Converts the pane's pixel dimensions + current cell size → cols/rows,
  // updates the observable box, and schedules a backend broadcast.
  const sinkRef = useRef<PaneDimensionSink | null>(sink);
  sinkRef.current = sink;

  // bottomPadding may change when e.g. a ContextBar appears/disappears.
  const bottomPaddingRef = useRef(bottomPadding);
  bottomPaddingRef.current = bottomPadding;

  const recompute = useCallback(() => {
    const currentSink = sinkRef.current;
    const cell = cellSizeRef.current;
    const pixelDims = currentSink?.dimensions;
    if (!cell || !pixelDims) return;

    // The provider measures the content region (TabBar excluded). The uniform
    // TERMINAL_PADDING_PX insets the terminal from all sides; bottomPadding
    // adds an extra bottom inset for chrome rendered inside the content region
    // (e.g. the conversations ContextBar).
    const dims = computeGridDimensions({
      widthPx: pixelDims.width,
      heightPx: pixelDims.height,
      cellWidth: cell.width,
      cellHeight: cell.height,
      paddingPx: TERMINAL_PADDING_PX,
      padding: { bottom: bottomPaddingRef.current },
    });
    if (!dims) return;

    runInAction(() => {
      controllerDimsBoxRef.current!.set(dims);
    });
    // Only broadcast to the backend once a real terminal has calibrated the cell
    // size. The seed is accurate but this prevents any transient seed error from
    // ever reaching the PTY before calibration confirms the measurements.
    if (hasCalibratedRef.current) {
      schedulerRef.current?.schedule(dims);
    }
  }, []);

  const recomputeRef = useRef(recompute);
  recomputeRef.current = recompute;

  // ── MobX reaction: recompute when pane pixel dimensions change ───────────────
  // Runs synchronously within the ResizeObserver callback (MobX action → reaction),
  // preserving the "resize before next paint" guarantee (ENG-1577).
  useEffect(() => {
    if (!sink) return;
    const dispose = reaction(
      () => sink.dimensions,
      () => recomputeRef.current()
    );
    // Fire immediately if we already have dimensions.
    if (sink.dimensions) recomputeRef.current();
    return dispose;
    // `sink` identity only changes when PaneSizingContextProvider re-mounts.
    // eslint-disable-next-line react/exhaustive-deps
  }, [sink]);

  // ── Recompute when bottomPadding changes ────────────────────────────────────
  // The shared measurement does not change when chrome inside the content region
  // (e.g. ContextBar) appears/disappears, so we need an explicit recompute
  // triggered by the padding change rather than a ResizeObserver event.
  const prevBottomPaddingRef = useRef(bottomPadding);
  useEffect(() => {
    if (prevBottomPaddingRef.current !== bottomPadding) {
      prevBottomPaddingRef.current = bottomPadding;
      recomputeRef.current();
    }
  }, [bottomPadding]);

  // ── Font-change event: invalidate standalone cache and recompute ─────────────
  useEffect(() => {
    const handleFontChange = (e: Event) => {
      const detail = (e as CustomEvent<{ fontFamily?: string; fontSize?: number }>).detail;
      const fontFamily = buildTerminalFontFamily(detail?.fontFamily ?? '');
      const fontSize = detail?.fontSize ?? TERMINAL_FONT_SIZE_DEFAULT;
      invalidateCellMetricsCache();
      const newCell = measureTerminalCell(
        fontFamily,
        fontSize,
        TERMINAL_LINE_HEIGHT,
        TERMINAL_LETTER_SPACING
      );
      if (newCell) {
        cellSizeRef.current = newCell;
        recomputeRef.current();
      }
    };
    window.addEventListener('terminal-font-changed', handleFontChange);
    return () => window.removeEventListener('terminal-font-changed', handleFontChange);
  }, []);

  // ── Session IDs: send current dims to newly added sessions ──────────────────
  useEffect(() => {
    const prev = sessionsRef.current;
    const added = sessionIds.filter((id) => !prev.includes(id));
    sessionsRef.current = sessionIds;
    const dims = controllerDimsBoxRef.current!.get();
    if (dims && added.length > 0 && hasCalibratedRef.current) {
      for (const id of added) {
        const frontendPty = getFrontendPty(id);
        frontendPty?.resizeBackend(dims.cols, dims.rows);
        const term = frontendPty?.terminal;
        if (term && (term.cols !== dims.cols || term.rows !== dims.rows)) {
          term.resize(dims.cols, dims.rows);
        }
      }
    }
  }, [sessionIds]);

  // ── Cancel pending flush on unmount ─────────────────────────────────────────
  useEffect(() => {
    return () => schedulerRef.current?.cancel();
  }, []);

  // ── Public API ──────────────────────────────────────────────────────────────
  const calibrateCell = useCallback((width: number, height: number) => {
    const alreadyCalibrated = hasCalibratedRef.current;
    hasCalibratedRef.current = true;
    if (cellSizeRef.current?.width === width && cellSizeRef.current?.height === height) {
      // Cell metrics unchanged; if this is the first calibration, still flush the
      // backend broadcast that was suppressed during the seed-only phase.
      // Guard against a null box value: the pane may have never produced dimensions
      // (e.g. opened in a collapsed panel or before layout), so recompute() could
      // have bailed before setting the box. Scheduling null would throw on flush.
      if (!alreadyCalibrated) {
        const dims = controllerDimsBoxRef.current!.get();
        if (dims) schedulerRef.current?.schedule(dims);
      }
      return;
    }
    cellSizeRef.current = { width, height };
    recomputeRef.current();
  }, []);

  const getCurrentDimensions = useCallback(
    (): { cols: number; rows: number } | null => controllerDimsBoxRef.current!.get(),
    []
  );

  return useMemo(
    () => ({ controllerDims, calibrateCell, getCurrentDimensions }),
    [controllerDims, calibrateCell, getCurrentDimensions]
  );
}
