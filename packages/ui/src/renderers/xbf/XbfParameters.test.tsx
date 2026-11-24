import React from 'react';
import { act, cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import FlatPanel, { FLAT_PANEL_DEFAULT_WIDTH } from '../../../dist/renderers/kit/shell/FlatPanel.js';
import XbfParametersSection, { useXbfParameters } from '../../../dist/renderers/xbf/XbfParametersSection.js';
import { xbfPanelSections } from '../../../dist/renderers/xbf/XbfRenderer.js';
import QuickEdit from '../../../dist/renderers/kit/tools/quick-edit/QuickEdit.js';
import { ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';

// The Parameters tab of an engine document's panel: a model's declared numbers as the structure
// serves them, edited as drafts shown on screen as they move (a preview the engine builds for this page
// alone, nothing written), saved in one request through the client, said once to the agent.

Object.assign(globalThis, { React });
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView ||= () => {};
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const ID = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
// The model's own two, ranged and not, one of another module's, and one its code computes.
const structureOf = ({ wall = 2, holes = 6 } = {}) => ({ parameters: [
  { name: 'wall', value: wall, kind: 'float', min: 1, max: 5, step: 0.5, unit: 'mm', writable: true, reason: null, source: 'bracket.py' },
  { name: 'holes', value: holes, kind: 'int', min: null, max: null, step: null, unit: null, writable: true, reason: null, source: 'bracket.py' },
  { name: 'pitch', value: 30, kind: 'float', min: null, max: null, step: null, unit: 'deg', writable: false, reason: 'shared', source: 'lib/spec.py' },
  { name: 'gap', value: 0.5, kind: 'float', min: 0, max: 1, step: null, unit: null, writable: false, reason: 'expression', source: 'bracket.py' },
] });
const modelDocument = (structure: object) => ({ source: { kind: 'model', doc: ID }, structure });
const resource = { kind: 'cad-model', path: ID } as const;
const face = { resource, target: { kind: 'cad-selector', selectors: ['base/f:base.extrude1.2'] } } as const;

function Tab({ client, document, copied = null, drawn = null, onEdit = null }: { client: any, document: any, copied?: string[] | null, drawn?: (string | null)[] | null, onEdit?: (() => void) | null }) {
  // The scene's side: what the tab hands it to draw, drawn at once (`useXbfScene`'s `preview` and `previewing`).
  const [previewing, setPreviewing] = React.useState<string | null>(null);
  const onPreview = React.useCallback((url: string | null) => { drawn?.push(url); setPreviewing(url); }, [drawn]);
  const parameters = useXbfParameters({ client, document, onPreview, previewing, onEdit });
  const host = React.useMemo(() => testHost({ clipboard: { writeText: async (text: string | Promise<string>) => { copied?.push(await text); },
    readText: async () => '', writeImage: async () => {} } }), [copied]);
  return <ViewerHostContext.Provider value={host}>
    <FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
      sections={<XbfParametersSection parameters={parameters} />} tab="parameters" onTabChange={() => {}} width={FLAT_PANEL_DEFAULT_WIDTH} maxWidth={480}
      onWidthChange={() => {}} focusSearch={0} />
    {copied ? <div data-slot="cad-file-view"><QuickEdit resource={resource} references={[face]} notes={parameters.notes} /></div> : null}
  </ViewerHostContext.Provider>;
}

const tab = () => document.querySelector<HTMLElement>('[data-flat-panel-section="parameters"]')!;
// Each parameter: its name, its control, the value it shows, and why it is off where it is its own reason (its hint).
const rows = () => [...tab().querySelectorAll<HTMLElement>('[data-parameter]')].map(row => [row.getAttribute('data-parameter'),
  row.getAttribute('data-parameter-control'), row.querySelector<HTMLInputElement>('input')?.value, row.getAttribute('aria-description')]);
// Which controls are off: a field disabled, a slider's root marked so.
const off = () => [...tab().querySelectorAll<HTMLElement>('[data-parameter]')].map(row => Boolean(row.querySelector('input:disabled, [data-slot="slider"][data-disabled]')));
// Why Save is off, where it is for a reason: the reason's code, and what its hint says.
const saveWhy = () => {
  const wrapper = tab().querySelector<HTMLElement>('[data-parameters-save-reason]');
  return wrapper ? [wrapper.getAttribute('data-parameters-save-reason'), wrapper.getAttribute('aria-description')] : null;
};
const valueField = (name: string) => within(tab()).getByLabelText(`${name} value`) as HTMLInputElement;
const save = () => within(tab()).getByRole('button', { name: /^(Save|Saving…)$/ }) as HTMLButtonElement;
const reset = () => within(tab()).getByRole('button', { name: 'Reset' }) as HTMLButtonElement;
const status = () => tab().querySelector('[data-parameters-status]')!.textContent;
async function type(user: ReturnType<typeof userEvent.setup>, name: string, text: string) {
  await user.clear(valueField(name));
  await user.type(valueField(name), `${text}{Enter}`);
}

it('is a slider over a declared range, a number field without one, and one the code holds elsewhere is off, its hint saying why, under its file\'s name', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  render(<Tab client={{ setModelParameters: vi.fn() }} document={modelDocument(structureOf())} />);
  // One tab is a title, not a pill.
  expect([document.querySelector('[role=tablist]'), document.querySelector('[data-flat-panel-heading]')!.textContent]).toEqual([null, 'Params']);
  // From two files: the model's own first, with no heading, then the other file's under its name.
  expect(rows()).toEqual([
    ['wall', 'slider', '2.0', null],
    ['holes', 'number', '6', null],
    ['gap', 'slider', '0.50', 'Calculated in the code.'],
    ['pitch', 'number', '30°', 'Set in lib/spec.py.'],
  ]);
  const heading = tab().querySelector<HTMLElement>('[data-parameters-file]')!;
  expect([[...tab().querySelectorAll('[data-parameters-file]')].map(element => element.textContent),
    Boolean(heading.compareDocumentPosition(tab().querySelector('[data-parameter="pitch"]')!) & Node.DOCUMENT_POSITION_FOLLOWING),
    Boolean(heading.compareDocumentPosition(tab().querySelector('[data-parameter="gap"]')!) & Node.DOCUMENT_POSITION_PRECEDING)]).toEqual([['lib/spec.py'], true, true]);
  expect(off()).toEqual([false, false, true, true]);
  // No line of text says it: the off control's hint does, on hover.
  expect(tab().querySelector('[role=alert]')).toBeNull();
  await user.hover(tab().querySelector('[data-parameter="pitch"]')!);
  expect((await within(document.body).findByRole('tooltip')).textContent).toContain('Set in lib/spec.py.');
  // The slider spans the declared range, by the declared step; nothing is drafted, so nothing is to save.
  const thumb = within(tab()).getByRole('slider', { name: 'wall' });
  expect([thumb.getAttribute('aria-valuemin'), thumb.getAttribute('aria-valuemax'), thumb.getAttribute('aria-valuenow')]).toEqual(['1', '5', '2']);
  // Off with nothing to save is no reason: no hint.
  expect([save().disabled, reset().disabled, status(), saveWhy()]).toEqual([true, true, '', null]);
  // Save and Reset are the tab's last row, under the list, in its foot (kept at the panel's bottom edge as a long list scrolls).
  const foot = tab().querySelector<HTMLElement>('[data-parameters-foot]')!;
  const last = [...tab().querySelectorAll('[data-parameter]')].at(-1)!;
  expect([foot.contains(save()), Boolean(last.compareDocumentPosition(foot) & Node.DOCUMENT_POSITION_FOLLOWING), foot.classList.contains('sticky')]).toEqual([true, true, true]);
});

it('a file document and a model no worker holds say why in the foot\'s status; a host that cannot save says it on Save', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const statusReason = () => tab().querySelector('[data-parameters-status]')!.getAttribute('data-parameters-status-reason');
  const read = () => [off(), rows().map(row => row[3]), save().disabled, saveWhy(), status(), statusReason()];
  const fileStructure = { parameters: structureOf().parameters.map(parameter => ({ ...parameter, writable: false, reason: 'file', source: null })) };
  const { rerender } = render(<Tab client={{ setModelParameters: vi.fn() }} document={{ source: { kind: 'xbf', doc: ID }, structure: fileStructure }} />);
  // Nothing in the tab can work: said once, as text, left of Reset and Save; Save is simply off, with no hint.
  expect(read()).toEqual([[true, true, true, true], [null, null, null, null], true, null, 'Edit these in the script.', 'file']);
  // From one file (none named another): no heading at all.
  expect(tab().querySelector('[data-parameters-file]')).toBeNull();
  // After a restart no worker holds the script's run (`no_worker`): the same, its own line.
  const unheld = { parameters: structureOf().parameters.map(parameter => ({ ...parameter, writable: false, reason: 'no_worker' })) };
  rerender(<Tab client={{ setModelParameters: vi.fn() }} document={modelDocument(unheld)} />);
  expect(read()).toEqual([[true, true, true, true], [null, null, null, null], true, null, 'Run the script again to edit.', 'no_worker']);
  // Locked, only the controls look it: the labels and the values keep their colours (no half strength on them), the
  // sliders and fields are at half strength with a not-allowed pointer, and Save is drawn as Reset is off (the neutral
  // button's disabled look), never a filled grey.
  const labels = [...tab().querySelectorAll<HTMLElement>('[data-parameter] [data-field-label]')];
  expect(labels.length > 0 && labels.every(label => !label.className.includes('opacity-50') && label.className.includes('text-muted-foreground'))).toBe(true);
  const values = [...tab().querySelectorAll<HTMLElement>('[data-parameter] [data-slider-field-value]')];
  expect(values.length > 0 && values.every(value => !value.closest('[data-disabled]')!.className.split(' ').includes('data-[disabled]:opacity-50'))).toBe(true);
  const tracks = [...tab().querySelectorAll<HTMLElement>('[data-parameter] [data-slider-field-track]')];
  expect(tracks.length > 0 && tracks.every(track => track.hasAttribute('data-disabled') && track.className.includes('data-[disabled]:cursor-not-allowed'))).toBe(true);
  const fields = [...tab().querySelectorAll<HTMLElement>('[data-parameter-control="number"] input')].map(input => input.closest<HTMLElement>('.rounded-md')!);
  expect(fields.length > 0 && fields.every(field => field.className.includes('opacity-50') && field.className.includes('cursor-not-allowed'))).toBe(true);
  expect([save().getAttribute('data-variant'), reset().getAttribute('data-variant'), save().disabled]).toEqual(['ghost', 'ghost', true]);
  // The message stands directly over Reset and Save, in the foot.
  expect(tab().querySelector('[data-parameters-foot] [data-parameters-status] + [data-parameters-buttons]')).not.toBeNull();
  // A host whose client has no way to save (the method left out): every control off, a parameter's own reason on it,
  // and Save's hint says why (a disabled Save still shows it: its wrapper takes the pointer).
  rerender(<Tab client={{}} document={modelDocument(structureOf())} />);
  expect(read()).toEqual([[true, true, true, true], [null, null, 'Calculated in the code.', 'Set in lib/spec.py.'], true,
    ['unavailable', 'This view can’t save.'], '', null]);
  await user.hover(tab().querySelector('[data-parameters-save-reason]')!);
  expect((await within(document.body).findByRole('tooltip')).textContent).toContain('This view can’t save.');
  expect(tab().querySelector('[role=alert]')).toBeNull();
});

it('edits are drafts until Save, which sends only the changed values in one request, busy meanwhile; Reset drops them', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  let answer!: (value: unknown) => void;
  const setModelParameters = vi.fn(() => new Promise(resolve => { answer = resolve; }));
  render(<Tab client={{ setModelParameters }} document={modelDocument(structureOf())} />);
  // A slider moved is a draft: nothing is sent while it moves.
  fireEvent.keyDown(within(tab()).getByRole('slider', { name: 'wall' }), { key: 'ArrowRight' });
  expect([valueField('wall').value, status(), setModelParameters.mock.calls.length]).toEqual(['2.5', '', 0]);
  await user.click(reset());
  expect([valueField('wall').value, status(), save().disabled]).toEqual(['2.0', '', true]);
  // A whole number for an integer parameter; a value typed back to the document's is no draft.
  await type(user, 'holes', '7.6');
  await type(user, 'wall', '3');
  await type(user, 'wall', '2');
  await type(user, 'wall', '3.5');
  expect([valueField('holes').value, valueField('wall').value, status()]).toEqual(['8', '3.5', '']);
  await user.click(save());
  expect(setModelParameters.mock.calls).toEqual([[ID, { holes: 8, wall: 3.5 }]]);
  // While it is out: every control and both buttons off, Save says so.
  expect([save().textContent, save().disabled, save().getAttribute('aria-busy'), reset().disabled, valueField('holes').disabled, valueField('wall').disabled,
    within(tab()).getByRole('slider', { name: 'wall' }).hasAttribute('data-disabled')]).toEqual(['Saving…', true, 'true', true, true, true, true]);
  await act(async () => answer({ id: ID, written: [], rebuilt: [] }));
  expect(save().textContent).toBe('Save');
});

it('a refused save turns Save off, its hint saying why until an edit; a changed script turns every control off until it runs again', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const refusal = (code: string, message: string, hint = '') => Object.assign(new Error(message), { code, hint });
  const setModelParameters = vi.fn()
    .mockRejectedValueOnce(refusal('out_of_range', 'wall takes 1 to 5, not 9'))
    .mockRejectedValueOnce(refusal('locked', 'the script is locked by another save', 'try again'))
    .mockRejectedValueOnce(refusal('busy', 'bracket.py is building now'))
    .mockRejectedValueOnce(refusal('script_changed', 'bracket.py changed since it last ran', 'run it first'));
  const client = { setModelParameters };
  const { rerender } = render(<Tab client={client} document={modelDocument(structureOf())} />);
  await type(user, 'holes', '9');
  const said = async () => {
    await user.click(save());
    await waitFor(() => expect(saveWhy()).not.toBeNull());
    return [...saveWhy()!, save().disabled, valueField('holes').value, status()];
  };
  // A refusal says the tab's one short line, never the engine's message; the drafts stay, and no count is shown.
  expect(await said()).toEqual(['out_of_range', 'A value is out of range.', true, '9', '']);
  expect(tab().querySelector('[role=alert]')).toBeNull();
  // An edit clears it, and Save is on again.
  await type(user, 'holes', '10');
  expect([saveWhy(), save().disabled]).toEqual([null, false]);
  // A code this page does not know: a plain failure, the engine's words left out.
  expect(await said()).toEqual(['unknown', 'Couldn’t save.', true, '10', '']);
  await type(user, 'holes', '11');
  // The model building: off a moment, then Save may be pressed again, the draft kept.
  expect(await said()).toEqual(['busy', 'Still building. Try again soon.', true, '11', '']);
  await waitFor(() => expect(saveWhy()).toBeNull(), { timeout: 3000 });
  expect(save().disabled).toBe(false);
  // The script changed by hand since it ran: nothing can be saved until it runs again. The foot says so, Save is
  // off, and nothing is taken back: the draft stays on its control, every control stays live.
  await user.click(save());
  await waitFor(() => expect(status()).toBe('Script changed. Run it again.'));
  expect([saveWhy(), save().disabled, valueField('holes').value, off()]).toEqual([null, true, '11', [false, false, true, true]]);
  // An edit does not clear it: only the script's next run tells the tab it can save again.
  await type(user, 'holes', '12');
  expect([status(), save().disabled, valueField('holes').value]).toEqual(['Script changed. Run it again.', true, '12']);
  expect(setModelParameters.mock.calls.map(call => call[1])).toEqual([{ holes: 9 }, { holes: 10 }, { holes: 11 }, { holes: 11 }]);
  // The script run again (its next version): Save is on again, the draft where the person left it.
  rerender(<Tab client={client} document={modelDocument(structureOf({ holes: 7 }))} />);
  await waitFor(() => expect(status()).toBe(''));
  expect([saveWhy(), save().disabled, valueField('holes').value, off()]).toEqual([null, false, '12', [false, false, true, true]]);
}, 10000);

it('a save answered changes nothing on screen until the rebuilt document holds the values, and then the drafts are gone', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const setModelParameters = vi.fn(async () => ({ id: ID, rebuilt: [ID],
    written: [{ name: 'wall', from: 2, to: 3, file: '/home/someone/parts/bracket.py', line: 7 }, { name: 'holes', from: 6, to: 8, file: '/home/someone/parts/bracket.py', line: 8 }] }));
  const client = { setModelParameters };
  const { rerender } = render(<Tab client={client} document={modelDocument(structureOf())} />);
  await type(user, 'wall', '3');
  await type(user, 'holes', '8');
  await user.click(save());
  await waitFor(() => expect(status()).toBe('Saved'));
  // Answered: the values stay on their controls, awaited, and are not sent again.
  expect([valueField('wall').value, valueField('holes').value, save().disabled]).toEqual(['3.0', '8', true]);
  // A new version that holds one of them: that draft goes, the other is still awaited.
  rerender(<Tab client={client} document={modelDocument(structureOf({ wall: 3 }))} />);
  expect([valueField('wall').value, valueField('holes').value, status()]).toEqual(['3.0', '8', '']);
  rerender(<Tab client={client} document={modelDocument(structureOf({ wall: 3, holes: 8 }))} />);
  expect([valueField('wall').value, valueField('holes').value, status(), save().disabled]).toEqual(['3.0', '8', 'Saved', true]);
  expect(setModelParameters).toHaveBeenCalledTimes(1);
});

it('the next Quick Edit carries what was saved, once, by the script\'s name; a later one does not', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const copied: string[] = [];
  const setModelParameters = vi.fn(async (_id: string, values: Record<string, number>) => ({ id: ID, rebuilt: [ID],
    written: Object.entries(values).map(([name, to]) => ({ name, from: name === 'wall' ? 2 : 6, to, file: '/home/someone/parts/bracket.py', line: 7 })) }));
  render(<Tab client={{ setModelParameters }} document={modelDocument(structureOf())} copied={copied} />);
  await type(user, 'wall', '2.5');
  await user.click(save());
  await waitFor(() => expect(status()).toBe('Saved'));
  const copy = async (count: number) => {
    fireEvent.click(document.querySelector<HTMLElement>('[data-quick-edit-action="copy"]')!);
    await waitFor(() => expect(copied).toHaveLength(count));
  };
  await copy(1);
  await copy(2);
  const block = 'Saved from the viewer since your last edit: wall 2 -> 2.5 (bracket.py); the script holds these values and is built at them: read it again before you edit it, and keep them';
  // After what the person wrote (nothing here) and before the file: said once, then not again.
  expect(copied[0]).toBe(`${block}\n\n${copied[1]}`);
  expect(copied[1]).not.toContain('Saved from the viewer');
  expect(copied[1]).toContain(ID);
  expect(copied.join('\n')).not.toContain('/home/someone');
});

it('what was saved is handed to one message at a time: a second taken before the first has gone carries none of it', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const setModelParameters = vi.fn(async () => ({ id: ID, rebuilt: [ID], written: [{ name: 'wall', from: 2, to: 2.5, file: '/parts/bracket.py', line: 7 }] }));
  let notes: any = null;
  function Held(props: any) {
    const parameters = useXbfParameters(props);
    notes = parameters.notes;
    return <FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
      sections={<XbfParametersSection parameters={parameters} />} tab="parameters" onTabChange={() => {}} width={FLAT_PANEL_DEFAULT_WIDTH} maxWidth={480}
      onWidthChange={() => {}} focusSearch={0} />;
  }
  render(<Held client={{ setModelParameters }} document={modelDocument(structureOf())} />);
  await type(user, 'wall', '2.5');
  await user.click(save());
  await waitFor(() => expect(status()).toBe('Saved'));
  const first = notes.take();
  expect(first?.text).toContain('wall 2 -> 2.5');
  expect(notes.take()).toBeNull(); // pressed again before the first has gone
  first.cancel(); // the first did not go: the next message carries it
  const again = notes.take();
  expect(again?.text).toBe(first.text);
  again.done();
  expect(notes.take()).toBeNull();
});

it('the Model tab is first wherever there is a part: a part file\'s one row, then its Params and Joints', () => {
  // A part file: its one row, then Parameters, then Position, as an assembly's.
  expect(xbfPanelSections({ parts: 1, posable: false, parameters: 2 })).toEqual(['model', 'parameters']);
  expect(xbfPanelSections({ parts: 1, posable: false, parameters: 0 })).toEqual(['model']);
  expect(xbfPanelSections({ parts: 1, posable: true, parameters: 1 })).toEqual(['model', 'parameters', 'position']);
  expect(xbfPanelSections({ parts: 3, posable: true, parameters: 1 })).toEqual(['model', 'parameters', 'position']);
  expect(xbfPanelSections({ parts: 3, posable: false, parameters: 0 })).toEqual(['model']);
  // Nothing in the tree, nothing recorded: no panel.
  expect(xbfPanelSections({ parts: 0, posable: false, parameters: 0 })).toEqual([]);
});

// A preview client: each request answered by the test (`answer`), the URL of each one the values it was for.
function previewClient() {
  const pending: { values: Record<string, number>, page: string, resolve: (value: unknown) => void, reject: (error: unknown) => void }[] = [];
  const previewModelParameters = vi.fn((_id: string, values: Record<string, number>, { page }: { page: string }) =>
    new Promise((resolve, reject) => { pending.push({ values, page, resolve, reject }); }));
  const answer = async (outcome?: unknown) => {
    const next = pending.shift()!;
    await act(async () => {
      if (outcome instanceof Error) next.reject(outcome);
      else next.resolve(outcome ?? (Object.keys(next.values).length
        ? { id: ID, preview: { id: `${ID}~preview-${JSON.stringify(next.values)}`, url: `/preview/${JSON.stringify(next.values)}`, values: next.values } }
        : { id: ID, preview: null }));
    });
    return next;
  };
  return { previewModelParameters, pending, answer };
}
const moveWall = (times: number, key = 'ArrowRight') => {
  for (let at = 0; at < times; at += 1) fireEvent.keyDown(within(tab()).getByRole('slider', { name: 'wall' }), { key });
};

it('a slider moved shows the model at its values as fast as they build, one request out, the newest next, nothing written', async () => {
  const drawn: (string | null)[] = [];
  const { previewModelParameters, pending, answer } = previewClient();
  const setModelParameters = vi.fn();
  render(<Tab client={{ setModelParameters, previewModelParameters }} document={modelDocument(structureOf())} drawn={drawn} />);
  moveWall(1);
  await waitFor(() => expect(previewModelParameters).toHaveBeenCalledTimes(1));
  // Moved on while it builds: nothing more goes out until it is answered, then the newest values at once.
  moveWall(3);
  expect(previewModelParameters).toHaveBeenCalledTimes(1);
  const first = await answer();
  expect(first.values).toEqual({ wall: 2.5 });
  expect(drawn).toEqual(['/preview/{"wall":2.5}']);
  await waitFor(() => expect(previewModelParameters).toHaveBeenCalledTimes(2));
  expect(pending[0].values).toEqual({ wall: 4 });
  expect(pending[0].page).toBe(first.page); // the page's own token, every time
  await answer();
  expect(drawn).toEqual(['/preview/{"wall":2.5}', '/preview/{"wall":4}']);
  // The model on screen is unsaved: Save is on, and no count says so; nothing was written.
  expect([status(), save().disabled]).toEqual(['', false]);
  expect(setModelParameters).not.toHaveBeenCalled();
  expect(previewModelParameters).toHaveBeenCalledTimes(2);
});

it('Reset draws the document again at once and lets the preview go; Save sends the drafts in one request and keeps the preview until the version holds them', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const drawn: (string | null)[] = [];
  const { previewModelParameters, pending, answer } = previewClient();
  const setModelParameters = vi.fn(async () => ({ id: ID, rebuilt: [ID], written: [{ name: 'wall', from: 2, to: 3, file: '/parts/bracket.py', line: 7 }] }));
  const client = { setModelParameters, previewModelParameters };
  const { rerender } = render(<Tab client={client} document={modelDocument(structureOf())} drawn={drawn} />);
  moveWall(2);
  await waitFor(() => expect(pending).toHaveLength(1));
  await answer();
  await waitFor(() => expect(pending).toHaveLength(1)); // the newest values, once that was answered
  await answer();
  await user.click(reset());
  expect([drawn.at(-1), valueField('wall').value, status()]).toEqual([null, '2.0', '']);
  await waitFor(() => expect(pending).toHaveLength(1));
  expect(pending[0].values).toEqual({}); // the engine told it may let it go
  await answer();
  // Edited again and saved: one request, the drafts alone; no preview asked while it is out or after it.
  await type(user, 'wall', '3');
  await waitFor(() => expect(pending).toHaveLength(1));
  await answer();
  expect(drawn.at(-1)).toBe('/preview/{"wall":3}');
  await user.click(save());
  await waitFor(() => expect(status()).toBe('Saved'));
  expect(setModelParameters.mock.calls).toEqual([[ID, { wall: 3 }]]);
  expect([drawn.at(-1), pending.length]).toEqual(['/preview/{"wall":3}', 0]);
  // The version that holds them arrives: the document is drawn, the preview let go.
  rerender(<Tab client={client} document={modelDocument(structureOf({ wall: 3 }))} drawn={drawn} />);
  await waitFor(() => expect(drawn.at(-1)).toBeNull());
  expect([valueField('wall').value, status()]).toEqual(['3.0', 'Saved']);
});

it('a preview refused turns Save off and keeps the last one that built; a busy model is asked again; a changed script says so and takes nothing back', async () => {
  const drawn: (string | null)[] = [];
  const { previewModelParameters, pending, answer } = previewClient();
  const client = { setModelParameters: vi.fn(), previewModelParameters };
  const { rerender } = render(<Tab client={client} document={modelDocument(structureOf())} drawn={drawn} />);
  moveWall(1);
  await waitFor(() => expect(pending).toHaveLength(1));
  await answer();
  moveWall(4);
  await waitFor(() => expect(pending).toHaveLength(1));
  await answer(Object.assign(new Error('bracket does not build at these values: ValueError: too thick'),
    { code: 'build_failed', hint: 'try other values' }));
  // Nothing buildable to save: Save is off, its hint says why, and the view keeps the last values that built.
  expect([...saveWhy()!, save().disabled]).toEqual(['build_failed', 'These values don’t build.', true]);
  expect(tab().querySelector('[role=alert]')).toBeNull();
  expect(drawn).toEqual(['/preview/{"wall":2.5}']);
  // A build of the script under way: asked again, said nothing.
  moveWall(1, 'ArrowLeft');
  expect(saveWhy()).toBeNull();
  await waitFor(() => expect(pending).toHaveLength(1));
  await answer(Object.assign(new Error('bracket.py is building now'), { code: 'busy', hint: '' }));
  expect(saveWhy()).toBeNull();
  await waitFor(() => expect(pending).toHaveLength(1), { timeout: 2000 });
  expect(pending[0].values).toEqual({ wall: 4 });
  await answer();
  expect(drawn.at(-1)).toBe('/preview/{"wall":4}');
  // Moved back to the document's own value: drawn at once, the engine told after (once the first value the
  // slider passed is answered).
  moveWall(4, 'ArrowLeft');
  await waitFor(() => expect(drawn.at(-1)).toBeNull());
  expect(status()).toBe('');
  await waitFor(() => expect(pending).toHaveLength(1));
  await answer();
  await waitFor(() => expect(pending).toHaveLength(1));
  expect(pending[0].values).toEqual({});
  await answer();
  // The script changed by hand since it ran: the preview refused says so in the foot, and nothing snaps back or
  // locks: the slider stays where it was dragged, every control live, the view keeps what it drew.
  moveWall(2);
  await waitFor(() => expect(pending).toHaveLength(1));
  await answer(Object.assign(new Error('bracket.py changed since its last run'), { code: 'script_changed', hint: 'run the script first' }));
  await waitFor(() => expect(status()).toBe('Script changed. Run it again.'));
  expect([saveWhy(), save().disabled, valueField('wall').value, off(), drawn.at(-1), pending.length])
    .toEqual([null, true, '3.0', [false, false, true, true], null, 0]);
  // Moved again: the slider follows, and nothing more is asked until the script runs again.
  const asked = previewModelParameters.mock.calls.length;
  moveWall(1);
  expect([valueField('wall').value, status(), previewModelParameters.mock.calls.length]).toEqual(['3.5', 'Script changed. Run it again.', asked]);
  // Its next version: the drafts on screen are asked for again.
  rerender(<Tab client={client} document={modelDocument(structureOf())} drawn={drawn} />);
  await waitFor(() => expect(pending).toHaveLength(1));
  expect([pending[0].values, status()]).toEqual([{ wall: 3.5 }, '']);
});

it('a Quick Edit sent while unsaved values are on screen says so, every time, and what was saved once', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const copied: string[] = [];
  const { previewModelParameters, pending, answer } = previewClient();
  render(<Tab client={{ setModelParameters: vi.fn(), previewModelParameters }} document={modelDocument(structureOf())} copied={copied} />);
  await type(user, 'wall', '3.5');
  await waitFor(() => expect(pending).toHaveLength(1));
  await answer();
  const copy = async (count: number) => {
    fireEvent.click(document.querySelector<HTMLElement>('[data-quick-edit-action="copy"]')!);
    await waitFor(() => expect(copied).toHaveLength(count));
  };
  await copy(1);
  await copy(2);
  const line = 'Shown in the viewer, not saved: wall 2 -> 3.5 (bracket.py); the script still holds the first values; write the new ones only if asked';
  expect(copied[0]).toContain(line);
  expect(copied[1]).toContain(line);
  expect(copied[0]).not.toContain('Saved from the viewer');
});

// ---- the cadence: a fast model follows the slider, a slow one is sent the value the person comes to -----------
// Time is the test's (fake timers, the clock the hook measures a preview by included): a request answered after
// `advance(ms)` took that long.
const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
const useClock = () => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'] });
// A pointer on the wall slider (1 to 5 over a 100px track): down, moves and up at a value, as Radix reads them.
function wallPointer() {
  const root = tab().querySelector<HTMLElement>('[data-parameter="wall"] [data-slider-field-track]')!;
  root.getBoundingClientRect = () => ({ left: 0, right: 100, width: 100, top: 0, bottom: 12, height: 12, x: 0, y: 0, toJSON() {} }) as DOMRect;
  const at = (value: number) => ({ pointerId: 1, button: 0, clientX: ((value - 1) / 4) * 100, clientY: 6 });
  return {
    down: (value: number) => fireEvent.pointerDown(root, at(value)),
    move: (value: number) => fireEvent.pointerMove(root, at(value)),
    up: (value: number) => fireEvent.pointerUp(root, at(value)),
  };
}
// A value typed and committed (Enter), as the field takes it.
const typeIn = (name: string, text: string) => {
  fireEvent.change(valueField(name), { target: { value: text } });
  fireEvent.keyDown(valueField(name), { key: 'Enter' });
};
// Nothing says a preview builds: the foot's status never reads "Building", and no row carries a note.
const building = () => /Building/.test(tab().textContent ?? '') ? tab().textContent : null;
const thumb = () => within(tab()).getByRole('slider', { name: 'wall' });
// A slow model: its first preview (a keyboard step, sent at once while nothing is measured) answered in `ms`.
async function measured(previewModelParameters: any, answer: (outcome?: unknown) => Promise<unknown>, ms = 800) {
  moveWall(1);
  await advance(0);
  expect(previewModelParameters).toHaveBeenCalledTimes(1);
  await advance(ms);
  await answer();
}

describe('the preview cadence', () => {
  beforeEach(() => {
    useClock();
    Object.assign(Element.prototype, {
      setPointerCapture(this: any, id: number) { this.captured = id; },
      hasPointerCapture(this: any, id: number) { return this.captured === id; },
      releasePointerCapture(this: any) { delete this.captured; },
    });
  });
  afterEach(() => { vi.useRealTimers(); });

  it('a fast model streams while a slider is dragged: the newest values go as each answer arrives', async () => {
    const { previewModelParameters, pending, answer } = previewClient();
    render(<Tab client={{ setModelParameters: vi.fn(), previewModelParameters }} document={modelDocument(structureOf())} />);
    const pointer = wallPointer();
    pointer.down(2.5);
    await advance(0);
    expect(pending.map(request => request.values)).toEqual([{ wall: 2.5 }]);
    pointer.move(3);
    pointer.move(3.5);
    await advance(60);
    await answer(); // 60 ms: fast
    await advance(0);
    // Still held down: the newest value went at once.
    expect(pending.map(request => request.values)).toEqual([{ wall: 3.5 }]);
    pointer.move(4);
    await advance(60);
    await answer();
    await advance(0);
    expect(pending.map(request => request.values)).toEqual([{ wall: 4 }]);
    pointer.up(4);
    await advance(60);
    await answer();
    await advance(1000);
    expect(previewModelParameters.mock.calls.map(call => call[1])).toEqual([{ wall: 2.5 }, { wall: 3.5 }, { wall: 4 }]);
  });

  it('a slow model is sent nothing mid-drag: once on release, once on a 300 ms rest, once on a typed value', async () => {
    const { previewModelParameters, pending, answer } = previewClient();
    render(<Tab client={{ setModelParameters: vi.fn(), previewModelParameters }} document={modelDocument(structureOf())} />);
    await measured(previewModelParameters, answer); // 800 ms: slow
    const sent = () => previewModelParameters.mock.calls.slice(1).map(call => call[1]);
    const pointer = wallPointer();
    // A drag: every move under the rest, nothing sent while it moves; the value let go is sent, once.
    pointer.down(3);
    for (const value of [3.5, 4, 4.5, 4, 3.5]) { await advance(100); pointer.move(value); }
    await advance(100);
    expect(sent()).toEqual([]);
    expect([thumb().getAttribute('aria-valuenow'), valueField('wall').value]).toEqual(['3.5', '3.5']);
    pointer.up(3.5);
    await advance(0);
    expect(sent()).toEqual([{ wall: 3.5 }]);
    await advance(800);
    await answer();
    await advance(1000);
    expect(sent()).toEqual([{ wall: 3.5 }]);
    // Held still mid-drag for 300 ms: the value it rests on is sent, once, the pointer still down.
    pointer.down(4);
    await advance(100);
    pointer.move(4.5);
    await advance(299);
    expect(sent()).toEqual([{ wall: 3.5 }]);
    await advance(1);
    expect(sent()).toEqual([{ wall: 3.5 }, { wall: 4.5 }]);
    await advance(800);
    await answer();
    pointer.up(4.5); // let go where it rested: that value is drawn already, nothing more is sent
    await advance(1000);
    expect(sent()).toEqual([{ wall: 3.5 }, { wall: 4.5 }]);
    // A value typed: sent at once.
    typeIn('wall', '2');
    await advance(0);
    expect(sent()).toEqual([{ wall: 3.5 }, { wall: 4.5 }, {}]);
    await answer();
    typeIn('wall', '3');
    await advance(0);
    expect(sent()).toEqual([{ wall: 3.5 }, { wall: 4.5 }, {}, { wall: 3 }]);
    expect(pending).toHaveLength(1);
  });

  it('says nothing of a building preview, in the foot or on a row, and the slider stays live', async () => {
    const { previewModelParameters, pending, answer } = previewClient();
    render(<Tab client={{ setModelParameters: vi.fn(), previewModelParameters }} document={modelDocument(structureOf())} />);
    moveWall(1);
    await advance(400);
    expect(pending).toHaveLength(1);
    expect([building(), tab().querySelector('[data-parameters-status]')?.textContent]).toEqual([null, '']);
    moveWall(2);
    expect([thumb().hasAttribute('data-disabled'), thumb().getAttribute('aria-valuenow')]).toEqual([false, '3.5']);
    await advance(400);
    await answer();
    await advance(0);
    expect(building()).toBeNull();
  });
});

// A parameter edit lets go of what holds the model (the view's motion: `onEdit`) as it is made, before any preview is
// asked for: a preview the engine refuses leaves no clip in charge, and the Joints tab nothing locked.
it('every edit tells the view first, so a motion holding the model is let go of whether or not its preview builds', async () => {
  const { previewModelParameters, pending, answer } = previewClient();
  const onEdit = vi.fn();
  render(<Tab client={{ setModelParameters: vi.fn(), previewModelParameters }} document={modelDocument(structureOf())} onEdit={onEdit} />);
  moveWall(4);
  expect(onEdit).toHaveBeenCalled();
  const edits = onEdit.mock.calls.length;
  await waitFor(() => expect(pending).toHaveLength(1));
  await answer(Object.assign(new Error('bracket does not build at these values'), { code: 'build_failed', hint: '' }));
  // Refused, and the next edit is told as well.
  moveWall(1, 'ArrowLeft');
  expect(onEdit.mock.calls.length).toBeGreaterThan(edits);
});

// The Params tab's "changed" dot: on exactly while its Reset is (a draft off the document), from the same state.
it("the Params tab's dot is on exactly while its Reset is", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  render(<Tab client={{ setModelParameters: vi.fn(() => new Promise(() => {})) }} document={modelDocument(structureOf())} />);
  const heading = () => document.querySelector<HTMLElement>('[data-flat-panel-heading]')!;
  const state = () => [!reset().disabled, heading().hasAttribute('data-changed'), Boolean(heading().querySelector('[data-tool-changed]'))];
  expect(state()).toEqual([false, false, false]);
  fireEvent.keyDown(within(tab()).getByRole('slider', { name: 'wall' }), { key: 'ArrowRight' });
  expect([...state(), heading().getAttribute('aria-label')]).toEqual([true, true, true, 'Params, changed']);
  // Saving: Reset is off while the request is out, and so is the dot.
  await user.click(save());
  expect(state()).toEqual([false, false, false]);
});
