import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import AnnotationOverlay from '../../../../../dist/renderers/kit/tools/annotate/AnnotationOverlay.js';
import { ViewerHostContext } from '../../../../../dist/host/context.js';
import { testHost } from '../../../../../dist/host/testing/host.js';

// Projecting needs a WebGL scene: here a mark goes into the annotation as it was made.
const projected = vi.hoisted(() => ({ calls: [] as unknown[][], fills: [] as any[][], screen: [] as any[] }));
vi.mock('../../../../../dist/renderers/kit/tools/annotate/annotation3d.js', () => ({
  projectAnnotations: (...args: unknown[]) => { projected.calls.push(args); return args[1]; },
  annotationsOnScreen: () => projected.screen,
  moveAnnotations: () => [],
  closedShape: (item: any) => item.kind === 'stroke' && item.closed && !item.widths,
  fillAreasOf: (...args: any[]) => { projected.fills.push(args); return [{ kind: 'area', id: 'placed' }]; },
}));

beforeEach(() => { vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function mount(placement = 'surface', tool = 'text') {
  // The session's views: a view is named, nothing more.
  const noteView = vi.fn((view: unknown) => (view ? 'view 1' : undefined));
  const annotation = { items: [], selected: [], tool, style: { color: '#ff2d55', strokeWidth: 2, placement },
    noteView,
    add: vi.fn(), remove: vi.fn(), replace: vi.fn(), select: vi.fn(), undo: vi.fn(), redo: vi.fn() };
  render(<ViewerHostContext.Provider value={testHost()}>
    <AnnotationOverlay annotation={annotation} runtimeRef={{ current: {} }} viewOf={() => ({ camera: {} })} /></ViewerHostContext.Provider>);
  return { annotation, surface: document.querySelector('[data-cad-annotation-overlay]') as HTMLElement };
}
// A press on the surface as a browser makes it: the pointerdown (whose work React has done by the
// time the next event comes), then the mousedown, whose default focuses what was pressed.
function press(surface: HTMLElement, x: number, y: number) {
  fireEvent.pointerDown(surface, { button: 0, buttons: 1, pointerId: 1, clientX: x, clientY: y });
  if (fireEvent.mouseDown(surface, { button: 0, clientX: x, clientY: y })) surface.focus();
  fireEvent.pointerUp(surface, { button: 0, pointerId: 1, clientX: x, clientY: y });
}
const field = () => screen.queryByRole('textbox', { name: 'Text' }) as HTMLTextAreaElement | null;

it('writes text where the surface was pressed and puts it down as a card on Enter, Shift+Enter making a new line', async () => {
  const { annotation, surface } = mount();
  press(surface, 120, 80);
  // The press that opened the text leaves the keyboard in it.
  expect(field()).not.toBeNull();
  expect(document.activeElement).toBe(field());
  expect(field()!.style).toMatchObject({ left: '120px', top: '80px' });
  await userEvent.keyboard('Fender{Shift>}{Enter}{/Shift}radius{Enter}');
  expect(field()).toBeNull();
  expect(annotation.add).toHaveBeenCalledTimes(1);
  expect(annotation.add.mock.calls[0][0]).toMatchObject([{ kind: 'text', text: 'Fender\nradius', color: '#ff2d55', corners: [{ x: 120, y: 80 }, {}, {}, {}] }]);
  // The keyboard is the surface's again, for ⌘Z.
  expect(document.activeElement).toBe(surface);
});

it('puts the text down when the surface is pressed elsewhere, without opening another', async () => {
  const { annotation, surface } = mount();
  press(surface, 40, 40);
  await userEvent.keyboard('Edge');
  press(surface, 200, 150);
  expect(field()).toBeNull();
  expect(annotation.add.mock.calls.map(([items]) => items[0].text)).toEqual(['Edge']);
});

it('drops the text on Escape, and puts nothing down for none written', async () => {
  const { annotation, surface } = mount();
  press(surface, 40, 40);
  await userEvent.keyboard('gone{Escape}');
  expect(field()).toBeNull();
  expect(document.activeElement).toBe(surface);
  press(surface, 60, 60);
  press(surface, 80, 80);
  expect(annotation.add).not.toHaveBeenCalled();
});

it("puts a mark down as the session's placement says, named by its view, with no plane of its own", async () => {
  projected.calls.length = 0;
  const { annotation, surface } = mount('plane');
  for (const text of ['one', 'two']) {
    press(surface, 40, 40);
    await userEvent.keyboard(`${text}{Enter}`);
  }
  expect(projected.calls).toHaveLength(2);
  for (const [, marks, , options] of projected.calls) {
    expect(options).toMatchObject({ placement: 'plane' });
    expect(options).not.toHaveProperty('plane');
    expect((marks as { view: string }[])[0].view).toBe('view 1');
  }
  expect(annotation.noteView).toHaveBeenCalledTimes(2);
  expect(annotation.noteView.mock.calls.every(call => call.length === 1)).toBe(true);
});

// A drag across the surface, as a mouse makes it.
function drag(surface: HTMLElement, points: [number, number][]) {
  const [first, ...rest] = points;
  fireEvent.pointerDown(surface, { button: 0, buttons: 1, pointerId: 1, clientX: first[0], clientY: first[1] });
  for (const [x, y] of rest) fireEvent.pointerMove(surface, { buttons: 1, pointerId: 1, clientX: x, clientY: y });
  fireEvent.pointerUp(surface, { button: 0, pointerId: 1, clientX: rest[rest.length - 1][0], clientY: rest[rest.length - 1][1] });
}

it('the highlighter puts down an ordinary stroke: five times the weight, 0.35 opaque, no pressure widths; the pen keeps its own', () => {
  const line: [number, number][] = [[20, 20], [60, 30], [100, 20], [140, 40]];
  const highlighter = mount('surface', 'highlighter');
  drag(highlighter.surface, line);
  const [mark] = highlighter.annotation.add.mock.calls[0][0];
  expect(mark).toMatchObject({ kind: 'stroke', color: '#ff2d55', width: 10, opacity: 0.35, closed: false });
  expect(mark).not.toHaveProperty('widths');
  cleanup();
  const pen = mount('surface', 'freedraw');
  drag(pen.surface, line);
  const [inked] = pen.annotation.add.mock.calls[0][0];
  expect(inked).toMatchObject({ kind: 'stroke', width: 3, opacity: 1 });
  expect(inked.widths).toHaveLength(inked.points.length);
});

// The Fill tool, over a flat view's surface (which places marks itself): a press inside a closed shape fills it with
// the colour in hand; on a filled one in that colour it unfills it, in another it recolours it; on an open mark or
// on nothing, nothing.
it('Fill fills the closed shape under the press with the colour in hand, unfills or recolours a filled one, and leaves open marks and empty space alone', () => {
  const square = [{ x: 100, y: 100 }, { x: 200, y: 100 }, { x: 200, y: 200 }, { x: 100, y: 200 }];
  const items: any[] = [
    { id: 'rect', kind: 'stroke', closed: true, color: '#ff2d55', width: 2, points: new Float32Array(12) },
    { id: 'line', kind: 'stroke', closed: false, color: '#ff2d55', width: 2, points: new Float32Array(6) },
  ];
  const screenInk = [{ id: 'rect', kind: 'stroke', closed: true, width: 2, points: square },
    { id: 'line', kind: 'stroke', closed: false, width: 2, points: [{ x: 300, y: 50 }, { x: 400, y: 150 }] }];
  const surface = { onScreen: () => screenInk, place: (marks: any[]) => marks, view: () => null };
  const annotation: any = { items, selected: [], tool: 'fill', style: { color: '#39ff14', strokeWidth: 2, placement: 'surface' },
    noteView: () => undefined, add: vi.fn(), remove: vi.fn(), fill: vi.fn(), fillColor: vi.fn(), select: vi.fn() };
  const view = render(<ViewerHostContext.Provider value={testHost()}>
    <AnnotationOverlay annotation={annotation} surface={surface} viewOf={() => null} /></ViewerHostContext.Provider>);
  const overlay = document.querySelector('[data-cad-annotation-overlay]') as HTMLElement;
  // jsdom puts the overlay at 0,0, so the client point is the screen point.
  expect(overlay.style.cursor).toMatch(/^url\("data:image\/svg\+xml/);
  press(overlay, 150, 150);
  expect(annotation.fill).toHaveBeenCalledTimes(1);
  const [shape, areas, color] = annotation.fill.mock.calls[0];
  expect([shape, areas.map((area: any) => area.kind), color]).toEqual(['rect', ['area'], '#39ff14']);
  // Open marks and empty space: nothing.
  press(overlay, 350, 100);
  press(overlay, 20, 20);
  expect([annotation.fill.mock.calls.length, annotation.remove.mock.calls.length, annotation.fillColor.mock.calls.length]).toEqual([1, 0, 0]);
  // Filled already: in the colour in hand it is unfilled, in another it takes the colour in hand.
  items[0].group = 'g';
  items.push({ id: 'f', kind: 'area', group: 'g', color: '#39ff14' });
  press(overlay, 150, 150);
  expect(annotation.remove).toHaveBeenLastCalledWith(['f']);
  items[2].color = '#2979ff';
  press(overlay, 150, 150);
  expect(annotation.fillColor).toHaveBeenLastCalledWith('rect', '#39ff14');
  view.unmount();
});

// A right or middle drag in Draw is the view's, and the SAME press it is under Select: handed to the canvas with its own
// button, buttons and keys, so the view's one camera mapping (a 3D view's OrbitControls: the right button pans) decides it
// in both tools. A left press stays the drawing's, and never reaches the canvas.
it("hands a right or middle press to the view's canvas as Select's canvas gets it: the same button, so a right drag pans", () => {
  const canvas = document.body.appendChild(document.createElement('canvas'));
  const reached: Array<Record<string, unknown>> = [];
  canvas.addEventListener('pointerdown', event => reached.push({ button: event.button, buttons: event.buttons, shiftKey: event.shiftKey, clientX: event.clientX }));
  const annotation = { items: [], selected: [], tool: 'pen', style: { color: '#ff2d55', strokeWidth: 2, placement: 'surface' }, noteView: vi.fn(),
    add: vi.fn(), remove: vi.fn(), replace: vi.fn(), select: vi.fn(), undo: vi.fn(), redo: vi.fn() };
  render(<ViewerHostContext.Provider value={testHost()}>
    <AnnotationOverlay annotation={annotation} runtimeRef={{ current: { renderer: { domElement: canvas } } }} viewOf={() => ({ camera: {} })} /></ViewerHostContext.Provider>);
  const surface = document.querySelector('[data-cad-annotation-overlay]') as HTMLElement;
  // What Select's canvas would get: the raw press.
  const presses = [{ button: 2, buttons: 2, shiftKey: false, clientX: 40 }, { button: 1, buttons: 4, shiftKey: true, clientX: 60 }];
  for (const init of presses) fireEvent.pointerDown(surface, { pointerId: 7, pointerType: 'mouse', clientY: 30, ...init });
  expect(reached).toEqual(presses);
  fireEvent.pointerDown(surface, { pointerId: 8, pointerType: 'mouse', button: 0, buttons: 1, clientX: 80, clientY: 30 });
  expect(reached).toHaveLength(2);
  canvas.remove();
});

// A freehand loop on the screen: a 100px circle round (150, 150) whose end stops `gap` px short of its start.
const loop = (gap: number) => Array.from({ length: 64 }, (_, i) => {
  const turn = (i / 63) * (2 * Math.PI - gap / 50);
  return { x: 150 + 50 * Math.cos(turn), y: 150 + 50 * Math.sin(turn) };
});
function mountFill(screenInk: any[], items: any[], { flat = true } = {}) {
  projected.screen = screenInk;
  projected.fills = [];
  const surface = flat ? { onScreen: () => screenInk, place: (marks: any[]) => marks, view: () => null } : null;
  const annotation: any = { items, selected: [], tool: 'fill', style: { color: '#39ff14', strokeWidth: 2, placement: 'surface' },
    noteView: () => undefined, add: vi.fn(), remove: vi.fn(), fill: vi.fn(), fillColor: vi.fn(), select: vi.fn() };
  const view = render(<ViewerHostContext.Provider value={testHost()}>
    <AnnotationOverlay annotation={annotation} surface={surface} runtimeRef={flat ? null : { current: {} }} viewOf={() => null} /></ViewerHostContext.Provider>);
  return { annotation, view, overlay: document.querySelector('[data-cad-annotation-overlay]') as HTMLElement };
}
const pen = (id: string, closed = false) => ({ id, kind: 'stroke', closed, color: '#ff2d55', width: 3, widths: [1, 1], points: new Float32Array(6) });

// A pen stroke whose end comes back near its start is a closed outline to Fill, on the screen as it is now; one whose
// ends stay apart is an open mark.
it('Fill fills a pen loop whose ends meet on the screen, and leaves an open one alone', () => {
  const { annotation, view, overlay } = mountFill([{ id: 'loop', kind: 'stroke', closed: false, width: 3, points: loop(10) },
    { id: 'open', kind: 'stroke', closed: false, width: 3, points: loop(120).map(p => ({ x: p.x + 200, y: p.y })) }], [pen('loop'), pen('open')]);
  press(overlay, 150, 150);
  expect(annotation.fill.mock.calls.map((call: any[]) => [call[0], call[1].map((area: any) => area.kind)])).toEqual([['loop', ['area']]]);
  press(overlay, 350, 150);
  expect(annotation.fill).toHaveBeenCalledTimes(1);
  view.unmount();
});

// A press on the outline's own line is a press on that shape (its fill seeded inside it), and where outlines nest the
// last drawn under the pointer takes it, inside or on its line alike.
it("Fill takes a press on a shape's outline as inside it, and the topmost shape where outlines nest", () => {
  const square = (a: number, b: number) => [{ x: a, y: a }, { x: b, y: a }, { x: b, y: b }, { x: a, y: b }];
  const items: any[] = [{ id: 'outer', kind: 'stroke', closed: true, color: '#ff2d55', width: 2, points: new Float32Array(12) },
    { id: 'inner', kind: 'stroke', closed: true, color: '#ff2d55', width: 2, points: new Float32Array(12) }];
  const { annotation, view, overlay } = mountFill([{ id: 'outer', kind: 'stroke', closed: true, width: 2, points: square(50, 250) },
    { id: 'inner', kind: 'stroke', closed: true, width: 2, points: square(100, 200) }], items);
  // On the outer square's line, just outside it: the outer square.
  press(overlay, 150, 48);
  // On the inner square's line, and inside it: the inner square, every time.
  press(overlay, 150, 101);
  press(overlay, 150, 99);
  press(overlay, 150, 150);
  expect(annotation.fill.mock.calls.map((call: any[]) => call[0])).toEqual(['outer', 'inner', 'inner', 'inner']);
  // A press on a filled shape's line in the colour in hand unfills it.
  items[1].group = 'g';
  items.push({ id: 'f', kind: 'area', group: 'g', color: '#39ff14' });
  press(overlay, 200, 150);
  expect(annotation.remove).toHaveBeenLastCalledWith(['f']);
  view.unmount();
});

// Over a model the fill goes through `fillAreasOf` (the selection bar's own), with the loop closed on the screen.
it("Fill over a model fills a pen loop through the scene's fill, its outline closed", () => {
  const { annotation, view, overlay } = mountFill([{ id: 'loop', kind: 'stroke', closed: false, width: 3, points: loop(10) }], [pen('loop')], { flat: false });
  press(overlay, 150, 150);
  const [[, shape, outline, seed]] = projected.fills;
  expect([shape.id, outline.closed, seed]).toEqual(['loop', true, { x: 150, y: 150 }]);
  expect(annotation.fill).toHaveBeenCalledWith('loop', [{ kind: 'area', id: 'placed' }], '#39ff14');
  view.unmount();
});

// With Fill in hand, the closed outline under the pointer is marked as what a press fills; nothing, over nothing.
it('Fill previews the closed outline under the pointer and clears it over nothing and on leaving', () => {
  const { view, overlay } = mountFill([{ id: 'loop', kind: 'stroke', closed: false, width: 3, points: loop(10) },
    { id: 'open', kind: 'stroke', closed: false, width: 3, points: [{ x: 300, y: 300 }, { x: 400, y: 300 }, { x: 400, y: 320 }] }], [pen('loop'), pen('open')]);
  const move = (x: number, y: number) => fireEvent.pointerMove(overlay, { pointerId: 1, pointerType: 'mouse', clientX: x, clientY: y });
  move(150, 150);
  expect(overlay.dataset.fillHover).toBe('loop');
  move(350, 305);
  expect(overlay.dataset.fillHover).toBeUndefined();
  move(150, 150);
  fireEvent.pointerLeave(overlay, { pointerId: 1, pointerType: 'mouse' });
  expect(overlay.dataset.fillHover).toBeUndefined();
  view.unmount();
});
