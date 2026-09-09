/**
 * Browser-mode tests for measureDimensions() and measureTerminalCell().
 *
 * These run in a real Chromium process via Playwright so getComputedStyle
 * reflects genuine CSS layout and canvas measurements are accurate.
 */
import { afterEach, describe, expect, it } from 'vitest';
import {
  invalidateCellMetricsCache,
  measureDimensions,
  measureTerminalCell,
} from '@core/features/terminals/api/browser/pty/pty-dimensions';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeContainer(width: string, height: string): HTMLDivElement {
  const el = document.createElement('div');
  el.style.position = 'absolute';
  el.style.width = width;
  el.style.height = height;
  document.body.appendChild(el);
  return el;
}

// Cell sizes used throughout the suite.  Chosen to give clean integer results.
const CW = 8; // cell width  (px)
const CH = 16; // cell height (px)

// ── Suite ─────────────────────────────────────────────────────────────────────

describe('measureDimensions', () => {
  let container: HTMLDivElement;

  afterEach(() => {
    container?.remove();
  });

  // ── Null / guard conditions ────────────────────────────────────────────────

  it('returns null when cellWidth is 0', () => {
    container = makeContainer('800px', '400px');
    expect(measureDimensions(container, 0, CH)).toBeNull();
  });

  it('returns null when cellHeight is 0', () => {
    container = makeContainer('800px', '400px');
    expect(measureDimensions(container, CW, 0)).toBeNull();
  });

  it('returns null when computed height is 0', () => {
    // height: 0 is the height-chain failure mode (collapsed flex child).
    container = makeContainer('800px', '0px');
    expect(measureDimensions(container, CW, CH)).toBeNull();
  });

  it('returns null when container has no explicit size (auto / 0)', () => {
    container = document.createElement('div');
    document.body.appendChild(container);
    // No width/height set — auto resolves to 0px for an absolutely-positioned div.
    container.style.position = 'absolute';
    expect(measureDimensions(container, CW, CH)).toBeNull();
  });

  // ── Normal calculation ─────────────────────────────────────────────────────

  it('computes cols and rows from a plain sized container', () => {
    container = makeContainer('800px', '400px');
    const dims = measureDimensions(container, CW, CH);
    expect(dims).toEqual({
      cols: Math.floor(800 / CW), // 100
      rows: Math.floor(400 / CH), // 25
    });
  });

  it('subtracts scrollbarWidth from available width', () => {
    container = makeContainer('800px', '400px');
    const SCROLLBAR = 15;
    const dims = measureDimensions(container, CW, CH, SCROLLBAR);
    expect(dims).toEqual({
      cols: Math.floor((800 - SCROLLBAR) / CW), // 98
      rows: Math.floor(400 / CH), // 25
    });
  });

  it('subtracts per-side padding from the respective axis', () => {
    container = makeContainer('800px', '400px');
    // bottom-only extra inset of 32px (e.g. a context bar).
    const dims = measureDimensions(container, CW, CH, 0, 0, { bottom: 32 });
    expect(dims).toEqual({
      cols: Math.floor(800 / CW), // 100 — width unaffected
      rows: Math.floor((400 - 32) / CH), // 23
    });
  });

  it('combines paddingPx and per-side padding additively', () => {
    container = makeContainer('800px', '400px');
    // paddingPx = 8 → subtracts 8 from all sides; extra bottom = 32
    // availW = 800 - 8 - 8 = 784; availH = 400 - 8 - (8 + 32) = 352
    const dims = measureDimensions(container, CW, CH, 0, 8, { bottom: 32 });
    expect(dims).toEqual({
      cols: Math.floor(784 / CW), // 98
      rows: Math.floor(352 / CH), // 22
    });
  });

  it('clamps cols to MINIMUM_COLS (2) when container is very narrow', () => {
    container = makeContainer('3px', '400px'); // 3 / 8 = 0 → clamp to 2
    const dims = measureDimensions(container, CW, CH);
    expect(dims).not.toBeNull();
    expect(dims!.cols).toBe(2);
  });

  it('clamps rows to MINIMUM_ROWS (1) when container is shorter than one cell', () => {
    container = makeContainer('800px', '10px'); // 10 / 16 = 0 → clamp to 1
    const dims = measureDimensions(container, CW, CH);
    expect(dims).not.toBeNull();
    expect(dims!.rows).toBe(1);
  });

  it('floors fractional cell width correctly', () => {
    // 800 / 8.4 = 95.23... → floor → 95
    container = makeContainer('800px', '400px');
    const dims = measureDimensions(container, 8.4, CH);
    expect(dims).not.toBeNull();
    expect(dims!.cols).toBe(Math.floor(800 / 8.4));
  });

  it('floors fractional cell height correctly', () => {
    // 400 / 16.5 = 24.24... → floor → 24
    container = makeContainer('800px', '400px');
    const dims = measureDimensions(container, CW, 16.5);
    expect(dims).not.toBeNull();
    expect(dims!.rows).toBe(Math.floor(400 / 16.5));
  });

  // ── Height-chain integration ───────────────────────────────────────────────
  // Validates the CSS layout in pane-dimension-provider.tsx:
  //   flex parent → flex child (flex:1) → PaneDimensionProvider wrapper (flex:1 1 0%) → container
  // The container must receive real pixel height via CSS flex distribution.

  it('resolves height correctly inside a flex column chain', () => {
    const PARENT_H = 600;
    const TABS_H = 40;
    const TERMINAL_H = PARENT_H - TABS_H; // 560

    // Outer panel: flex column, fixed height
    const panel = document.createElement('div');
    panel.style.position = 'absolute';
    panel.style.width = '1200px';
    panel.style.height = `${PARENT_H}px`;
    panel.style.display = 'flex';
    panel.style.flexDirection = 'column';
    document.body.appendChild(panel);

    // Tabs row: shrink-0
    const tabs = document.createElement('div');
    tabs.style.flex = 'none';
    tabs.style.height = `${TABS_H}px`;
    panel.appendChild(tabs);

    // Terminal area: flex:1, flex container (the panel.tsx fix)
    const terminalArea = document.createElement('div');
    terminalArea.style.flex = '1 1 0%';
    terminalArea.style.minHeight = '0';
    terminalArea.style.display = 'flex';
    terminalArea.style.flexDirection = 'column';
    panel.appendChild(terminalArea);

    // PaneDimensionProvider wrapper: flex:1 1 0%
    container = document.createElement('div');
    container.style.flex = '1 1 0%';
    container.style.height = '100%';
    container.style.minHeight = '0';
    container.style.minWidth = '0';
    terminalArea.appendChild(container);

    const dims = measureDimensions(container, CW, CH);
    expect(dims).not.toBeNull();
    expect(dims!.rows).toBe(Math.floor(TERMINAL_H / CH)); // 35
    expect(dims!.cols).toBe(Math.floor(1200 / CW)); // 150

    panel.remove();
  });

  it('returns null when the flex chain is broken (non-flex parent)', () => {
    // Simulates the OLD bug: terminal-area div is not a flex container so
    // the wrapper's flex:1 has no effect and it collapses to auto height (0).
    const panel = document.createElement('div');
    panel.style.position = 'absolute';
    panel.style.width = '1200px';
    panel.style.height = '600px';
    // NOT a flex container ← this is the pre-fix state
    document.body.appendChild(panel);

    container = document.createElement('div');
    container.style.flex = '1 1 0%';
    container.style.minHeight = '0';
    panel.appendChild(container);

    // Without a flex parent, flex:1 is ignored and height resolves to 0.
    expect(measureDimensions(container, CW, CH)).toBeNull();

    panel.remove();
  });
});

// ── measureTerminalCell — real canvas measurements ───────────────────────────

describe('measureTerminalCell', () => {
  afterEach(() => {
    invalidateCellMetricsCache();
  });

  it('returns positive cell width and height for a monospace font', () => {
    const result = measureTerminalCell('monospace', 13);
    expect(result).not.toBeNull();
    expect(result!.width).toBeGreaterThan(0);
    expect(result!.height).toBeGreaterThan(0);
  });

  it('returns larger cells for a larger font size', () => {
    const small = measureTerminalCell('monospace', 13);
    invalidateCellMetricsCache();
    const large = measureTerminalCell('monospace', 20);
    expect(small).not.toBeNull();
    expect(large).not.toBeNull();
    // Both width and height should grow with font size.
    expect(large!.height).toBeGreaterThanOrEqual(small!.height);
    expect(large!.width).toBeGreaterThanOrEqual(small!.width);
  });

  it('caches the result for the same inputs', () => {
    const a = measureTerminalCell('monospace', 13);
    const b = measureTerminalCell('monospace', 13);
    // Both calls should return the same (cached) object values.
    expect(a).toEqual(b);
  });

  it('returns different values after invalidateCellMetricsCache() with a different fontSize', () => {
    const a = measureTerminalCell('monospace', 13);
    invalidateCellMetricsCache();
    const b = measureTerminalCell('monospace', 20);
    expect(a).not.toBeNull();
    expect(b).not.toBeNull();
    // Cell height must differ between 13px and 20px.
    expect(b!.height).not.toBe(a!.height);
  });
});
