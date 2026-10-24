import React, { Profiler } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import QuickEdit, { quickEditReferenceIds } from '../../../../../dist/renderers/kit/tools/quick-edit/QuickEdit.js';
import { ViewerHostContext } from '../../../../../dist/host/context.js';
import { testHost } from '../../../../../dist/host/testing/host.js';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const resource = { kind: 'workspace-file', path: '/models/parts/bracket.step', revision: 'r1' } as const;
const face = { resource, target: { kind: 'cad-selector', selectors: ['o:1a2b3c4d5e6f/f:base.extrude1.2'] } } as const;
const composer = { kind: 'composer', available: true } as const;

function mount(host = testHost(), props: Record<string, unknown> = {}) {
  const view = (next: Record<string, unknown>) => <ViewerHostContext.Provider value={host}><div data-slot="cad-file-view">
    <QuickEdit resource={resource} {...props} {...next} />
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
const field = () => screen.getByRole('textbox', { name: 'Describe your changes' }) as HTMLElement;
// The note is an editable field: what is written in it, and writing in it, as typing would.
const note = () => field().textContent;
const write = (value: string) => { field().textContent = value; fireEvent.input(field()); };
const buttons = () => within(box()!).getAllByRole('button').map(button => button.getAttribute('aria-label') || button.textContent);

it('follows what it would carry while the note is empty: open for the person with the keyboard, for an agent without it', () => {
  const edge = { resource, target: { kind: 'cad-selector', selectors: ['o:1a2b3c4d5e6f/e:base.extrude1.3'] } } as const;
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
  const several = [{ resource, target: { kind: 'cad-selector', selectors: ['o:1a2b3c4d5e6f/f:base.extrude1.2', 'o:1a2b3c4d5e6f/e:base.extrude1.3', 'o:1a2b3c4d5e6f/e:base.fillet1.4'] } }] as const;
  update({ references: several });
  expect(box()!.querySelector('[data-quick-edit-chip="references"]')!.textContent).toBe('3 refs');
  expect(quickEditReferenceIds(several)).toEqual(['o:1a2b3c4d5e6f/f:base.extrude1.2', 'o:1a2b3c4d5e6f/e:base.extrude1.3', 'o:1a2b3c4d5e6f/e:base.fillet1.4']);
  // A note keeps it open when the selection goes.
  write('Round it.');
  update({ references: [] });
  expect(note()).toBe('Round it.');
  // The X clears the note and has the renderer clear what it carries; the box goes with that.
  const clear = vi.fn();
  update({ references: [face, edge], onClear: clear });
  fireEvent.click(within(box()!).getByRole('button', { name: 'Close Quick Edit' }));
  expect([note(), clear.mock.calls.length]).toEqual(['', 1]);
  update({ references: [] });
  expect(box()).toBeNull();
  // Escape keeps a note, box and all; in an empty box it is the viewer's own (whose clear closes it).
  const escape = vi.fn();
  update({ references: [face], onEscape: escape });
  write('Round it.');
  fireEvent.keyDown(field(), { key: 'Escape' });
  expect([box() !== null, escape.mock.calls.length]).toEqual([true, 0]);
  write('');
  fireEvent.keyDown(field(), { key: 'Escape' });
  expect(escape.mock.calls.length).toBe(1);
});

it('opens with an annotation while there is ink, taking the keyboard once the pen lifts, and closes when the ink goes', () => {
  const annotation = (present: boolean) => ({ present });
  const view = () => document.querySelector('[data-slot="cad-file-view"]')!;
  const { update } = mount();
  update({ annotation: annotation(false) });
  expect(box()).toBeNull();
  fireEvent.pointerDown(view());
  update({ annotation: annotation(true) });
  expect(box()!.querySelector('[data-quick-edit-ref="annotation"]')!.textContent).toBe('Annotation');
  expect(document.activeElement).not.toBe(field());
  fireEvent.pointerUp(view(), { button: 0 });
  expect(document.activeElement).toBe(field());
  update({ annotation: annotation(false) });
  expect(box()).toBeNull();
  update({ annotation: annotation(true) });
  write('A boss here.');
  update({ annotation: null });
  expect(note()).toBe('A boss here.');
});

it('offers the buttons the host can carry out, the rightmost primary and pressed by Enter', async () => {
  const send = vi.fn(async () => ({ status: 'sent' as const, partIds: [] }));
  const deliver = vi.fn(async () => ({ status: 'added' as const, partIds: [] }));
  const clear = vi.fn();
  const used = vi.fn();
  mount(testHost({ promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver, send }, usage: { used } }), { references: [face], onClear: clear });
  expect(buttons()).toEqual(['Close Quick Edit', 'Copy Prompt', 'Queue', 'Send']);
  expect(within(box()!).getByRole('button', { name: 'Send' }).hasAttribute('disabled')).toBe(true);
  write('Make it 2 mm thicker.');
  fireEvent.keyDown(field(), { key: 'Enter', shiftKey: true });
  expect(send).not.toHaveBeenCalled();
  fireEvent.keyDown(field(), { key: 'Enter' });
  expect(send).toHaveBeenCalledTimes(1);
  const context = (send.mock.calls[0] as unknown[])[0] as any;
  expect(context.parts.map((part: any) => [part.id, part.kind])).toEqual([['text', 'text'], ['file', 'reference'], ['reference-0', 'reference']]);
  // Gone: the note cleared, and what it carried with it -- and the host told, once, for its count.
  await waitFor(() => expect(clear).toHaveBeenCalledTimes(1));
  expect(note()).toBe('');
  expect(deliver).not.toHaveBeenCalled();
  expect(used.mock.calls).toEqual([['quickEdit']]);
});

it('copies the note with its references by their files\' absolute paths, and its single snapshot by its path, keeping it all in the box', async () => {
  let copied: Promise<string> | string = '';
  const host = testHost({ clipboard: { writeText: async text => { copied = text; }, readText: async () => '', writeImage: async () => {} } });
  const annotation = { present: true };
  const views = [{ label: 'view 1' }];
  const prompt = {
    views: () => views,
    files: vi.fn(async () => ({ snapshot: '/tmp/p/bracket-1.snapshot.json' })),
    read: vi.fn(async () => new Blob()),
    annotation: () => ({ units: 'mm', marks: [] }),
  };
  const clear = vi.fn();
  mount(host, { references: [face], annotation, prompt, onClear: clear });
  // The annotation is a chip of its own, Annotation; without a way to wipe it, it has no X.
  expect(buttons()).toEqual(['Close Quick Edit', 'Annotation', 'Copy Prompt']);
  write('Round this edge.');
  expect(prompt.files).not.toHaveBeenCalled();
  fireEvent.click(within(box()!).getByRole('button', { name: 'Copy Prompt' }));
  // Copied, nothing has gone yet: the note and what it carries stay, and the button says so.
  await waitFor(() => expect(within(box()!).getByRole('button', { name: 'Prompt copied' })).toBeTruthy());
  expect([note(), clear.mock.calls.length]).toEqual(['Round this edge.', 0]);
  expect(await copied).toBe('Round this edge.\n\nFile: /models/parts/bracket.step\nReferences:\n/models/parts/bracket.step#o:1a2b3c4d5e6f/f:base.extrude1.2'
    + '\nSnapshot (cadgen snapshot --annotation): /tmp/p/bracket-1.snapshot.json');
  expect(prompt.files).toHaveBeenCalledWith(views);
  // Copied as text, no file's bytes were read.
  expect(prompt.read).not.toHaveBeenCalled();
});

it.each(['Copy Prompt', 'Queue', 'Send'])('%s creates the snapshot only at the press', async action => {
  const composer = { kind: 'composer', available: true } as const;
  const delivered: any[] = [];
  const take = async (context: any) => {
    delivered.push(context);
    await Promise.all(context.parts.filter((part: any) => part.kind === 'attachment').map((part: any) => part.path));
    return { status: 'added' as const, partIds: [] };
  };
  const prompt = { views: () => [{ label: 'view 1' }],
    files: vi.fn(async () => ({ snapshot: '/tmp/p/a.snapshot.json' })), read: vi.fn(async () => new Blob()) };
  const host = testHost({ promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver: take, send: take } as any });
  mount(host, { annotation: { present: true }, prompt });
  write('Change this.');
  expect(prompt.files).not.toHaveBeenCalled();
  fireEvent.click(within(box()!).getByRole('button', { name: action }));
  await waitFor(() => expect(prompt.files).toHaveBeenCalledTimes(1));
  if (action !== 'Copy Prompt') {
    const attachments = delivered[0].parts.filter((part: any) => part.kind === 'attachment');
    expect(attachments).toHaveLength(1);
    expect(await attachments[0].path).toBe('/tmp/p/a.snapshot.json');
  }
});

it('the annotation chip keeps its removal without copying or saving individual files, and the prompt carries no measurements', async () => {
  const writeText = vi.fn(async (_text: string | PromiseLike<string>) => {}), save = vi.fn(), files = vi.fn();
  const clearInk = vi.fn();
  const host = testHost({ clipboard: { writeText, readText: async () => '', writeImage: async () => {} },
    promptFiles: { create: files, read: vi.fn(), save } });
  const ink = { units: 'mm', marks: [] };
  render(<ViewerHostContext.Provider value={host}>
    <QuickEdit resource={resource} annotation={{ present: true, clear: clearInk }}
      prompt={{ views: () => [{ label: 'current view' }], save, files: async () => ({
        inline: JSON.stringify({ input: resource.path, jobs: [], annotation: ink }) }) } as any} />
  </ViewerHostContext.Provider>);
  fireEvent.click(screen.getByRole('button', { name: 'Annotation' }));
  expect(writeText).not.toHaveBeenCalled();
  expect(save).not.toHaveBeenCalled();
  expect(files).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Copy Prompt' }));
  await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
  const copied = await writeText.mock.calls[0][0];
  expect(copied).toContain('"annotation":');
  expect(copied).not.toContain('measurements');
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Remove Annotation' }));
  expect(clearInk).toHaveBeenCalledOnce();
});

it('a click on a pill in the note selects it whole, highlighted as selected text, so a Backspace takes it', () => {
  mount(testHost(), { references: [face] });
  write('Round ');
  fireEvent.paste(field(), { clipboardData: { getData: () => '/models/parts/hinge.step#o:1a2b3c4d5e6f/e:hinge.make1.4' } });
  const pill = field().querySelector('[data-quick-edit-note-ref]') as HTMLElement;
  fireEvent.mouseDown(pill.firstChild!, { button: 0 });
  const range = document.getSelection()!.getRangeAt(0);
  expect([range.startContainer, range.startOffset, range.endOffset]).toEqual([field(), 1, 2]);
  expect(pill.dataset.selected).toBe('');
  // The selection moving off it unmarks it.
  document.getSelection()!.collapse(field(), 0);
  document.dispatchEvent(new Event('selectionchange'));
  expect(pill.dataset.selected).toBeUndefined();
});

it('a pasted reference is a chip in the note, where it was pasted, and goes as the reference it stands for; the rest of a paste is text', async () => {
  let copied: Promise<string> | string = '';
  const host = testHost({ clipboard: { writeText: async text => { copied = text; }, readText: async () => '', writeImage: async () => {} } });
  mount(host, { references: [face] });
  const paste = (text: string) => fireEvent.paste(field(), { clipboardData: { getData: () => text } });
  write('Round ');
  // A line that is a reference alone, into any file (a robot's link too), is a chip; the rest stays text.
  paste('/models/parts/hinge.step#o:1a2b3c4d5e6f/e:hinge.make1.4,o:1a2b3c4d5e6f/e:hinge.make1.5\nand\n/robots/arm.urdf#upper_arm');
  const chips = [...field().querySelectorAll('[data-quick-edit-note-ref]')];
  expect(chips.map(chip => [chip.textContent, chip.getAttribute('contenteditable')]))
    .toEqual([['hinge.step · o:1a2b3c4d5e6f/e:hinge.make1.4, o:1a2b3c4d5e6f/e:hinge.make1.5', 'false'], ['arm.urdf · upper_arm', 'false']]);
  // A reference within a sentence is the sentence's.
  paste('see /models/parts/hinge.step#o:1a2b3c4d5e6f/e:hinge.make1.9');
  expect(field().querySelectorAll('[data-quick-edit-note-ref]')).toHaveLength(2);
  fireEvent.click(within(box()!).getByRole('button', { name: 'Copy Prompt' }));
  expect(await waitFor(() => copied)).toBe('Round /models/parts/hinge.step#o:1a2b3c4d5e6f/e:hinge.make1.4,o:1a2b3c4d5e6f/e:hinge.make1.5 \nand\n/robots/arm.urdf#upper_arm see /models/parts/hinge.step#o:1a2b3c4d5e6f/e:hinge.make1.9'
    + '\n\nFile: /models/parts/bracket.step\nReferences:\n/models/parts/bracket.step#o:1a2b3c4d5e6f/f:base.extrude1.2');
  // The box's X empties the note, chips and all (the selection here is fixed, so the box stays).
  fireEvent.click(within(box()!).getByRole('button', { name: 'Close Quick Edit' }));
  expect([note(), field().childNodes.length]).toEqual(['', 0]);
});

it('every chip\'s copy pasted is its pill, as its chip shows it: the annotation, a named part', async () => {
  let copied: Promise<string> | string = '';
  const host = testHost({ clipboard: { writeText: async text => { copied = text; }, readText: async () => '', writeImage: async () => {} } });
  const nameReference = () => ({ name: 'base', kind: 'solid' });
  mount(host, { references: [face], nameReference });
  const paste = (text: string) => fireEvent.paste(field(), { clipboardData: { getData: () => text } });
  const pills = () => [...field().querySelectorAll('[data-quick-edit-note-ref]')]
    .map(pill => [pill.querySelector('svg')?.getAttribute('data-pick-glyph'), pill.textContent]);
  const annotation = { units: 'mm', marks: [{ id: 'a', kind: 'stroke' }] };
  paste(JSON.stringify(annotation, null, 2));
  paste('/models/parts/bracket.step#o:1a2b3c4d5e6f');
  expect(pills()).toEqual([['pencil', 'Annotation'], ['solid', 'base']]);
  // Each goes as what was copied: the annotation as its JSON.
  fireEvent.click(within(box()!).getByRole('button', { name: 'Copy Prompt' }));
  const text = await waitFor(() => copied);
  expect(text).toContain(JSON.stringify(annotation));
});

it('keeps the note and says why when it did not go, and counts no use', async () => {
  const deliver = vi.fn(async () => ({ status: 'failed' as const, message: 'The chat is busy.' }));
  const clear = vi.fn();
  // A host whose count fails: the edit is unhurt either way.
  const used = vi.fn(() => { throw new Error('the count'); });
  mount(testHost({ promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver }, usage: { used } }), { references: [face], onClear: clear });
  write('Shorter.');
  await act(async () => { fireEvent.click(within(box()!).getByRole('button', { name: 'Queue' })); });
  expect(within(box()!).getByRole('alert').textContent).toBe('The chat is busy.');
  expect([note(), clear.mock.calls.length, used.mock.calls.length]).toEqual(['Shorter.', 0, 0]);
  deliver.mockResolvedValueOnce({ status: 'added', partIds: [] } as any);
  await act(async () => { fireEvent.click(within(box()!).getByRole('button', { name: 'Queue' })); });
  await waitFor(() => expect(clear).toHaveBeenCalledTimes(1));
  expect([used.mock.calls.length, within(box() ?? document.body).queryByRole('alert')]).toEqual([1, null]);
});

it('is sized by its corner while it is open, rendering nothing for the drag, and opens at the default size again', async () => {
  let commits = 0;
  const view = (references: readonly unknown[]) => <Profiler id="quick-edit" onRender={() => { commits += 1; }}>
    <ViewerHostContext.Provider value={testHost()}><QuickEdit resource={resource} references={references} /></ViewerHostContext.Provider>
  </Profiler>;
  const { rerender } = render(view([face]));
  const size = () => [box()!.style.width, (box()!.querySelector('[data-quick-edit-note-box]') as HTMLElement).style.height];
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
  write('Wider.');
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
  write('Thicker here.');
  update({ hidden: true });
  expect(document.querySelector('[data-quick-edit]')!.className).toMatch(/\bhidden\b/);
  update({ hidden: false });
  expect(note()).toBe('Thicker here.');
});

it('docked on a phone it is a bottom sheet peeking at its header and chips, keeps the keyboard down on a pick, and opens from its write button', async () => {
  const { update } = mount(testHost(), { docked: true });
  press();
  update({ references: [face] });
  // A bottom sheet (shadcn's drawer), peeking: its note and buttons are out of reach until it opens.
  expect(document.querySelector('[data-quick-edit-sheet]')).not.toBeNull();
  // Peeking, its way in is a field-like button under the chips; the note and buttons are out of reach.
  const opener = () => within(box()!).queryByRole('button', { name: 'Describe your changes…' });
  const compose = () => box()!.querySelector('[data-quick-edit-compose]')!;
  const note = () => box()!.querySelector<HTMLElement>('[data-quick-edit-note]')!;
  expect([opener()?.getAttribute('aria-expanded'), compose().hasAttribute('inert'), document.activeElement === note()]).toEqual(['false', true, false]);
  fireEvent.click(opener()!);
  await waitFor(() => expect(document.activeElement).toBe(note()));
  expect([opener(), compose().hasAttribute('inert')]).toEqual([null, false]);
  expect(box()!.querySelector('[data-quick-edit-resize]')).toBeNull();
});

it('Copy needs no note: with nothing written it copies what is picked, while Queue and Send wait for one', async () => {
  let copied: Promise<string> | string = '';
  const host = testHost({ clipboard: { writeText: async text => { copied = text; }, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver: vi.fn(), send: vi.fn() } as any });
  mount(host, { references: [face] });
  const disabled = () => ['Copy Prompt', 'Queue', 'Send'].map(name => within(box()!).getByRole('button', { name }).hasAttribute('disabled'));
  expect([note(), disabled()]).toEqual(['', [false, true, true]]);
  fireEvent.click(within(box()!).getByRole('button', { name: 'Copy Prompt' }));
  await waitFor(() => expect(within(box()!).getByRole('button', { name: 'Prompt copied' })).toBeTruthy());
  expect(await copied).toBe('File: /models/parts/bracket.step\nReferences:\n/models/parts/bracket.step#o:1a2b3c4d5e6f/f:base.extrude1.2');
});

it('peeking on a phone, its row is the note\'s field and a plain icon button per action, which acts without opening the sheet', async () => {
  let copied: Promise<string> | string = '';
  const host = testHost({ clipboard: { writeText: async text => { copied = text; }, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver: vi.fn(), send: vi.fn() } as any });
  const { update } = mount(host, { docked: true });
  press();
  update({ references: [face] });
  const peek = box()!.querySelector<HTMLElement>('[data-quick-edit-peek]')!;
  const actions = [...peek.querySelectorAll<HTMLButtonElement>('[data-quick-edit-peek-action]')];
  expect([within(peek).getByRole('button', { name: 'Describe your changes…' }) !== null,
    actions.map(button => [button.dataset.quickEditPeekAction, button.getAttribute('aria-label'), button.getAttribute('data-variant'), button.disabled])])
    .toEqual([true, [['copy', 'Copy Prompt', 'outline', false], ['queue', 'Queue', 'outline', true], ['send', 'Send', 'outline', true]]]);
  fireEvent.click(actions[0]);
  await waitFor(() => expect(peek.querySelector('[data-quick-edit-peek-action="copy"]')!.getAttribute('aria-label')).toBe('Prompt copied'));
  expect(await copied).toBe('File: /models/parts/bracket.step\nReferences:\n/models/parts/bracket.step#o:1a2b3c4d5e6f/f:base.extrude1.2');
  expect(within(box()!).getByRole('button', { name: 'Describe your changes…' }).getAttribute('aria-expanded')).toBe('false');
});


it.each(['Copy Prompt', 'Queue', 'Send'])('%s includes a small snapshot as JSON with no file read', async action => {
  const { resolvePromptMessage } = await import('@text-to-cad/core/prompt');
  let message = '';
  const take = async (context: any) => { message = await resolvePromptMessage(context); return { status: 'added' as const, partIds: [] }; };
  const host = testHost({ clipboard: { writeText: async text => { message = await text; }, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver: take, send: take } });
  const packet = JSON.stringify({ input: resource.path, jobs: [{ camera: 'front' }] });
  const prompt = { views: () => [{ label: 'current view' }], files: vi.fn(async () => ({ inline: packet })), read: vi.fn() };
  mount(host, { references: [face], prompt });
  write('Keep it.');
  expect(prompt.files).not.toHaveBeenCalled();
  fireEvent.click(within(box()!).getByRole('button', { name: action }));
  await waitFor(() => expect(message).toContain('Snapshot JSON (cadgen snapshot --annotation):'));
  expect(message).toContain(packet);
  expect(message).toContain('/models/parts/bracket.step#o:1a2b3c4d5e6f/f:base.extrude1.2');
  expect(prompt.read).not.toHaveBeenCalled();
});


it.each(['unsaved build preview', 'previous revision'])('keeps the note and honestly delivers text/references for a displayed %s without snapshot jobs', async displayed => {
  const copied: string[] = [];
  const files = vi.fn();
  const unavailable = `The references and view describe the displayed ${displayed}. The saved file may differ; view replay is unavailable.`;
  const host = testHost({ clipboard: { writeText: async (value: string | Promise<string>) => { copied.push(await value); }, readText: async () => '', writeImage: async () => {} } });
  mount(host, { references: [face], prompt: { unavailable: () => unavailable, views: () => [{ label: 'current view' }], files } });
  write('Round this edge.');
  expect(screen.getByRole('status').textContent).toContain(displayed);
  fireEvent.click(screen.getByRole('button', { name: 'Copy Prompt' }));
  await waitFor(() => expect(copied).toHaveLength(1));
  expect(copied[0]).toContain('Round this edge.');
  expect(copied[0]).toContain('View replay unavailable:');
  expect(copied[0]).toContain('The saved file may differ');
  expect(copied[0]).toContain(face.target.selectors[0]);
  expect(copied[0]).not.toContain('Snapshot JSON');
  expect(files).not.toHaveBeenCalled();
  expect(note()).toBe('Round this edge.');
});
