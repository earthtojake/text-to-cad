import React, { Profiler } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import QuickEdit, { quickEditReferenceIds } from '../../../../../dist/renderers/kit/tools/quick-edit/QuickEdit.js';
import { ViewerHostContext } from '../../../../../dist/host/context.js';
import { testHost } from '../../../../../dist/host/testing/host.js';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const resource = { kind: 'workspace-file', workspaceId: 'w', path: 'parts/bracket.step', revision: 'r1' } as const;
const face = { resource, target: { kind: 'cad-selector', selectors: ['o1.f2'] } } as const;
const composer = { kind: 'composer', available: true } as const;

function mount(host = testHost(), props: Record<string, unknown> = {}) {
  const view = (next: Record<string, unknown>) => <ViewerHostContext.Provider value={host}><div data-slot="cad-file-view">
    <QuickEdit resource={resource} referencePath={(path: string) => `models/${path}`} {...props} {...next} />
  </div></ViewerHostContext.Provider>;
  const rendered = render(view({}));
  return { ...rendered, update: (next: Record<string, unknown>) => rendered.rerender(view(next)) };
}
const box = () => screen.queryByRole('region', { name: 'Quick Edit' });
// A press in the view, as a pick is: what a selection that opens the box follows.
const press = () => {
  const view = document.querySelector('[data-slot="cad-file-view"]')!;
  fireEvent.pointerDown(view);
  fireEvent.pointerUp(view, { button: 0 });
};
const field = () => screen.getByRole('textbox', { name: 'Describe your changes' }) as HTMLTextAreaElement;
const buttons = () => within(box()!).getAllByRole('button').map(button => button.getAttribute('aria-label') || button.textContent);

it('follows what it would carry while the note is empty: open for the person with the keyboard, for an agent without it', () => {
  const edge = { resource, target: { kind: 'cad-selector', selectors: ['o1.e3'] } } as const;
  const { update } = mount();
  // With nothing to carry there is nothing at all: no box, and no button standing in for one.
  expect(box()).toBeNull();
  expect(screen.queryByRole('button')).toBeNull();
  // An agent's selection (no press of the person's) opens it, and leaves their keyboard where it was.
  update({ references: [face] });
  expect(box()).not.toBeNull();
  expect(document.activeElement).not.toBe(field());
  update({ references: [] });
  expect(box()).toBeNull();
  // The person's pick opens it with the keyboard in its note; the header counts what is picked.
  press();
  update({ references: [face] });
  expect(document.activeElement).toBe(field());
  expect(within(box()!).queryByText('bracket.step')).toBeNull();
  expect(box()!.querySelector('[data-quick-edit-chip="references"]')!.textContent).toBe('1 ref');
  // Each pick of theirs puts the keyboard back in the note.
  field().blur();
  press();
  update({ references: [face, edge] });
  expect(document.activeElement).toBe(field());
  expect(box()!.querySelector('[data-quick-edit-chip="references"]')!.textContent).toBe('2 refs');
  // A reference naming several picks counts each, and each is listed by its id.
  const several = [{ resource, target: { kind: 'cad-selector', selectors: ['o1.f2', 'o1.e3', 'o1.e4'] } }] as const;
  update({ references: several });
  expect(box()!.querySelector('[data-quick-edit-chip="references"]')!.textContent).toBe('3 refs');
  expect(quickEditReferenceIds(several)).toEqual(['o1.f2', 'o1.e3', 'o1.e4']);
  // A note keeps it open when the selection goes.
  fireEvent.change(field(), { target: { value: 'Round it.' } });
  update({ references: [] });
  expect(field().value).toBe('Round it.');
  // The X clears the note and has the renderer clear what it carries; the box goes with that.
  const clear = vi.fn();
  update({ references: [face, edge], onClear: clear });
  fireEvent.click(within(box()!).getByRole('button', { name: 'Close Quick Edit' }));
  expect([field().value, clear.mock.calls.length]).toEqual(['', 1]);
  update({ references: [] });
  expect(box()).toBeNull();
  // Escape keeps a note, box and all; in an empty box it is the viewer's own (whose clear closes it).
  const escape = vi.fn();
  update({ references: [face], onEscape: escape });
  fireEvent.change(field(), { target: { value: 'Round it.' } });
  fireEvent.keyDown(field(), { key: 'Escape' });
  expect([box() !== null, escape.mock.calls.length]).toEqual([true, 0]);
  fireEvent.change(field(), { target: { value: '' } });
  fireEvent.keyDown(field(), { key: 'Escape' });
  expect(escape.mock.calls.length).toBe(1);
});

it('opens with a sketch while there is ink, taking the keyboard once the pen lifts, and closes when the ink goes', () => {
  const drawing = (ink: boolean) => ({ ink, capture: async () => new Blob(['png'], { type: 'image/png' }) });
  const view = () => document.querySelector('[data-slot="cad-file-view"]')!;
  const { update } = mount();
  update({ sketch: drawing(false) });
  expect(box()).toBeNull();
  fireEvent.pointerDown(view());
  update({ sketch: drawing(true) });
  expect(box()!.querySelector('[data-quick-edit-chip="sketch"]')!.textContent).toBe('drawing');
  expect(document.activeElement).not.toBe(field());
  fireEvent.pointerUp(view(), { button: 0 });
  expect(document.activeElement).toBe(field());
  update({ sketch: drawing(false) });
  expect(box()).toBeNull();
  update({ sketch: drawing(true) });
  fireEvent.change(field(), { target: { value: 'A boss here.' } });
  update({ sketch: null });
  expect(field().value).toBe('A boss here.');
});

it('offers the buttons the host can carry out, the rightmost primary and pressed by Enter', async () => {
  const send = vi.fn(async () => ({ status: 'sent' as const, partIds: [] }));
  const deliver = vi.fn(async () => ({ status: 'added' as const, partIds: [] }));
  const clear = vi.fn();
  mount(testHost({ promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver, send } }), { references: [face], onClear: clear });
  expect(buttons()).toEqual(['Close Quick Edit', 'Copy Prompt', 'Queue', 'Send']);
  expect(within(box()!).getByRole('button', { name: 'Send' }).hasAttribute('disabled')).toBe(true);
  fireEvent.change(field(), { target: { value: 'Make it 2 mm thicker.' } });
  fireEvent.keyDown(field(), { key: 'Enter', shiftKey: true });
  expect(send).not.toHaveBeenCalled();
  fireEvent.keyDown(field(), { key: 'Enter' });
  expect(send).toHaveBeenCalledTimes(1);
  const context = (send.mock.calls[0] as unknown[])[0] as any;
  expect(context.parts.map((part: any) => [part.id, part.kind])).toEqual([['text', 'text'], ['file', 'reference'], ['reference-0', 'reference']]);
  // Gone: the note cleared, and what it carried with it.
  await waitFor(() => expect(clear).toHaveBeenCalledTimes(1));
  expect(field().value).toBe('');
  expect(deliver).not.toHaveBeenCalled();
});

it('copies the note with its references as copied, and its sketch saved as a file it names, keeping it all in the box', async () => {
  let copied: Promise<string> | string = '';
  const saved: string[] = [];
  const host = testHost({
    clipboard: { writeText: async text => { copied = text; }, readText: async () => '', writeImage: async () => {} },
    attachments: { save: async (_png, name) => { saved.push(name); return `/tmp/cadgen-sketches/${name}`; } },
  });
  const sketch = { ink: true, capture: async () => new Blob(['png'], { type: 'image/png' }) };
  const clear = vi.fn();
  mount(host, { references: [face], sketch, onClear: clear });
  expect(buttons()).toEqual(['Close Quick Edit', 'Copy Prompt']);
  fireEvent.change(field(), { target: { value: 'Round this edge.' } });
  fireEvent.click(within(box()!).getByRole('button', { name: 'Copy Prompt' }));
  // Copied, nothing has gone yet: the note and what it carries stay, and the button says so.
  await waitFor(() => expect(within(box()!).getByRole('button', { name: 'Prompt copied' })).toBeTruthy());
  expect([field().value, clear.mock.calls.length]).toEqual(['Round this edge.', 0]);
  expect(await copied).toBe('Round this edge.\n\nFile: models/parts/bracket.step\nReferences:\nmodels/parts/bracket.step#o1.f2\nSketch: /tmp/cadgen-sketches/bracket-sketch.png');
  expect(saved).toEqual(['bracket-sketch.png']);
});

it('keeps the note and says why when it did not go', async () => {
  const deliver = vi.fn(async () => ({ status: 'failed' as const, message: 'The chat is busy.' }));
  const clear = vi.fn();
  mount(testHost({ promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver } }), { references: [face], onClear: clear });
  fireEvent.change(field(), { target: { value: 'Shorter.' } });
  await act(async () => { fireEvent.click(within(box()!).getByRole('button', { name: 'Queue' })); });
  expect(within(box()!).getByRole('alert').textContent).toBe('The chat is busy.');
  expect([field().value, clear.mock.calls.length]).toEqual(['Shorter.', 0]);
});

it('is sized by its corner while it is open, rendering nothing for the drag, and opens at the default size again', async () => {
  let commits = 0;
  const view = (references: readonly unknown[]) => <Profiler id="quick-edit" onRender={() => { commits += 1; }}>
    <ViewerHostContext.Provider value={testHost()}><QuickEdit resource={resource} references={references} /></ViewerHostContext.Provider>
  </Profiler>;
  const { rerender } = render(view([face]));
  const size = () => [box()!.style.width, field().style.height];
  expect(size()).toEqual(['', '']);
  // jsdom measures the box and its note as 0, so a drag of the corner 300px left and 100px down
  // makes them that: drawn on the next frame, and nothing renders, then or when the pointer lets go.
  const corner = box()!.querySelector('[data-quick-edit-resize]')!;
  const before = commits;
  fireEvent.pointerDown(corner, { button: 0, pointerId: 1, clientX: 400, clientY: 100 });
  fireEvent.pointerMove(corner, { pointerId: 1, clientX: 100, clientY: 200 });
  await waitFor(() => expect(size()).toEqual(['300px', '100px']));
  fireEvent.pointerUp(corner, { pointerId: 1, clientX: 100, clientY: 200 });
  expect(commits).toBe(before);
  // The size holds for as long as the box is open.
  fireEvent.change(field(), { target: { value: 'Wider.' } });
  expect(size()).toEqual(['300px', '100px']);
  // Closed, it is forgotten: the next box is 15rem wide, its note growing with what is written.
  fireEvent.click(within(box()!).getByRole('button', { name: 'Close Quick Edit' }));
  rerender(view([]));
  expect(box()).toBeNull();
  rerender(view([face]));
  expect(size()).toEqual(['', '']);
});

it('keeps its note through a reload of the view: out of sight while it loads, and back as it was', () => {
  const { update } = mount(testHost(), { references: [face] });
  fireEvent.change(field(), { target: { value: 'Thicker here.' } });
  update({ hidden: true });
  expect(document.querySelector('[data-quick-edit]')!.className).toMatch(/\bhidden\b/);
  update({ hidden: false });
  expect(field().value).toBe('Thicker here.');
});
