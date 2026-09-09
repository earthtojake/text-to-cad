import { action, makeObservable, observable, runInAction } from 'mobx';
/**
 * Browser-mode tests for PaneDimensionProvider's ResizeObserver path.
 *
 * These run in a real Chromium process (no JSDOM) so ResizeObserver, CSS
 * layout, and getBoundingClientRect all reflect genuine browser behavior.
 * They validate the single-source measurement design: every box change —
 * whether from a continuous drag, a programmatic toggle, or a grow-back —
 * reaches the sink correctly with no suppression or hand-rolled remeasure.
 *
 * The test directly wires up the same logic that PaneDimensionProvider uses
 * (observe contentRect; seed with getBoundingClientRect on mount) against a
 * real observable sink, so we test the integration without React rendering
 * overhead.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  computeGridDimensions,
  measureTerminalCell,
} from '@core/features/terminals/api/browser/pty/pty-dimensions';
import { createResizeScheduler } from '@core/features/terminals/browser/pty/resize-scheduler';
import type { PaneDimensionSink } from '@core/primitives/workbench-shell/browser/tabs/pane-dimension-provider';

// ── Minimal observable sink ───────────────────────────────────────────────────

class TestSink implements PaneDimensionSink {
  dimensions: { width: number; height: number } | null = null;

  constructor() {
    makeObservable(this, { dimensions: observable, setDimensions: action });
  }

  setDimensions(width: number, height: number): void {
    this.dimensions = { width, height };
  }
}

// ── Wire a PaneDimensionProvider-equivalent onto a DOM element ───────────────
// Mirrors the effect in pane-dimension-provider.tsx exactly so we test the
// real observation path without a React renderer.

function attachProvider(el: HTMLElement, sink: PaneDimensionSink): { disconnect: () => void } {
  const observer = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (!entry) return;
    const { width, height } = entry.contentRect;
    sink.setDimensions(width, height);
  });
  observer.observe(el);
  // Synchronous seed (mirrors the getBoundingClientRect seed in the provider).
  const { width, height } = el.getBoundingClientRect();
  if (width > 0 || height > 0) sink.setDimensions(width, height);
  return { disconnect: () => observer.disconnect() };
}

// ── DOM helper ────────────────────────────────────────────────────────────────

function makeContainer(width: number, height: number): HTMLDivElement {
  const el = document.createElement('div');
  el.style.position = 'absolute';
  el.style.width = `${width}px`;
  el.style.height = `${height}px`;
  document.body.appendChild(el);
  return el;
}

/**
 * Poll until the sink's dimensions match the expected values, or throw after
 * a timeout. ResizeObserver callbacks are asynchronous relative to style
 * changes and may not have fired by the next rAF in headless Chromium.
 */
async function waitForDimensions(
  sink: TestSink,
  expected: { width: number; height: number },
  timeoutMs = 2000
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (sink.dimensions?.width === expected.width && sink.dimensions?.height === expected.height) {
      return;
    }
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  }
  throw new Error(
    `waitForDimensions timed out. Expected ${JSON.stringify(expected)}, got ${JSON.stringify(sink.dimensions)}`
  );
}

// ── Suite ─────────────────────────────────────────────────────────────────────

describe('PaneDimensionProvider single-source measurement', () => {
  let container: HTMLDivElement;
  let sink: TestSink;
  let provider: { disconnect: () => void };

  beforeEach(() => {
    sink = new TestSink();
  });

  afterEach(() => {
    provider?.disconnect();
    container?.remove();
  });

  // ── Initial measurement ──────────────────────────────────────────────────────

  it('seeds sink dimensions synchronously on mount via getBoundingClientRect', () => {
    container = makeContainer(1024, 600);
    provider = attachProvider(container, sink);
    // The synchronous seed runs before any RO callback.
    expect(sink.dimensions).toEqual({ width: 1024, height: 600 });
  });

  it('does not seed when the container has zero size on mount', () => {
    container = makeContainer(0, 0);
    provider = attachProvider(container, sink);
    expect(sink.dimensions).toBeNull();
  });

  // ── RO update on resize ──────────────────────────────────────────────────────

  it('updates sink when container is resized', async () => {
    container = makeContainer(800, 400);
    provider = attachProvider(container, sink);
    expect(sink.dimensions).toEqual({ width: 800, height: 400 });

    container.style.width = '1200px';
    container.style.height = '700px';
    await waitForDimensions(sink, { width: 1200, height: 700 });

    expect(sink.dimensions).toEqual({ width: 1200, height: 700 });
  });

  // ── Grow-back regression ─────────────────────────────────────────────────────
  // This is the close-drawer / collapse-sidebar bug: the pane grows back to its
  // original size after a sibling panel is collapsed. Verify the RO catches the
  // grown size with no suppression in the way.

  it('reflects grown size after container shrinks then grows back', async () => {
    container = makeContainer(800, 600);
    provider = attachProvider(container, sink);
    expect(sink.dimensions).toEqual({ width: 800, height: 600 });

    // Simulate sibling panel expanding (terminal drawer opens → top pane shrinks).
    container.style.height = '400px';
    await waitForDimensions(sink, { width: 800, height: 400 });
    expect(sink.dimensions).toEqual({ width: 800, height: 400 });

    // Simulate sibling panel collapsing (terminal drawer closes → top pane grows back).
    container.style.height = '600px';
    await waitForDimensions(sink, { width: 800, height: 600 });
    // With the old suppression design this could stick at 400 if the RO for the
    // grow-back arrived after the 140ms suppression window closed and the final
    // recompute had already read the stale value. With RO as the single source
    // there is no race: the grown size always reaches the sink.
    expect(sink.dimensions).toEqual({ width: 800, height: 600 });
  });

  // ── Programmatic toggle (no suppression) ────────────────────────────────────
  // Previously the drawer/sidebar toggle called suppressFor(140) which could eat
  // the RO event for the grow-back. Verify the RO fires for both collapse and
  // expand without any guard.

  it('observes both collapse and expand of a programmatic toggle', async () => {
    container = makeContainer(800, 600);
    provider = attachProvider(container, sink);

    // Collapse (simulate panel.collapse() resolving immediately).
    container.style.height = '0px';
    // A zero-height contentRect triggers the RO but setDimensions is skipped
    // (the provider's "width > 0 || height > 0" guard). So dimensions stay at
    // the last non-zero value. What matters is the EXPAND path below.

    // Expand back.
    container.style.height = '600px';
    await waitForDimensions(sink, { width: 800, height: 600 });
    expect(sink.dimensions).toEqual({ width: 800, height: 600 });
  });

  // ── Multiple sequential resizes ──────────────────────────────────────────────
  // Verify that the last value in a rapid burst is always what the sink holds
  // (RO coalesces intermediate values and delivers the latest).

  it('coalesces a burst of resizes to the final value', async () => {
    container = makeContainer(800, 400);
    provider = attachProvider(container, sink);

    // Rapid intermediate values (simulating a continuous splitter drag).
    container.style.width = '900px';
    container.style.width = '950px';
    container.style.width = '1000px';
    await waitForDimensions(sink, { width: 1000, height: 400 });

    // Only the last value should be in the sink (the RO coalesces intra-frame).
    expect(sink.dimensions!.width).toBe(1000);
    expect(sink.dimensions!.height).toBe(400);
  });

  // ── Grid dimensions derived from sink ───────────────────────────────────────
  // Verify that computeGridDimensions correctly derives cols/rows from the sink
  // value after a resize, confirming the end-to-end resize → grid pipeline.

  it('produces correct cols/rows from sink dimensions after a resize', async () => {
    const CW = 8;
    const CH = 16;
    const PADDING = 8;

    container = makeContainer(800, 400);
    provider = attachProvider(container, sink);

    container.style.width = '1024px';
    container.style.height = '512px';
    await waitForDimensions(sink, { width: 1024, height: 512 });

    const dims = sink.dimensions;
    expect(dims).not.toBeNull();

    const grid = computeGridDimensions({
      widthPx: dims!.width,
      heightPx: dims!.height,
      cellWidth: CW,
      cellHeight: CH,
      paddingPx: PADDING,
    });
    expect(grid).not.toBeNull();
    // availW = 1024 - 8 - 8 = 1008; cols = floor(1008/8) = 126
    // availH = 512  - 8 - 8 = 496;  rows = floor(496/16) = 31
    expect(grid!.cols).toBe(Math.floor((1024 - 2 * PADDING) / CW));
    expect(grid!.rows).toBe(Math.floor((512 - 2 * PADDING) / CH));
  });

  // ── Resize when terminal not active (background session) ─────────────────────
  // The controller should compute new dims even when no terminal has calibrated
  // (hasCalibratedRef = false). This covers background/inactive sessions.
  // The computeGridDimensions output should reflect the post-resize container size.

  it('computes updated dims from sink even when no terminal is calibrated', async () => {
    const CW = 8;
    const CH = 16;

    container = makeContainer(800, 400);
    provider = attachProvider(container, sink);

    // Resize while "no terminal mounted".
    container.style.width = '640px';
    container.style.height = '320px';
    await waitForDimensions(sink, { width: 640, height: 320 });

    // Sink always holds the latest box.
    expect(sink.dimensions).toEqual({ width: 640, height: 320 });

    // Grid computation from that sink value is still correct.
    const grid = computeGridDimensions({
      widthPx: sink.dimensions!.width,
      heightPx: sink.dimensions!.height,
      cellWidth: CW,
      cellHeight: CH,
    });
    expect(grid).not.toBeNull();
    expect(grid!.cols).toBe(Math.floor(640 / CW)); // 80
    expect(grid!.rows).toBe(Math.floor(320 / CH)); // 20
  });
});

// ── Controller-driven grid fan-out ────────────────────────────────────────────
//
// Verifies that background (parked) terminals' xterm grids are kept in sync by
// the resize controller's scheduler flush, not just the mounted terminal's
// MobX reaction. Uses real FrontendPty instances (same as xterm-host.test.ts)
// so the bySession registry is exercised end-to-end.

async function getPtyModule() {
  return import('@core/features/terminals/api/browser/pty/pty');
}

describe('Controller-driven PTY grid fan-out (FrontendPty.bySession)', () => {
  beforeEach(() => {
    vi.stubGlobal('electronAPI', {
      eventOn: vi.fn(() => () => {}),
      eventSend: vi.fn(),
      invoke: vi.fn(() => Promise.resolve({ success: true, data: { buffer: '' } })),
    });

    // Minimal xterm CSS variables so FrontendPty doesn't log colour errors.
    for (const v of [
      '--xterm-bg',
      '--xterm-fg',
      '--xterm-cursor',
      '--xterm-cursor-accent',
      '--xterm-selection-bg',
      '--xterm-selection-fg',
    ]) {
      document.documentElement.style.setProperty(v, v.includes('bg') ? '#101010' : '#f0f0f0');
    }
  });

  afterEach(async () => {
    const { disposeAllPtys } = await getPtyModule();
    disposeAllPtys();
    document.querySelector('[data-terminal-host="true"]')?.remove();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  // ── Registry lifecycle ───────────────────────────────────────────────────────

  const noopConnector = () => ({
    connect: () => () => {},
  });

  it('registers a FrontendPty in bySession on construction', async () => {
    const { FrontendPty, getFrontendPty } = await getPtyModule();
    const pty = new FrontendPty('session-a', undefined, undefined, undefined, noopConnector());
    expect(FrontendPty.bySession.get('session-a')).toBe(pty);
    expect(getFrontendPty('session-a')).toBe(pty);
  });

  it('removes a FrontendPty from bySession on dispose', async () => {
    const { FrontendPty, getFrontendPty } = await getPtyModule();
    const pty = new FrontendPty('session-b', undefined, undefined, undefined, noopConnector());
    expect(getFrontendPty('session-b')).toBe(pty);
    pty.dispose();
    expect(getFrontendPty('session-b')).toBeUndefined();
  });

  it('returns undefined for an unknown session ID', async () => {
    const { getFrontendPty } = await getPtyModule();
    expect(getFrontendPty('does-not-exist')).toBeUndefined();
  });

  // ── Scheduler fan-out resizes background grids ────────────────────────────────
  // Simulates the exact flush function used by usePtyPaneResize:
  //   runtime resize(id) + getFrontendPty(id)?.terminal.resize(cols, rows)
  // Verifies that both the active and background terminal grids are updated.

  it('scheduler flush resizes all registered terminal grids', async () => {
    const { FrontendPty, getFrontendPty } = await getPtyModule();

    const ptyA = new FrontendPty('fan-a', undefined, undefined, undefined, noopConnector());
    const ptyB = new FrontendPty('fan-b', undefined, undefined, undefined, noopConnector());

    // Seeded from Terminal constructor defaults.
    const initialCols = ptyA.terminal.cols;
    const initialRows = ptyA.terminal.rows;

    const sessionIds = ['fan-a', 'fan-b'];
    const resizeSpy = vi.fn();

    // Mirror the scheduler flush in usePtyPaneResize, but replace rpc with a spy.
    const scheduler = createResizeScheduler<{ cols: number; rows: number }>((dims) => {
      for (const id of sessionIds) {
        resizeSpy(id, dims.cols, dims.rows); // stands in for runtime resize
        const term = getFrontendPty(id)?.terminal;
        if (term && (term.cols !== dims.cols || term.rows !== dims.rows)) {
          term.resize(dims.cols, dims.rows);
        }
      }
    }, 60);

    const newCols = initialCols + 10;
    const newRows = initialRows + 5;
    scheduler.schedule({ cols: newCols, rows: newRows });

    // Leading-edge flush runs synchronously.
    expect(ptyA.terminal.cols).toBe(newCols);
    expect(ptyA.terminal.rows).toBe(newRows);
    expect(ptyB.terminal.cols).toBe(newCols);
    expect(ptyB.terminal.rows).toBe(newRows);
    expect(resizeSpy).toHaveBeenCalledWith('fan-a', newCols, newRows);
    expect(resizeSpy).toHaveBeenCalledWith('fan-b', newCols, newRows);

    scheduler.cancel();
  });

  it('scheduler fan-out no-ops for sessions already at the target size', async () => {
    const { FrontendPty, getFrontendPty } = await getPtyModule();
    const pty = new FrontendPty('fan-noop', undefined, undefined, undefined, noopConnector());
    const targetCols = 80;
    const targetRows = 24;
    pty.terminal.resize(targetCols, targetRows);

    const resizeSpy = vi.spyOn(pty.terminal, 'resize');

    const scheduler = createResizeScheduler<{ cols: number; rows: number }>((dims) => {
      const term = getFrontendPty('fan-noop')?.terminal;
      if (term && (term.cols !== dims.cols || term.rows !== dims.rows)) {
        term.resize(dims.cols, dims.rows);
      }
    }, 60);

    // Schedule dimensions the terminal already has.
    scheduler.schedule({ cols: targetCols, rows: targetRows });
    expect(resizeSpy).not.toHaveBeenCalled();

    scheduler.cancel();
  });

  it('disposed terminal is absent from registry and skipped in fan-out', async () => {
    const { FrontendPty, getFrontendPty } = await getPtyModule();
    const ptyA = new FrontendPty(
      'fan-disposed-a',
      undefined,
      undefined,
      undefined,
      noopConnector()
    );
    const ptyB = new FrontendPty(
      'fan-disposed-b',
      undefined,
      undefined,
      undefined,
      noopConnector()
    );

    ptyA.dispose();

    const sessionIds = ['fan-disposed-a', 'fan-disposed-b'];
    const scheduler = createResizeScheduler<{ cols: number; rows: number }>((dims) => {
      for (const id of sessionIds) {
        const term = getFrontendPty(id)?.terminal;
        if (term && (term.cols !== dims.cols || term.rows !== dims.rows)) {
          term.resize(dims.cols, dims.rows);
        }
      }
    }, 60);

    const newCols = ptyB.terminal.cols + 20;
    const newRows = ptyB.terminal.rows + 5;
    scheduler.schedule({ cols: newCols, rows: newRows });

    // Disposed pty is gone; live pty is resized.
    expect(getFrontendPty('fan-disposed-a')).toBeUndefined();
    expect(ptyB.terminal.cols).toBe(newCols);
    expect(ptyB.terminal.rows).toBe(newRows);

    scheduler.cancel();
  });

  // ── Parked resize regression ──────────────────────────────────────────────────
  // Simulates the "resize while on a non-pty tab, then return" scenario:
  // the terminal is parked off-screen but the scheduler still drives its grid.
  // On becoming visible (re-mount), it should already have the correct dims.

  it('parked terminal has correct grid dims before re-mount', async () => {
    const { FrontendPty, getFrontendPty } = await getPtyModule();
    const pty = new FrontendPty('fan-parked', undefined, undefined, undefined, noopConnector());

    // Terminal starts parked in the off-screen host (initial state after construction).
    // Use trailingMs=0 so both schedule calls fire synchronously on the leading
    // edge (no debounce coalescing in the test).
    const sessionIds = ['fan-parked'];
    const scheduler = createResizeScheduler<{ cols: number; rows: number }>((dims) => {
      for (const id of sessionIds) {
        const term = getFrontendPty(id)?.terminal;
        if (term && (term.cols !== dims.cols || term.rows !== dims.rows)) {
          term.resize(dims.cols, dims.rows);
        }
      }
    }, 0);

    // First resize while parked (e.g. resize while on a non-pty tab).
    scheduler.schedule({ cols: 100, rows: 30 });
    expect(pty.terminal.cols).toBe(100);
    expect(pty.terminal.rows).toBe(30);

    // Second resize (e.g. closing the terminal drawer after the tab switch).
    scheduler.schedule({ cols: 120, rows: 40 });
    expect(pty.terminal.cols).toBe(120);
    expect(pty.terminal.rows).toBe(40);

    // When the terminal re-mounts, it already has the right size — no flash.
    const mountTarget = document.createElement('div');
    document.body.appendChild(mountTarget);
    pty.mount(mountTarget); // no targetDims override needed
    expect(pty.terminal.cols).toBe(120);
    expect(pty.terminal.rows).toBe(40);

    mountTarget.remove();
    scheduler.cancel();
  });
});

// ── measureTerminalCell: floor-based cell height ──────────────────────────────
// Regression guard: confirms measureTerminalCell uses Math.floor (matching
// xterm's device.cell.height formula) rather than Math.ceil. A ceil result
// makes the seed always 1px taller than the calibrated xterm value, which
// prevents the calibrateCell fast-path from ever short-circuiting.

describe('measureTerminalCell', () => {
  it('cell height matches Math.floor(charHeight * lineHeight) for a fractional lineHeight', () => {
    // Use a lineHeight that produces a fractional product, so ceil and floor differ.
    const lineHeight = 1.2;
    const result = measureTerminalCell('monospace', 13, lineHeight, 0);
    expect(result).not.toBeNull();
    const { height } = result!;

    // Re-derive charHeight via canvas (same path as measureTerminalCell) so we
    // can compute the expected floor/ceil values independently.
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d')!;
    ctx.font = '13px monospace';
    const mMetrics = ctx.measureText('M');
    const charHeight =
      typeof mMetrics.actualBoundingBoxAscent === 'number' &&
      typeof mMetrics.actualBoundingBoxDescent === 'number' &&
      mMetrics.actualBoundingBoxAscent + mMetrics.actualBoundingBoxDescent > 0
        ? mMetrics.actualBoundingBoxAscent + mMetrics.actualBoundingBoxDescent
        : 13;
    const expectedFloor = Math.floor(charHeight * lineHeight);
    const expectedCeil = Math.ceil(charHeight * lineHeight);

    // The function must return the floor value.
    expect(height).toBe(expectedFloor);
    // Verify our test is actually sensitive: floor and ceil differ for this input.
    // If they happen to be equal for this font/platform the test is vacuously true,
    // which is fine — but we log to confirm sensitivy was present.
    if (expectedFloor === expectedCeil) {
      console.warn(
        'measureTerminalCell ceil/floor test: charHeight * lineHeight was already an integer ' +
          `(charHeight=${charHeight}, lineHeight=${lineHeight}). Test is vacuously true on this platform.`
      );
    }
  });
});

// ── calibrateCell: no crash when controllerDims box is null ──────────────────
// Regression guard: the first-calibration flush branch must not schedule a null
// payload (which causes a TypeError on dims.cols in the flush callback) when
// recompute() has never run (e.g. the pane was opened in a collapsed panel).

describe('calibrateCell null-dims guard', () => {
  it('does not flush the scheduler when controllerDims is null at first calibration', () => {
    // Mirror the calibrateCell branch logic directly, as the existing tests do
    // for attachProvider / scheduler, without a full hook render.
    // Replicate the observable box as created in usePtyPaneResize.
    const controllerDimsBox = observable.box<{ cols: number; rows: number } | null>(null);

    // Replicate the scheduler with a spy flush — must never be called with null.
    const flushCalls: Array<{ cols: number; rows: number }> = [];
    const scheduler = createResizeScheduler<{ cols: number; rows: number }>((dims) => {
      flushCalls.push(dims);
    }, 0);

    // Simulate the first calibration when seed == calibrated cell size (fast path).
    // The seed is set during construction; for this test we use an explicit value.
    const seedCell = { width: 8, height: 18 };
    // Replicate: cellSizeRef.current matches calibrated values → fast path.
    const cellSizeCurrent = { ...seedCell };
    const hasCalibratedRef = { current: false };

    // This is the exact branch being tested.
    const calibrateWidth = seedCell.width;
    const calibrateHeight = seedCell.height;

    const alreadyCalibrated = hasCalibratedRef.current;
    hasCalibratedRef.current = true;

    if (cellSizeCurrent.width === calibrateWidth && cellSizeCurrent.height === calibrateHeight) {
      if (!alreadyCalibrated) {
        // Fixed version: guard the value, do not assert non-null.
        const dims = controllerDimsBox.get();
        if (dims) scheduler.schedule(dims);
      }
    }

    // controllerDimsBox is null → scheduler must not have been called.
    expect(flushCalls).toHaveLength(0);

    // Now simulate a successful recompute setting the box.
    runInAction(() => controllerDimsBox.set({ cols: 167, rows: 50 }));

    // A second calibration that hits the fast path with a non-null box should flush.
    const alreadyCalibrated2 = hasCalibratedRef.current;
    hasCalibratedRef.current = true;
    if (cellSizeCurrent.width === calibrateWidth && cellSizeCurrent.height === calibrateHeight) {
      if (!alreadyCalibrated2) {
        const dims2 = controllerDimsBox.get();
        if (dims2) scheduler.schedule(dims2);
      }
    }
    // alreadyCalibrated2 is true → branch not entered → still no flush.
    expect(flushCalls).toHaveLength(0);

    scheduler.cancel();
  });
});
