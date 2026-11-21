import React, { Profiler } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import QuickEdit, { quickEditReferenceIds } from '../../../../../dist/renderers/kit/tools/quick-edit/QuickEdit.js';
import { ViewerHostContext } from '../../../../../dist/host/context.js';
import { testHost } from '../../../../../dist/host/testing/host.js';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const resource = { kind: 'workspace-file', path: '/models/parts/bracket.step', revision: 'r1' } as const;
const face = { resource, target: { kind: 'cad-selector', selectors: ['base/f:base.extrude1.2'] } } as const;
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

it('is always there: one row with nothing to carry, no close button; a row of attachments above the note with a pick, the keyboard the person\'s, never an agent\'s', () => {
  const edge = { resource, target: { kind: 'cad-selector', selectors: ['base/e:base.extrude1.3'] } } as const;
  const { update } = mount();
  // Nothing to carry: the bar, one row (the note and Copy Prompt); no attachments row, no X.
  expect([box() !== null, box()!.querySelector('[data-quick-edit-context]'), buttons()]).toEqual([true, null, ['Copy Prompt']]);
  // An agent's selection (no press of the person's) brings the attachments, above the note, which stays the same
  // element at the bar's foot (its box unmoved: `RendererShell.browser.test.mjs`), and leaves their keyboard where it was.
  const compose = box()!.querySelector('[data-quick-edit-compose]');
  update({ references: [face] });
  const context = box()!.querySelector('[data-quick-edit-context]');
  expect([context !== null, document.activeElement === field(), box()!.querySelector('[data-quick-edit-compose]') === compose,
    Boolean(context && context.compareDocumentPosition(compose!) & Node.DOCUMENT_POSITION_FOLLOWING)]).toEqual([true, false, true, true]);
  update({ references: [] });
  expect([box() !== null, box()!.querySelector('[data-quick-edit-context]')]).toEqual([true, null]);
  // The person's pick puts the keyboard in its note; a renderer with no chips of its own has its references
  // drawn as chips, one chip as every other: one is its own name, several their count.
  const groupText = () => [...box()!.querySelectorAll('[data-quick-edit-ref]')].map(chip => chip.textContent);
  press();
  update({ references: [face] });
  expect(document.activeElement).toBe(field());
  expect(within(box()!).queryByText('bracket.step')).toBeNull();
  expect(groupText()).toEqual(['base/f:base.extrude1.2']);
  // Each pick of theirs puts the keyboard back in the note.
  field().blur();
  press();
  update({ references: [face, edge] });
  expect(document.activeElement).toBe(field());
  expect(groupText()).toEqual(['2 refs']);
  // A reference naming several picks counts each, and each is listed by its id.
  const several = [{ resource, target: { kind: 'cad-selector', selectors: ['base/f:base.extrude1.2', 'base/e:base.extrude1.3', 'base/e:base.fillet1.4'] } }] as const;
  update({ references: several });
  expect(groupText()).toEqual(['3 refs']);
  expect(quickEditReferenceIds(several)).toEqual(['base/f:base.extrude1.2', 'base/e:base.extrude1.3', 'base/e:base.fillet1.4']);
  // A note is kept as the selection goes.
  write('Round it.');
  update({ references: [] });
  expect(note()).toBe('Round it.');
  // Escape keeps a note; in an empty box it is the viewer's own (whose clear takes the attachments).
  const escape = vi.fn();
  update({ references: [face], onEscape: escape });
  fireEvent.keyDown(field(), { key: 'Escape' });
  expect([box() !== null, escape.mock.calls.length]).toEqual([true, 0]);
  write('');
  fireEvent.keyDown(field(), { key: 'Escape' });
  expect(escape.mock.calls.length).toBe(1);
});

it('carries the annotation while there is ink, taking the keyboard once the pen lifts, and lets it go with the ink', () => {
  const annotation = (present: boolean) => ({ present });
  const view = () => document.querySelector('[data-slot="cad-file-view"]')!;
  const { update } = mount();
  update({ annotation: annotation(false) });
  expect(box()!.querySelector('[data-quick-edit-context]')).toBeNull();
  fireEvent.pointerDown(view());
  update({ annotation: annotation(true) });
  expect(box()!.querySelector('[data-quick-edit-ref="annotation"]')!.textContent).toBe('Annotation');
  expect(document.activeElement).not.toBe(field());
  fireEvent.pointerUp(view(), { button: 0 });
  expect(document.activeElement).toBe(field());
  update({ annotation: annotation(false) });
  expect(box()!.querySelector('[data-quick-edit-context]')).toBeNull();
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
  // The reference's own chip first (a renderer with no chips of its own has one a reference), then the bar's buttons.
  expect(buttons()).toEqual(['base/f:base.extrude1.2', 'Copy Prompt', 'Queue', 'Send']);
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
  // The annotation is a chip of its own, Annotation, on the attachments row; without a way to wipe it, it has no X.
  expect(buttons()).toEqual(['Annotation', 'base/f:base.extrude1.2', 'Copy Prompt']);
  write('Round this edge.');
  expect(prompt.files).not.toHaveBeenCalled();
  fireEvent.click(within(box()!).getByRole('button', { name: 'Copy Prompt' }));
  // Copied, nothing has gone yet: the note and what it carries stay, and the button says so.
  await waitFor(() => expect(within(box()!).getByRole('button', { name: 'Prompt copied' })).toBeTruthy());
  expect([note(), clear.mock.calls.length]).toEqual(['Round this edge.', 0]);
  expect(await copied).toBe('Round this edge.\n\nFile: /models/parts/bracket.step\nReferences:\n/models/parts/bracket.step#base/f:base.extrude1.2'
    + '\nSnapshot (cad step snapshot --annotation): /tmp/p/bracket-1.snapshot.json');
  // The views go with the selection they were sent with, for a packet that carries it (a board's).
  expect(prompt.files).toHaveBeenCalledWith(views, [face]);
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
  fireEvent.paste(field(), { clipboardData: { getData: () => '/models/parts/hinge.step#hinge/e:hinge.make1.4' } });
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
  paste('/models/parts/hinge.step#hinge/e:hinge.make1.4,hinge/e:hinge.make1.5\nand\n/robots/arm.urdf#upper_arm');
  const chips = [...field().querySelectorAll('[data-quick-edit-note-ref]')];
  expect(chips.map(chip => [chip.textContent, chip.getAttribute('contenteditable')]))
    .toEqual([['hinge.step · hinge/e:hinge.make1.4, hinge/e:hinge.make1.5', 'false'], ['arm.urdf · upper_arm', 'false']]);
  // A reference within a sentence is the sentence's.
  paste('see /models/parts/hinge.step#hinge/e:hinge.make1.9');
  expect(field().querySelectorAll('[data-quick-edit-note-ref]')).toHaveLength(2);
  fireEvent.click(within(box()!).getByRole('button', { name: 'Copy Prompt' }));
  expect(await waitFor(() => copied)).toBe('Round /models/parts/hinge.step#hinge/e:hinge.make1.4,hinge/e:hinge.make1.5 \nand\n/robots/arm.urdf#upper_arm see /models/parts/hinge.step#hinge/e:hinge.make1.9'
    + '\n\nFile: /models/parts/bracket.step\nReferences:\n/models/parts/bracket.step#base/f:base.extrude1.2');
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
  paste('/models/parts/bracket.step#base');
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

it("is a chat's input at the bottom of the view: its attachments on a row over the note, no X; the note across the bar, its buttons at its bottom-right in room the note keeps clear; one line growing as it is written to four", () => {
  mount(testHost(), { references: [face], chips: [{ key: 'a', label: 'bracket', glyph: 'solid' }, { key: 'b', label: 'Annotation', glyph: 'pencil' }] });
  const [context, compose] = [...box()!.children];
  expect([context.hasAttribute('data-quick-edit-context'), compose.hasAttribute('data-quick-edit-compose')]).toEqual([true, true]);
  expect([...context.querySelectorAll('[data-quick-edit-ref]')].map(chip => chip.getAttribute('data-quick-edit-ref'))).toEqual(['a', 'b']);
  expect(box()!.querySelector('[data-quick-edit-close]')).toBeNull();
  // The note spans the bar; its buttons stand at its bottom-right, the note keeping their room (one button, the control:
  // 28px on a desktop, from THE scale's tokens; 6px and the scrollbar's 8px lane) clear on every line; no corner to drag,
  // no sheet.
  expect([compose.firstElementChild!.hasAttribute('data-quick-edit-note-box'), compose.lastElementChild!.hasAttribute('data-quick-edit-actions'), field().style.paddingRight])
    .toEqual([true, true, 'calc(1 * var(--cad-control) + 0 * var(--cad-step) + 14px)']);
  expect([box()!.querySelector('[data-quick-edit-resize]'), document.querySelector('[data-quick-edit-sheet]')]).toEqual([null, null]);
  expect((box()!.querySelector('[data-quick-edit-note-box]') as HTMLElement).style.maxHeight).toBe('92px');
  expect(field().getAttribute('data-placeholder')).toBe('Describe a change…');
  // What a person types, and the placeholder, at the chrome's UI size (13/20), not the bar's 12px.
  expect([field().classList.contains('text-ui'), field().classList.contains('text-xs'), field().classList.contains('leading-5')]).toEqual([true, false, true]);
});

it('Shift+Enter writes a new line in the note, a real one that goes with it; Enter copies', async () => {
  let copied: Promise<string> | string = '';
  const host = testHost({ clipboard: { writeText: async text => { copied = text; }, readText: async () => '', writeImage: async () => {} } });
  mount(host, { references: [face] });
  write('First line.');
  const selection = document.getSelection()!;
  selection.selectAllChildren(field());
  selection.collapseToEnd();
  fireEvent.keyDown(field(), { key: 'Enter', shiftKey: true });
  field().append(document.createTextNode('Second line.'));
  fireEvent.input(field());
  expect(note()).toBe('First line.\nSecond line.');
  fireEvent.keyDown(field(), { key: 'Enter' });
  await waitFor(() => expect(within(box()!).getByRole('button', { name: 'Prompt copied' })).toBeTruthy());
  expect(String(await copied).startsWith('First line.\nSecond line.\n\nFile:')).toBe(true);
});

it("counts its attachments coming, so we can tell how often it has something to carry", async () => {
  const { ControlUsageProvider } = await import('../../../../../dist/usage/controls.js');
  const report = vi.fn();
  const view = (references: readonly unknown[]) => <ControlUsageProvider report={report} flushMs={0}>
    <ViewerHostContext.Provider value={testHost()}><div data-slot="cad-file-view"><QuickEdit resource={resource} references={references} /></div></ViewerHostContext.Provider>
  </ControlUsageProvider>;
  const { rerender, unmount } = render(view([]));
  rerender(view([face]));
  unmount();
  const counted = report.mock.calls.flatMap(([counts]) => counts.map((count: { control: string }) => count.control));
  expect(counted).toEqual(['quick_edit_shown']);
});

it('keeps its note through a reload of the view: out of sight while it loads, and back as it was', () => {
  const { update } = mount(testHost(), { references: [face] });
  write('Thicker here.');
  update({ hidden: true });
  expect(document.querySelector('[data-quick-edit]')!.className).toMatch(/\bhidden\b/);
  update({ hidden: false });
  expect(note()).toBe('Thicker here.');
});

it('docked on a phone it is the same bar, at the scale\'s sizes (its tokens: a phone\'s from the one switch), and a pick leaves the keyboard down', () => {
  const { update } = mount(testHost(), { docked: true });
  press();
  update({ references: [face] });
  expect([box()!.hasAttribute('data-docked'), document.querySelector('[data-quick-edit-sheet]'), document.activeElement === field()]).toEqual([true, null, false]);
  expect(within(box()!).getByRole('button', { name: 'Copy Prompt' }).className).toMatch(/\bsize-control\b/);
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
  expect(await copied).toBe('File: /models/parts/bracket.step\nReferences:\n/models/parts/bracket.step#base/f:base.extrude1.2');
});

it.each(['Copy Prompt', 'Queue', 'Send'])('%s includes a small snapshot as JSON with no file read', async action => {
  const { resolvePromptMessage } = await import('@cad/core/prompt');
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
  await waitFor(() => expect(message).toContain('Snapshot JSON (cad step snapshot --annotation):'));
  expect(message).toContain(packet);
  expect(message).toContain('/models/parts/bracket.step#base/f:base.extrude1.2');
  expect(prompt.read).not.toHaveBeenCalled();
});


it.each(['Copy Prompt', 'Send'])('%s names every file from the workspace the host says, the inline packet\'s input too, never by the home', async action => {
  const { resolvePromptMessage } = await import('@cad/core/prompt');
  let message = '';
  const take = async (context: any) => { message = await resolvePromptMessage(context); return { status: 'sent' as const, partIds: [] }; };
  const board = { kind: 'workspace-file', path: '/Users/jake/robots/demo/twin_orbit.kicad_pcb' } as const;
  const part = { resource: board, target: { kind: 'cad-selector', selectors: ['#R1'] } } as const;
  const folders = vi.fn(async () => ({ start: '/Users/jake/robots/demo', home: '/Users/jake' }));
  const host = testHost({ clipboard: { writeText: async text => { message = await text; }, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => composer, subscribe: () => () => {}, deliver: take, send: take },
    promptFiles: { create: vi.fn(), read: vi.fn(), folders } });
  const packet = JSON.stringify({ input: board.path, jobs: [{ camera: 'front', outputs: [{ path: '/tmp/cad-quick-edit-a/twin_orbit-1-current.png' }] }] });
  const prompt = { views: () => [{ label: 'current view' }], files: vi.fn(async () => ({ inline: packet })), read: vi.fn() };
  mount(host, { resource: board, references: [part], prompt });
  write('Add a logo here.');
  fireEvent.click(within(box()!).getByRole('button', { name: action }));
  await waitFor(() => expect(message).toContain('Snapshot JSON'));
  expect(folders).toHaveBeenCalledTimes(1);
  expect(message).toContain('File: twin_orbit.kicad_pcb\nReferences:\ntwin_orbit.kicad_pcb#R1\n');
  expect(message).toContain('{"input":"twin_orbit.kicad_pcb","jobs":[{"camera":"front","outputs":[{"path":"/tmp/cad-quick-edit-a/twin_orbit-1-current.png"}]}]}');
  expect(message).not.toContain('/Users/jake');
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

it('carries every reference as one chip: one its name, several their count, whose list names each with its kind and its key facts and whose X drops them all; the drawing its own chip; every reference still goes', async () => {
  let copied: Promise<string> | string = '';
  const host = testHost({ clipboard: { writeText: async text => { copied = text; }, readText: async () => '', writeImage: async () => {} } });
  const removed: string[] = [];
  const part = (name: string) => ({ key: `part:${name}`, label: name, glyph: 'solid', copy: `/models/parts/bracket.step#${name}`, onRemove: () => removed.push(name) });
  const faces = { key: 'run:base|face', label: 'base · 3 faces', glyph: 'face', count: 3, compact: { name: 'base', kind: 'face', count: 3 }, onRemove: () => removed.push('faces') };
  const edge = { key: 'edge:base|e2', label: 'base · edge 2', glyph: 'edge', onRemove: () => removed.push('edge') };
  // The view's description of a part: its key facts, a bad one among them (left out, never drawn).
  const flange = { ...part('output_flange'), detail: { id: 'part:output_flange', pick: '', kind: 'solid', title: 'output_flange',
    facts: [{ label: 'Size', value: '10 × 10 × 2 mm' }, { label: 'Volume', value: { not: 'text' } }, { label: 'Mass', value: '0.1 kg' }] } };
  const references = ['a', 'output_flange'].map(name => ({ resource, target: { kind: 'cad-selector', selectors: [name] } }));
  mount(host, { references, chips: [part('a'), faces, edge, flange], annotation: { present: true, clear: () => removed.push('ink') } });
  const chips = () => [...box()!.querySelectorAll('[data-quick-edit-refs] > [data-quick-edit-ref]')].map(chip => [chip.getAttribute('data-quick-edit-ref'), chip.textContent]);
  // A part, a run of three faces, an edge and another part: six references, one chip; the drawing beside it.
  expect(chips()).toEqual([['annotation', 'Annotation'], ['group:references', '6 refs']]);
  // Its list names each, by its glyph, its name and its kind, with its X and no card of its own, its key facts under it
  // (only what the view knows: a part with no description has none); its X drops them all.
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  await act(async () => { fireEvent.click(within(box()!).getByRole('button', { name: '6 refs' })); });
  const list = await screen.findByRole('dialog', { name: '6 refs' });
  const rows = () => within(screen.getByRole('dialog')).getAllByRole('listitem').map(item => [item.querySelector('[data-quick-edit-group-show]')!.textContent,
    [...item.querySelectorAll('[data-quick-edit-ref-facts] > div')].map(fact => fact.textContent).join('; ')]);
  expect(rows()).toEqual([['aPart', ''], ['base · 3 faces3 faces', ''], ['base · edge 2Edge', ''], ['output_flangePart', 'Size10 × 10 × 2 mm; Mass0.1 kg']]);
  // The facts in the muted 11/16, under the name.
  expect(list.querySelector('[data-quick-edit-ref-facts]')!.className).toContain('text-tiny');
  expect(list.querySelector('[data-quick-edit-ref-facts]')!.className).toContain('text-muted-foreground');
  expect(document.querySelector('[data-quick-edit-ref-card]')).toBeNull();
  expect(warn).toHaveBeenCalled();
  warn.mockRestore();
  fireEvent.click(within(box()!).getByRole('button', { name: 'Remove 6 refs' }));
  expect(removed).toEqual(['a', 'faces', 'edge', 'output_flange']);
  // One reference is its own chip, by its name; a run of faces alone is its count.
  cleanup();
  mount(host, { references: [references[1]], chips: [flange] });
  expect(chips()).toEqual([['part:output_flange', 'output_flange']]);
  // A press on it shows that one's row and facts, the same list (no second popover); a press on its name there copies it.
  await act(async () => { fireEvent.click(within(box()!).getByRole('button', { name: 'output_flange' })); });
  await screen.findByRole('dialog', { name: 'output_flange' });
  expect(rows()).toEqual([['output_flangePart', 'Size10 × 10 × 2 mm; Mass0.1 kg']]);
  expect(document.querySelectorAll('[role="dialog"]').length).toBe(1);
  await act(async () => { fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'output_flange' })); });
  expect(await waitFor(() => copied)).toBe('/models/parts/bracket.step#output_flange');
  copied = '';
  cleanup();
  mount(host, { references: [references[0]], chips: [faces] });
  expect(chips()).toEqual([['group:references', '3 refs']]);
  cleanup();
  // The prompt is the same: every reference goes, whatever the chips show.
  mount(host, { references, chips: [part('a'), flange] });
  fireEvent.click(within(box()!).getByRole('button', { name: 'Copy Prompt' }));
  const text = String(await waitFor(() => copied));
  for (const name of ['a', 'output_flange']) expect(text).toContain(`/models/parts/bracket.step#${name}`);
});
