import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  invalidateCellMetricsCache,
  measureDimensions,
  measureTerminalCell,
} from '@core/features/terminals/api/browser/pty/pty-dimensions';

// ── measureDimensions (node-safe, uses mock window/getComputedStyle) ──────────

describe('measureDimensions', () => {
  it('returns null when cellWidth is 0', () => {
    const el = { style: {} } as unknown as HTMLElement;
    vi.stubGlobal('window', {
      getComputedStyle: () => ({ width: '800', height: '400' }),
    });
    expect(measureDimensions(el, 0, 16)).toBeNull();
    vi.unstubAllGlobals();
  });

  it('returns null when cellHeight is 0', () => {
    const el = { style: {} } as unknown as HTMLElement;
    vi.stubGlobal('window', {
      getComputedStyle: () => ({ width: '800', height: '400' }),
    });
    expect(measureDimensions(el, 8, 0)).toBeNull();
    vi.unstubAllGlobals();
  });

  it('computes cols and rows correctly', () => {
    const el = { style: {} } as unknown as HTMLElement;
    vi.stubGlobal('window', {
      getComputedStyle: () => ({ width: '800', height: '400' }),
    });
    expect(measureDimensions(el, 8, 16)).toEqual({ cols: 100, rows: 25 });
    vi.unstubAllGlobals();
  });
});

// ── measureTerminalCell — guard conditions (no real DOM in node env) ──────────

describe('measureTerminalCell', () => {
  afterEach(() => {
    invalidateCellMetricsCache();
    vi.unstubAllGlobals();
  });

  it('returns null when document is unavailable', () => {
    // Node environment: document is not defined.
    expect(typeof document).toBe('undefined');
    expect(measureTerminalCell('monospace', 13)).toBeNull();
  });

  it('returns null when the canvas context is unavailable', () => {
    vi.stubGlobal('document', {
      createElement: () => ({ getContext: () => null }),
    });
    vi.stubGlobal('window', { devicePixelRatio: 1 });
    expect(measureTerminalCell('monospace', 13)).toBeNull();
  });

  it('returns positive width and height from a canvas stub', () => {
    const mockCtx = {
      font: '',
      measureText: (text: string) => ({
        width: text === 'W' ? 8 : 7,
        actualBoundingBoxAscent: 10,
        actualBoundingBoxDescent: 3,
      }),
    };
    vi.stubGlobal('document', {
      createElement: () => ({ getContext: () => mockCtx }),
    });
    vi.stubGlobal('window', { devicePixelRatio: 1 });
    const result = measureTerminalCell('monospace', 13);
    expect(result).not.toBeNull();
    expect(result!.width).toBeGreaterThan(0);
    expect(result!.height).toBeGreaterThan(0);
  });

  it('uses ceil(width) for cell width and ceil(ascent+descent) for cell height', () => {
    const mockCtx = {
      font: '',
      measureText: (text: string) => ({
        width: text === 'W' ? 7.6 : 6,
        actualBoundingBoxAscent: 10.2,
        actualBoundingBoxDescent: 2.8,
      }),
    };
    vi.stubGlobal('document', {
      createElement: () => ({ getContext: () => mockCtx }),
    });
    vi.stubGlobal('window', { devicePixelRatio: 1 });
    const result = measureTerminalCell('monospace', 13);
    expect(result).toEqual({ width: 8, height: 13 }); // ceil(7.6)=8, ceil(10.2+2.8)=ceil(13)=13
  });

  it('caches the result for the same (fontFamily, fontSize, dpr)', () => {
    let callCount = 0;
    const mockCtx = {
      font: '',
      measureText: () => {
        callCount++;
        return { width: 8, actualBoundingBoxAscent: 10, actualBoundingBoxDescent: 3 };
      },
    };
    vi.stubGlobal('document', {
      createElement: () => ({ getContext: () => mockCtx }),
    });
    vi.stubGlobal('window', { devicePixelRatio: 1 });

    measureTerminalCell('monospace', 13);
    const before = callCount;
    measureTerminalCell('monospace', 13);
    // Canvas should NOT be queried again for the same inputs.
    expect(callCount).toBe(before);
  });

  it('recomputes after invalidateCellMetricsCache()', () => {
    let callCount = 0;
    const mockCtx = {
      font: '',
      measureText: () => {
        callCount++;
        return { width: 8, actualBoundingBoxAscent: 10, actualBoundingBoxDescent: 3 };
      },
    };
    vi.stubGlobal('document', {
      createElement: () => ({ getContext: () => mockCtx }),
    });
    vi.stubGlobal('window', { devicePixelRatio: 1 });

    measureTerminalCell('monospace', 13);
    const before = callCount;
    invalidateCellMetricsCache();
    measureTerminalCell('monospace', 13);
    expect(callCount).toBeGreaterThan(before);
  });

  it('falls back to fontSize when bounding box metrics are zero', () => {
    const mockCtx = {
      font: '',
      measureText: () => ({
        width: 8,
        actualBoundingBoxAscent: 0,
        actualBoundingBoxDescent: 0,
      }),
    };
    vi.stubGlobal('document', {
      createElement: () => ({ getContext: () => mockCtx }),
    });
    vi.stubGlobal('window', { devicePixelRatio: 1 });
    // When ascent+descent = 0, falls back to fontSize (13), ceil(13) = 13.
    const result = measureTerminalCell('monospace', 13);
    expect(result!.height).toBe(13);
  });
});
