import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import QuickEdit from '../../../../../dist/renderers/kit/tools/quick-edit/QuickEdit.js';
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

it('opens itself when a selection or a sketch begins, taking the keyboard, and attaches what is live', () => {
  const sketch = { ink: true, capture: async () => new Blob(['png'], { type: 'image/png' }), subscribe: () => () => {} };
  const edge = { resource, target: { kind: 'cad-selector', selectors: ['o1.e3'] } } as const;
  const { update } = mount();
  expect(box()).toBeNull();
  // An agent's selection (no press of the person's) opens nothing.
  update({ references: [face] });
  expect(box()).toBeNull();
  update({ references: [] });
  press();
  update({ references: [face] });
  expect(box()).not.toBeNull();
  expect(document.activeElement).toBe(field());
  expect(within(box()!).getByText('bracket.step')).toBeTruthy();
  expect(within(box()!).getByText('1 reference', { exact: false })).toBeTruthy();
  update({ references: [face, edge] });
  expect(within(box()!).getByText('2 references', { exact: false })).toBeTruthy();
  // A reference naming several picks counts each.
  update({ references: [{ resource, target: { kind: 'cad-selector', selectors: ['o1.f2', 'o1.e3', 'o1.e4'] } }] });
  expect(within(box()!).getByText('3 references', { exact: false })).toBeTruthy();
  // The X clears the note and closes the box; the next selection opens it again.
  fireEvent.change(field(), { target: { value: 'Round it.' } });
  fireEvent.click(within(box()!).getByRole('button', { name: 'Clear Quick Edit' }));
  expect(box()).toBeNull();
  update({ references: [] });
  press();
  update({ references: [edge] });
  expect(field().value).toBe('');
  // Its own button hides it with the note kept, and then it stays away — a selection or a sketch
  // begun opens nothing — until that button opens it again, attaching what is live.
  fireEvent.change(field(), { target: { value: 'Round it.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Quick Edit' }));
  expect(box()).toBeNull();
  update({ references: [] });
  press();
  update({ references: [face], sketch });
  expect(box()).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Quick Edit' }));
  expect(field().value).toBe('Round it.');
  expect(document.activeElement).toBe(field());
  expect(box()!.querySelector('[data-quick-edit-chip="references"]')).not.toBeNull();
  expect(box()!.querySelector('[data-quick-edit-chip="sketch"]')).not.toBeNull();
  // Escape keeps a note, box and all; in an empty box it closes it and is the viewer's too.
  const escape = vi.fn();
  update({ references: [face], sketch, onEscape: escape });
  fireEvent.keyDown(field(), { key: 'Escape' });
  expect([box() !== null, escape.mock.calls.length]).toEqual([true, 0]);
  fireEvent.change(field(), { target: { value: '' } });
  fireEvent.keyDown(field(), { key: 'Escape' });
  expect([box(), escape.mock.calls.length]).toEqual([null, 1]);
});

it('opens once per sketch: its first ink, not the ink an Undo takes away and a Redo puts back', () => {
  const drawing = (ink: boolean) => ({ ink, capture: async () => new Blob(['png'], { type: 'image/png' }), subscribe: () => () => {} });
  const { update } = mount();
  update({ sketch: drawing(false) });
  expect(box()).toBeNull();
  update({ sketch: drawing(true) });
  expect(box()).not.toBeNull();
  fireEvent.click(within(box()!).getByRole('button', { name: 'Clear Quick Edit' }));
  update({ sketch: drawing(false) });
  update({ sketch: drawing(true) });
  expect(box()).toBeNull();
  // Draw put down and taken up again is a new sketch.
  update({ sketch: null });
  update({ sketch: drawing(true) });
  expect(box()).not.toBeNull();
});

it('offers the buttons the host can carry out, the rightmost primary and pressed by Enter', async () => {
  const send = vi.fn(async () => ({ status: 'sent' as const, partIds: [] }));
  const deliver = vi.fn(async () => ({ status: 'added' as const, partIds: [] }));
  mount(testHost({ promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver, send } }));
  fireEvent.click(screen.getByRole('button', { name: 'Quick Edit' }));
  expect(buttons()).toEqual(['Clear Quick Edit', 'Copy Prompt', 'Queue', 'Send']);
  expect(within(box()!).getByRole('button', { name: 'Send' }).hasAttribute('disabled')).toBe(true);
  fireEvent.change(field(), { target: { value: 'Make it 2 mm thicker.' } });
  fireEvent.keyDown(field(), { key: 'Enter', shiftKey: true });
  expect(send).not.toHaveBeenCalled();
  fireEvent.keyDown(field(), { key: 'Enter' });
  expect(send).toHaveBeenCalledTimes(1);
  const context = (send.mock.calls[0] as unknown[])[0] as any;
  expect(context.parts.map((part: any) => [part.id, part.kind])).toEqual([['text', 'text'], ['file', 'reference']]);
  // Gone: cleared and closed.
  await waitFor(() => expect(box()).toBeNull());
  expect(deliver).not.toHaveBeenCalled();
});

it('copies the note with its references as copied, and its sketch saved as a file it names', async () => {
  let copied: Promise<string> | string = '';
  const saved: string[] = [];
  const host = testHost({
    clipboard: { writeText: async text => { copied = text; }, readText: async () => '', writeImage: async () => {} },
    attachments: { save: async (_png, name) => { saved.push(name); return `/tmp/cadgen-sketches/${name}`; } },
  });
  const sketch = { ink: true, capture: async () => new Blob(['png'], { type: 'image/png' }), subscribe: () => () => {} };
  mount(host, { references: [face], sketch });
  fireEvent.click(screen.getByRole('button', { name: 'Quick Edit' }));
  expect(buttons()).toEqual(['Clear Quick Edit', 'Copy Prompt']);
  fireEvent.change(field(), { target: { value: 'Round this edge.' } });
  fireEvent.click(within(box()!).getByRole('button', { name: 'Copy Prompt' }));
  await waitFor(() => expect(box()).toBeNull());
  expect(await copied).toBe('Round this edge.\n\nFile: models/parts/bracket.step\nReferences:\nmodels/parts/bracket.step#o1.f2\nSketch: /tmp/cadgen-sketches/bracket-sketch.png');
  expect(saved).toEqual(['bracket-sketch.png']);
});

it('keeps the note and says why when it did not go', async () => {
  const deliver = vi.fn(async () => ({ status: 'failed' as const, message: 'The chat is busy.' }));
  mount(testHost({ promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver } }));
  fireEvent.click(screen.getByRole('button', { name: 'Quick Edit' }));
  fireEvent.change(field(), { target: { value: 'Shorter.' } });
  await act(async () => { fireEvent.click(within(box()!).getByRole('button', { name: 'Queue' })); });
  expect(within(box()!).getByRole('alert').textContent).toBe('The chat is busy.');
  expect(field().value).toBe('Shorter.');
});
