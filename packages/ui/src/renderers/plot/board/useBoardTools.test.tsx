import { act, cleanup, renderHook } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, expect, it } from 'vitest';
import { createBoardIndex } from '@text-to-cad/core/lib/board2d/boardIndex.js';
import { BOARD_OVERLAY_COLORS } from '@text-to-cad/core/lib/board2d/boardOverlay.js';
import { PLOT_TOOL, PLOT_TOOL_MODES, escapePlot } from '../../../../dist/renderers/plot/tools.js';
import { useBoardSelection } from '../../../../dist/renderers/plot/board/useBoardSelection.js';
import { useBoardPicking } from '../../../../dist/renderers/plot/board/useBoardPicking.js';
import { useBoardIsolation } from '../../../../dist/renderers/plot/board/useBoardIsolation.js';

// A board's tool composed as `PlotRenderer.jsx` composes it, over a 40 x 30 mm board drawn at
// 10 px/mm from the pane's corner: a press at (x, y) px lands on page (x / 10, y / 10) mm. What a
// person does with it — a press, Escape, a tree row's hover and eye, a new revision — is decided
// here; the pixels are the browser suite's.
const square = (cx: number, cy: number, w: number, h: number) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const board = (parts = ['R1']) => ({
  origin: [5, 25], nets: [{ name: 'VIN', class: '' }, { name: 'GND', class: '' }],
  parts: parts.map((ref) => ({ ref, value: '10k', footprint: 'R_0603', side: 'top', at: [15, 20], rotation: 0, fields: {}, outline: square(15, 20, 3, 1.4) })),
  pads: parts.includes('R1') ? [
    { part: 'R1', number: '1', name: '', net: 'VIN', type: 'passive', side: 'top', at: [14.175, 20], polygon: square(14.175, 20, 0.8, 0.95) },
    { part: 'R1', number: '2', name: '', net: 'GND', type: 'passive', side: 'top', at: [15.825, 20], polygon: square(15.825, 20, 0.8, 0.95) },
  ] : [],
  tracks: [], vias: [], zones: [], holes: [{ at: [3, 3], diameter: 2 }, { at: [37, 27], diameter: 2 }], outline: [],
});
const SHEET = { x: 0, y: 0, width: 40, height: 30 };
const indexOf = (data = board()) => createBoardIndex(data, { x: SHEET.x, y: SHEET.y });

function useTools({ index, restored }: { index: ReturnType<typeof indexOf>, restored: string[] }) {
  const [view] = useState(() => ({
    transformRef: { current: { scale: 10, offsetX: 0, offsetY: 0 } }, canvasRef: { current: null }, requestPaint: () => {},
    layer: null as null | { overlay: (ctx: unknown, frame: unknown) => void, picking: Record<string, (...args: any[]) => any> },
    setLayer(layer: any) { view.layer = layer; },
  }));
  const [toolMode, setToolMode] = useState(PLOT_TOOL_MODES.defaultMode);
  const selectTool = (mode: string) => setToolMode((current: string) => PLOT_TOOL_MODES.next(current, mode));
  const selection = useBoardSelection({ index, requestPaint: view.requestPaint });
  const isolation = useBoardIsolation({ index, restored });
  const copied: string[][] = [];
  useBoardPicking({ view, index, sheet: SHEET, selection, isolated: isolation.resolved, onCopy: (selectors: string[]) => copied.push(selectors) });
  return { view, toolMode, selectTool, selection, isolation, copied, escape: () => escapePlot({ selection }) };
}
function mount(index = indexOf(), restored: string[] = []) {
  return renderHook(({ index: shown }) => useTools({ index: shown, restored }), { initialProps: { index } });
}
type View = ReturnType<typeof mount>;
const tap = (view: View, x: number, y: number, event: Record<string, boolean> = {}) => act(() => { view.result.current.view.layer!.picking.onTap({ x, y }, event); });
// The overlay's strokes and fills, as one paint of the frame sets them.
function paint(view: View) {
  const styles: string[] = [];
  const ctx = new Proxy({} as Record<string | symbol, unknown>, {
    get: (target, key) => (key in target ? target[key] : () => {}),
    set: (target, key, value) => { if (key === 'strokeStyle' || key === 'fillStyle') styles.push(String(value)); target[key] = value; return true; },
  });
  view.result.current.view.layer!.overlay(ctx, { transform: { scale: 10, offsetX: 0, offsetY: 0 }, pixelRatio: 1, width: 400, height: 300 });
  return styles;
}

afterEach(cleanup);

it('Select is the one tool, and cannot be put down: a press on it, or on Draw or Measure, leaves it in hand', () => {
  const view = mount();
  expect(PLOT_TOOL).toEqual({ SELECT: 'select' });
  for (const asked of [PLOT_TOOL.SELECT, 'draw', 'measure', '']) {
    act(() => view.result.current.selectTool(asked));
    expect(view.result.current.toolMode).toBe(PLOT_TOOL.SELECT);
  }
});

it('a press selects a pad, a shift-press adds its neighbour, bare board clears, and a double-click copies', () => {
  const view = mount();
  tap(view, 141.75, 200);
  expect(view.result.current.selection.selection).toEqual(['#R1.1']);
  tap(view, 158.25, 200, { shiftKey: true });
  expect(view.result.current.selection.selection).toEqual(['#R1.1', '#R1.2']);
  tap(view, 300, 50);
  expect(view.result.current.selection.selection).toEqual([]);
  let copied = false;
  act(() => { copied = view.result.current.view.layer!.picking.onDoubleTap({ x: 141.75, y: 200 }); });
  expect(copied).toBe(true);
  expect(view.result.current.selection.selection).toEqual(['#R1.1']);
  // On bare board a double-click is not spent here: the view fits.
  act(() => { copied = view.result.current.view.layer!.picking.onDoubleTap({ x: 300, y: 50 }); });
  expect(copied).toBe(false);
});

it('Escape clears the selection, and spends nothing with none', () => {
  const view = mount();
  act(() => view.result.current.selection.select(['#R1.2']));
  expect(view.result.current.selection.active).toBe(true);
  act(() => { expect(view.result.current.escape()).toBe(true); });
  expect(view.result.current.selection.selection).toEqual([]);
  act(() => { expect(view.result.current.escape()).toBe(false); });
});

it('a selection keeps only what the board has, and survives a rebuild for what still names something', () => {
  const view = mount();
  act(() => view.result.current.selection.select(['#R1.2', '#U9', '#@x1y2']));
  expect(view.result.current.selection.selection).toEqual(['#R1.2', '#@x1y2']);
  view.rerender({ index: indexOf(board(['C1'])) });
  expect(view.result.current.selection.selection).toEqual(['#@x1y2']);
});

it('a capture leaves out the hover: the view is drawn without it once dropped', () => {
  const view = mount();
  act(() => view.result.current.view.layer!.picking.onHover({ x: 141, y: 200 }, {}));
  expect(paint(view)).toContain(BOARD_OVERLAY_COLORS.hover);
  view.result.current.selection.dropHover();
  expect(paint(view)).not.toContain(BOARD_OVERLAY_COLORS.hover);
});

it('a tree row under the pointer lights what it names on the canvas, and puts it out as the pointer leaves', () => {
  const view = mount();
  expect(paint(view)).not.toContain(BOARD_OVERLAY_COLORS.hover);
  act(() => view.result.current.selection.hover('#net:VIN'));
  expect(paint(view)).toContain(BOARD_OVERLAY_COLORS.hover);
  act(() => view.result.current.selection.hover(null));
  expect(paint(view)).not.toContain(BOARD_OVERLAY_COLORS.hover);
  // A group row names nothing: it lights nothing.
  act(() => view.result.current.selection.hover('#U9'));
  expect(paint(view)).not.toContain(BOARD_OVERLAY_COLORS.hover);
});

it('an eye isolates a part or a net: the rest steps back, and a second press lets it back in', () => {
  const view = mount();
  act(() => view.result.current.isolation.toggle('#R1'));
  act(() => view.result.current.isolation.toggle('#net:GND'));
  expect(view.result.current.isolation.isolated).toEqual(['#R1', '#net:GND']);
  const styles = paint(view);
  expect(styles).toContain(BOARD_OVERLAY_COLORS.dim);
  expect(styles).toContain(BOARD_OVERLAY_COLORS.hover);
  act(() => view.result.current.isolation.toggle('#R1'));
  act(() => view.result.current.isolation.toggle('#net:GND'));
  expect(view.result.current.isolation.isolated).toEqual([]);
  expect(paint(view)).not.toContain(BOARD_OVERLAY_COLORS.dim);
});

it('what is isolated survives a rebuild by its references, and what the new revision lacks is dropped', () => {
  // Restored from the file's view: one part the board has, and one it never had.
  const view = mount(indexOf(), ['#R1', '#U9', '#net:VIN']);
  expect(view.result.current.isolation.isolated).toEqual(['#R1', '#net:VIN']);
  // A rebuild that took R1 off the board keeps the net.
  view.rerender({ index: indexOf(board(['C1'])) });
  expect(view.result.current.isolation.isolated).toEqual(['#net:VIN']);
  act(() => view.result.current.isolation.toggle('#C1'));
  expect(view.result.current.isolation.isolated).toEqual(['#net:VIN', '#C1']);
});
