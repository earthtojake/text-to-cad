import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import AnnotationOverlay from '../../../../../dist/renderers/kit/tools/annotate/AnnotationOverlay.js';
import { ViewerHostContext } from '../../../../../dist/host/context.js';
import { testHost } from '../../../../../dist/host/testing/host.js';

// Projecting needs a WebGL scene: here a mark goes into the annotation as it was made.
const projected = vi.hoisted(() => ({ calls: [] as unknown[][] }));
vi.mock('../../../../../dist/renderers/kit/tools/annotate/annotation3d.js', () => ({
  projectAnnotations: (...args: unknown[]) => { projected.calls.push(args); return args[1]; },
  annotationsOnScreen: () => [],
  moveAnnotations: () => [],
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
